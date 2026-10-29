"""Pure business rules of the commercial process (no database access, unit-testable).

Covers pipeline probabilities, stage transitions, bid scoring, decision authority, proposal
calculation and versioning, NDA / contract coverage and the opportunity-to-project mapping.
"""

from __future__ import annotations

import hashlib
import json
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

STAGES = ("lead", "qualification", "bid_decision", "proposal", "negotiation", "won", "lost")
OPEN_STAGES = STAGES[:5]
DEFAULT_PROBABILITY = {"lead": 10, "qualification": 25, "bid_decision": 40, "proposal": 50, "negotiation": 70, "won": 100, "lost": 0}
NEEDS_BID_STAGES = ("proposal", "negotiation", "won")

BID_CRITERIA = (
    "strategic_fit", "customer_potential", "technical_feasibility", "capacity", "competence", "risk",
    "margin", "funding", "reference_value", "reuse_potential", "win_chance",
)

TWO_PLACES = Decimal("0.01")


def money(value: Any) -> Decimal:
    """Round to cents, half up. Never goes through float."""
    return Decimal(str(value or 0)).quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def format_number(kind: str, year: int, value: int) -> str:
    return f"{kind}-{year}-{value:04d}"


# ------------------------------------------------------------- pipeline


def stage_probabilities(config: dict[str, int] | None = None) -> dict[str, int]:
    out = dict(DEFAULT_PROBABILITY)
    for stage, pct in (config or {}).items():
        if stage in out and stage not in ("won", "lost"):
            out[stage] = int(pct)
    return out


def effective_probability(stage: str, manual: int | None, is_manual: bool, config: dict[str, int] | None = None) -> int:
    """Closed opportunities are certain; open ones use the manual override or the stage default."""
    if stage == "won":
        return 100
    if stage == "lost":
        return 0
    if is_manual and manual is not None:
        return int(manual)
    return stage_probabilities(config)[stage]


def weighted_value(value: Any, probability: int) -> Decimal | None:
    if value is None:
        return None
    return money(Decimal(str(value)) * Decimal(probability) / Decimal(100))


def stage_transition_error(
    current: str, new: str, lost_reason: str | None, bid_decision: str | None, converted: bool, is_admin: bool
) -> tuple[str, str, str | None] | None:
    """Return (code, message, field) when the move is not allowed, else None."""
    if new == current:
        return None
    if converted and new != "won":
        return ("ALREADY_CONVERTED", "This opportunity was already turned into a project and cannot be moved.", "stage")
    if current in ("won", "lost") and not is_admin:
        return ("REOPEN_ADMIN_ONLY", "Only administrators can reopen a closed opportunity.", "stage")
    if new == "lost" and not (lost_reason or "").strip():
        return ("LOST_REASON_REQUIRED", "A reason is required when an opportunity is lost.", "lost_reason")
    if new in NEEDS_BID_STAGES and bid_decision != "bid":
        return ("BID_DECISION_REQUIRED", "A Bid decision is required before this stage.", "stage")
    return None


def is_overdue(due: date | None, stage: str, today: date | None = None) -> bool:
    return bool(due and stage in OPEN_STAGES and due < (today or date.today()))


# ----------------------------------------------------------------- bid


