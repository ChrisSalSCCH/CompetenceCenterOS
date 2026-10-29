"""Pure business rules of the project portfolio (no database access, unit-testable)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

KNOWLEDGE_SECTIONS = ("business_context", "solution", "challenges", "results", "reuse", "architecture", "ai_usage")
VERIFICATIONS = ("unverified", "verified", "ai_draft", "approved")
COMM_FLAGS = ("allow_name", "allow_logo", "allow_images", "allow_description", "allow_results")


def _num(value: Any) -> Decimal | None:
    return None if value is None else Decimal(str(value))


def finance_metrics(fin: dict[str, Any] | None, today: date | None = None) -> dict[str, Any]:
    """Values derived from the entered finance data. Every derived value is listed in `calculated`."""
    today = today or date.today()
    fin = fin or {}
    total, funding, costs = _num(fin.get("budget_total")), _num(fin.get("budget_funding")), _num(fin.get("costs_to_date"))
    out: dict[str, Any] = {"funding_rate": None, "budget_remaining": None, "budget_used_pct": None, "report_overdue": False}
    if total and total > 0:
        if funding is not None:
            out["funding_rate"] = round(float(funding / total) * 100, 1)
        if costs is not None:
            out["budget_remaining"] = total - costs
            out["budget_used_pct"] = round(float(costs / total) * 100, 1)
    due = fin.get("next_report_due")
    out["report_overdue"] = bool(due and due < today and fin.get("reporting_cycle", "none") != "none")
    return out


CALCULATED_FIELDS = ["funding_rate", "budget_remaining", "budget_used_pct", "report_overdue"]


def normalize_communication(data: dict[str, Any]) -> dict[str, Any]:
    """A project that is not a released reference must not carry any usage permission."""
    out = dict(data)
    if not out.get("reference_allowed"):
        for flag in COMM_FLAGS:
            out[flag] = False
    return out


def customer_rule_violated(classification: str, customer_org_count: int) -> bool:
    """Customer projects need at least one linked customer organization."""
    return classification == "customer" and customer_org_count < 1


def can_set_verification(level: str, is_manager: bool, requested: str) -> bool:
    """Who may set which verification state."""
    if requested in ("unverified", "ai_draft"):
        return level != "observer"
    if requested == "verified":
        return level == "org_admin" or (level == "member" and is_manager)
    if requested == "approved":
        return level == "org_admin" or is_manager
    return False


def knowledge_completeness(sections: list[dict[str, Any]], ai_relevant: bool, customer: bool) -> dict[str, Any]:
    """Share of relevant sections that are filled, and how many of those are verified."""
    relevant = [s for s in KNOWLEDGE_SECTIONS if s != "ai_usage" or ai_relevant]
    if not customer:
        relevant = [s for s in relevant if s != "business_context"]
    by_key = {s["section"]: s for s in sections}
    filled = [s for s in relevant if (by_key.get(s) or {}).get("content", "").strip()]
    verified = [s for s in filled if by_key[s]["verification"] in ("verified", "approved")]
    return {"relevant": len(relevant), "filled": len(filled), "verified": len(verified), "calculated": True}


def public_reference(project: dict[str, Any], comm: dict[str, Any], industry: str | None) -> dict[str, Any]:
    """Only the content that was explicitly released may leave the organization."""
    allowed_name = bool(comm.get("allow_name"))
    return {
        "project_id": project["id"],
        "title": project["name"] if allowed_name else f"Confidential project{' (' + industry + ')' if industry else ''}",
        "name_released": allowed_name,
        "description": project.get("description") if comm.get("allow_description") else None,
        "logo_released": bool(comm.get("allow_logo")),
        "images_released": bool(comm.get("allow_images")),
        "results_released": bool(comm.get("allow_results")),
        "industry": industry,
    }