def bid_score(scores: list[dict[str, Any]]) -> dict[str, Any]:
    """Weighted score 0-100 (5 = most favourable for every criterion). Informational: it never decides."""
    rated = [s for s in scores if s.get("rating")]
    total_weight = sum(int(s.get("weight") or 3) for s in rated)
    if total_weight == 0:
        return {"score": None, "complete": False, "rated": 0}
    achieved = sum(int(s["rating"]) * int(s.get("weight") or 3) for s in rated)
    score = (Decimal(achieved) / Decimal(5 * total_weight) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return {"score": score, "complete": {s["criterion"] for s in rated} >= set(BID_CRITERIA), "rated": len(rated)}


def rule_matches(rule: dict[str, Any], *, value: Any, category: str | None, risk: str | None, circle_id: Any, margin_pct: Any = None) -> bool:
    if not rule.get("active", True):
        return False
    if rule.get("category") and rule["category"] != category:
        return False
    if rule.get("risk") and rule["risk"] != risk:
        return False
    if rule.get("circle_id") and str(rule["circle_id"]) != str(circle_id):
        return False
    amount = Decimal(str(value or 0))
    if rule.get("min_value") is not None and amount < Decimal(str(rule["min_value"])):
        return False
    if rule.get("max_value") is not None and amount > Decimal(str(rule["max_value"])):
        return False
    if rule.get("min_margin_pct") is not None and margin_pct is not None and Decimal(str(margin_pct)) < Decimal(str(rule["min_margin_pct"])):
        return False
    return True


def resolve_authority(
    rules: list[dict[str, Any]], held_role_ids: set[Any], *, value: Any, category: str | None, risk: str | None, circle_id: Any, margin_pct: Any = None
) -> dict[str, Any]:
    """Who may take a decision. `unclear` means no matching rule has a staffed role - then only an
    administrator may decide, and only with a recorded note."""
    matching = [r for r in rules if rule_matches(r, value=value, category=category, risk=risk, circle_id=circle_id, margin_pct=margin_pct)]
    matching.sort(key=lambda r: (r.get("step_order", 1), str(r.get("label", ""))))
    staffed = [r for r in matching if int(r.get("holders") or 0) > 0]
    held = {str(x) for x in held_role_ids}
    authorized = any(str(r["role_id"]) in held for r in matching)
    return {"matching": matching, "unclear": not staffed, "authorized": authorized}


def approval_steps(matching: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One required, ordered step per matching rule; sequence numbers are gap-free."""
    return [
        {"step_order": i, "label": r["label"], "rule_id": r["id"], "role_id": r["role_id"]}
        for i, r in enumerate(matching, start=1)
    ]


# -------------------------------------------------------------- proposal


def line_effort_days(line: dict[str, Any]) -> Decimal:
    if line.get("line_kind") != "labor":
        return Decimal(0)
    qty = Decimal(str(line.get("quantity") or 0))
    unit = line.get("unit")
    if unit == "day":
        return qty
    if unit == "hour":
        return qty / Decimal(8)
    return Decimal(0)


def currency_error(lines: list[dict[str, Any]], currency: str, fx_rate: Any, fx_note: str | None) -> tuple[str, str] | None:
    foreign = {ln.get("currency") or currency for ln in lines} - {currency}
    if not foreign:
        return None
    if len(foreign) > 1:
        return ("MULTIPLE_CURRENCIES", "Only one foreign currency per version can be converted.")
    if fx_rate is None or Decimal(str(fx_rate)) <= 0 or not (fx_note or "").strip():
        return ("FX_RATE_REQUIRED", "Lines in another currency need an exchange rate and a note on where it comes from.")
    return None


def calc_totals(lines: list[dict[str, Any]], currency: str, fx_rate: Any = None) -> dict[str, Any]:
    """Totals in the version currency. Each line is rounded to cents before summing."""
    rate = Decimal(str(fx_rate)) if fx_rate is not None else Decimal(1)
    price = Decimal(0)
    cost = Decimal(0)
    effort = Decimal(0)
    for ln in lines:
        factor = rate if (ln.get("currency") or currency) != currency else Decimal(1)
        qty = Decimal(str(ln.get("quantity") or 0))
        price += money(money(qty * Decimal(str(ln.get("unit_price") or 0))) * factor)
        cost += money(money(qty * Decimal(str(ln.get("unit_cost") or 0))) * factor)
        effort += line_effort_days(ln)
    margin = money(price - cost)
    margin_pct = (margin / price * 100).quantize(TWO_PLACES, rounding=ROUND_HALF_UP) if price > 0 else None
    return {"price_total": money(price), "cost_total": money(cost), "margin": margin, "margin_pct": margin_pct, "effort_days": effort.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)}


def rate_for(rates: list[dict[str, Any]], role_label: str, on: date) -> dict[str, Any] | None:
    """The price-list entry valid on a date; the most recently started entry wins."""
    hits = [
        r for r in rates
        if r["role_label"].lower() == role_label.lower() and r["valid_from"] <= on and (r.get("valid_to") is None or r["valid_to"] >= on)
    ]
    return max(hits, key=lambda r: r["valid_from"]) if hits else None


def snapshot_hash(snapshot: dict[str, Any]) -> str:
    canonical = json.dumps(snapshot, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(canonical.encode()).hexdigest()


def diff_versions(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """Compare two version snapshots: changed fields, totals delta, added/removed packages and lines."""
    fields = ("summary", "scope_text", "assumptions", "exclusions", "terms", "currency", "label")
    changed = [f for f in fields if (a.get(f) or "") != (b.get(f) or "")]
    totals = {}
    for key in ("price_total", "cost_total", "effort_days"):
        old, new = Decimal(str(a.get(key) or 0)), Decimal(str(b.get(key) or 0))
        totals[key] = {"from": old, "to": new, "delta": new - old}

    def keys(snap: dict[str, Any], section: str, name: str) -> set[str]:
        return {str(x.get(name) or "") for x in snap.get(section, [])}

    return {
        "changed_fields": changed,
        "totals": totals,
        "work_packages_added": sorted(keys(b, "work_packages", "title") - keys(a, "work_packages", "title")),
        "work_packages_removed": sorted(keys(a, "work_packages", "title") - keys(b, "work_packages", "title")),
        "lines_added": sorted(keys(b, "lines", "description") - keys(a, "lines", "description")),
        "lines_removed": sorted(keys(a, "lines", "description") - keys(b, "lines", "description")),
    }


# ----------------------------------------------------- NDA and contracts


def nda_coverage(status: str, valid_from: date | None, valid_to: date | None, today: date | None = None, warn_days: int = 30) -> str:
    """none | draft | not_started | active | expiring | expired | terminated. A signed NDA is not a release for publication."""
    today = today or date.today()
    if status == "terminated":
        return "terminated"
    if status != "signed":
        return "draft"
    if valid_from and today < valid_from:
        return "not_started"
    if valid_to and today > valid_to:
        return "expired"
    if valid_to and today + timedelta(days=warn_days) >= valid_to:
        return "expiring"
    return "active"


def contract_state(status: str, valid_from: date | None, valid_to: date | None, today: date | None = None, warn_days: int = 60) -> str:
    today = today or date.today()
    if status in ("draft", "in_review", "terminated"):
        return status
    if valid_from and today < valid_from:
        return "signed"
    if valid_to and today > valid_to:
        return "expired"
    if valid_to and today + timedelta(days=warn_days) >= valid_to:
        return "expiring"
    return "active"


def reminder_dates(valid_to: date | None, notice_days: int | None, today: date | None = None, warn_days: int = 30) -> list[tuple[str, date]]:
    """(kind, due_date) pairs that are due now: expiry warning and the last day to give notice."""
    today = today or date.today()
    out: list[tuple[str, date]] = []
    if valid_to is None:
        return out
    if today <= valid_to <= today + timedelta(days=warn_days):
        out.append(("expires_soon", valid_to))
    if notice_days:
        notice_by = valid_to - timedelta(days=notice_days)
        if today <= notice_by <= today + timedelta(days=warn_days):
            out.append(("notice_deadline", notice_by))
    return out


# ----------------------------------------------- opportunity -> project


CONVERT_FIELDS = ("name", "description", "category", "start_date", "due_date", "effort_days", "budget_total", "classification")


def conversion_plan(source: dict[str, Any], existing: dict[str, Any] | None) -> list[dict[str, Any]]:
    """Compare what an opportunity would hand to a project with what the project already holds.

    New project: every field is `set`. Existing project: only empty fields are `fill`; differing values are
    `conflict` and are only overwritten when the caller explicitly asks for that field.
    """
    rows = []
    for field in CONVERT_FIELDS:
        new = source.get(field)
        if new in (None, ""):
            continue
        if existing is None:
            rows.append({"field": field, "action": "set", "new": new, "current": None})
            continue
        cur = existing.get(field)
        if cur in (None, "", 0):
            rows.append({"field": field, "action": "fill", "new": new, "current": cur})
        elif str(cur) != str(new):
            rows.append({"field": field, "action": "conflict", "new": new, "current": cur})
    return rows
