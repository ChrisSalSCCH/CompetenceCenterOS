"""Management reporting: cockpit, forecast, analytics and the commercial side of customer and project views.

Every figure is derived from the stored records. Monetary values are never added across currencies, and they
are hidden from read-only observers. Cost and margin need cost access; contract conditions need signing rights.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from routes.agreements import _signature_role
from routes.capacity import capacity_overview
from services.commercial import OPEN_STAGES, contract_state, effective_probability, is_overdue, nda_coverage, stage_probabilities, weighted_value
from services.commercial_db import has_cost_access
from services.ctx import CtxDep
from services.dbx import DbDep, err, q, q1
from services.management import build_forecast, forecast_totals, months_ahead

router = APIRouter(prefix="/api/management", tags=["management"])

STALE_DAYS = 30
EXPIRY_DAYS = 60
CLOSED = ("won", "lost")


async def _stage_cfg(db, org_id: UUID) -> dict[str, int]:
    rows = await q(db, "SELECT stage, probability FROM pipeline_stage_config WHERE organization_id = :o", o=org_id)
    return stage_probabilities({r["stage"]: int(r["probability"]) for r in rows})


def _add(target: dict[str, Decimal], currency: str, amount: Any) -> None:
    if amount is not None:
        target[currency] = target.get(currency, Decimal(0)) + Decimal(str(amount))


def _plain(d: dict[str, Decimal]) -> dict[str, float]:
    return {k: float(v) for k, v in d.items()}


async def _opportunities(db, ctx, circle_id: UUID | None, owner_id: UUID | None, category: str | None) -> list[dict]:
    return await q(
        db,
        """SELECT o.id, o.number, o.title, o.stage, o.value_amount, o.currency, o.probability, o.probability_manual, o.expected_close, o.expected_start, o.next_action, o.next_action_due,
                  o.owner_user_id, o.created_at, o.closed_at, o.category, o.risk, o.circle_id, o.project_id, o.lost_reason, o.crm_org_id, co.name AS customer_name,
                  (SELECT b.decision FROM bid_assessments b WHERE b.opportunity_id = o.id) AS bid_decision,
                  (SELECT b.authority_unclear FROM bid_assessments b WHERE b.opportunity_id = o.id) AS authority_unclear,
                  (SELECT MAX(a.occurred_at) FROM crm_activities a WHERE a.opportunity_id = o.id AND a.deleted_at IS NULL) AS last_activity,
                  EXISTS (SELECT 1 FROM contracts c WHERE c.opportunity_id = o.id AND c.deleted_at IS NULL AND c.status = 'signed') AS has_signed_contract
           FROM opportunities o JOIN crm_organizations co ON co.id = o.crm_org_id
           WHERE o.organization_id = :org AND o.deleted_at IS NULL AND (CAST(:ci AS uuid) IS NULL OR o.circle_id = CAST(:ci AS uuid))
             AND (CAST(:ow AS uuid) IS NULL OR o.owner_user_id = CAST(:ow AS uuid)) AND (CAST(:ca AS text) IS NULL OR o.category = CAST(:ca AS text))""",
        org=ctx.org_id, ci=circle_id, ow=owner_id, ca=category,
    )


def _ref(o: dict) -> dict:
    return {"id": o["id"], "number": o["number"], "title": o["title"], "customer_name": o["customer_name"]}


# ------------------------------------------------------------- cockpit


@router.get("/dashboard", summary="Management cockpit: pipeline, results, risks, contracts, projects and capacity")
async def dashboard(  # noqa: PLR0913, PLR0915 - one parameter per filter, one block per cockpit section
    ctx: CtxDep,
    db: DbDep,
    date_from: date | None = None,
    date_to: date | None = None,
    circle_id: UUID | None = None,
    owner_id: UUID | None = None,
    category: str | None = Query(default=None, max_length=20),
) -> dict:
    hide = ctx.level == "observer"
    today = date.today()
    now = datetime.now(timezone.utc)
    cfg = await _stage_cfg(db, ctx.org_id)
    opps = await _opportunities(db, ctx, circle_id, owner_id, category)
    open_opps = [o for o in opps if o["stage"] in OPEN_STAGES]

    by_stage: dict[str, dict[str, Any]] = {s: {"count": 0, "value": {}, "weighted": {}} for s in (*OPEN_STAGES, *CLOSED)}
    weighted_total: dict[str, Decimal] = {}
    for o in opps:
        b = by_stage[o["stage"]]
        b["count"] += 1
        _add(b["value"], o["currency"], o["value_amount"])
        if o["stage"] in OPEN_STAGES and o["value_amount"] is not None:
            w = weighted_value(o["value_amount"], effective_probability(o["stage"], o["probability"], o["probability_manual"], cfg)) or Decimal(0)
            _add(b["weighted"], o["currency"], w)
            _add(weighted_total, o["currency"], w)

    def in_period(o: dict) -> bool:
        closed = o["closed_at"]
        if closed is None:
            return False
        day = closed.date()
        return (date_from is None or day >= date_from) and (date_to is None or day <= date_to)

    won = [o for o in opps if o["stage"] == "won" and in_period(o)]
    lost = [o for o in opps if o["stage"] == "lost" and in_period(o)]
    won_value: dict[str, Decimal] = {}
    for o in won:
        _add(won_value, o["currency"], o["value_amount"])
    cycles = [(o["closed_at"] - o["created_at"]).days for o in won]

    stale_limit = now - timedelta(days=STALE_DAYS)
    attention = {
        "overdue_actions": [_ref(o) for o in open_opps if is_overdue(o["next_action_due"], o["stage"])],
        "overdue_decisions": [_ref(o) for o in open_opps if is_overdue(o["expected_close"], o["stage"])],
        "without_owner": [_ref(o) for o in open_opps if o["owner_user_id"] is None],
        "without_next_action": [_ref(o) for o in open_opps if not o["next_action"]],
        "stale": [_ref(o) for o in open_opps if o["created_at"] < stale_limit and (o["last_activity"] is None or o["last_activity"] < stale_limit)],
        "authority_unclear": [_ref(o) for o in opps if o["authority_unclear"] and o["bid_decision"] in ("bid", "no_bid")],
    }
    unfilled = await q(
        db,
        """SELECT dr.id, dr.label, r.name AS role_name, dr.decision_type FROM decision_rules dr JOIN roles r ON r.id = dr.role_id
           WHERE dr.organization_id = :o AND dr.deleted_at IS NULL AND dr.active
             AND NOT EXISTS (SELECT 1 FROM role_assignments ra WHERE ra.role_id = dr.role_id AND ra.deleted_at IS NULL)""",
        o=ctx.org_id,
    )

    proposals = await q(
        db,
        """SELECT p.status, COUNT(*) AS n FROM proposals p JOIN opportunities o ON o.id = p.opportunity_id AND o.deleted_at IS NULL
           WHERE p.organization_id = :org AND p.deleted_at IS NULL AND (CAST(:ci AS uuid) IS NULL OR o.circle_id = CAST(:ci AS uuid))
             AND (CAST(:ow AS uuid) IS NULL OR o.owner_user_id = CAST(:ow AS uuid)) AND (CAST(:ca AS text) IS NULL OR o.category = CAST(:ca AS text)) GROUP BY p.status""",
        org=ctx.org_id, ci=circle_id, ow=owner_id, ca=category,
    )
    awaiting = await q(
        db,
        """SELECT p.id, p.number, p.title, o.title AS opportunity_title FROM proposals p JOIN opportunities o ON o.id = p.opportunity_id AND o.deleted_at IS NULL
           WHERE p.organization_id = :o AND p.deleted_at IS NULL AND p.status = 'in_approval' ORDER BY p.updated_at LIMIT 5""",
        o=ctx.org_id,
    )

    contract_rows = await q(
        db,
        "SELECT id, number, title, status, valid_from, valid_to, value_amount, currency FROM contracts WHERE organization_id = :o AND deleted_at IS NULL",
        o=ctx.org_id,
    )
    terms_all = ctx.level == "org_admin" or await _signature_role(db, ctx)
    contract_states: dict[str, int] = defaultdict(int)
    active_value: dict[str, Decimal] = {}
    expiring = []
    for c in contract_rows:
        state = contract_state(c["status"], c["valid_from"], c["valid_to"], today, EXPIRY_DAYS)
        contract_states[state] += 1
        if state in ("active", "expiring"):
            _add(active_value, c["currency"], c["value_amount"])
        if state == "expiring":
            expiring.append({"id": c["id"], "number": c["number"], "title": c["title"], "valid_to": c["valid_to"]})
    ndas = await q(db, "SELECT status, valid_from, valid_to FROM ndas WHERE organization_id = :o AND deleted_at IS NULL", o=ctx.org_id)
    nda_states: dict[str, int] = defaultdict(int)
    for n in ndas:
        nda_states[nda_coverage(n["status"], n["valid_from"], n["valid_to"], today)] += 1

    projects = await q(
        db,
        """SELECT p.classification, p.phase, p.status, p.is_research, p.manager_id,
                  (SELECT COUNT(*) FROM project_finance_viewers v WHERE v.project_id = p.id AND v.user_id = :u) AS viewer
           FROM projects p WHERE p.organization_id = :org AND p.deleted_at IS NULL AND (CAST(:ci AS uuid) IS NULL OR p.circle_id = CAST(:ci AS uuid))
             AND (CAST(:ow AS uuid) IS NULL OR p.manager_id = CAST(:ow AS uuid)) AND (CAST(:ca AS text) IS NULL OR p.category = CAST(:ca AS text))""",
        org=ctx.org_id, u=ctx.user_id, ci=circle_id, ow=owner_id, ca=category,
    )
    finance = await q(
        db,
        """SELECT f.currency, SUM(f.budget_total) AS budget, SUM(f.costs_to_date) AS costs, SUM(f.budget_funding) AS funding, COUNT(*) AS n
           FROM project_finance f JOIN projects p ON p.id = f.project_id AND p.deleted_at IS NULL
           WHERE f.organization_id = :org AND p.phase NOT IN ('completed','archived') AND (CAST(:ci AS uuid) IS NULL OR p.circle_id = CAST(:ci AS uuid))
             AND (CAST(:adm AS boolean) OR p.manager_id = :u OR EXISTS (SELECT 1 FROM project_finance_viewers v WHERE v.project_id = p.id AND v.user_id = :u))
           GROUP BY f.currency""",
        org=ctx.org_id, u=ctx.user_id, ci=circle_id, adm=ctx.level == "org_admin",
    )
    phases: dict[str, int] = defaultdict(int)
    for p in projects:
        phases[p["phase"]] += 1

    cap = await capacity_overview(db, ctx, 8)
    return {
        "filters": {"date_from": date_from, "date_to": date_to, "circle_id": circle_id, "owner_id": owner_id, "category": category},
        "money_hidden": hide,
        "pipeline": {
            "open_count": len(open_opps),
            "weighted": None if hide else _plain(weighted_total),
            "by_stage": [{"stage": s, "count": b["count"], "value": None if hide else _plain(b["value"]), "weighted": None if hide else _plain(b["weighted"])} for s, b in by_stage.items()],
        },
        "results": {
            "won": len(won), "lost": len(lost), "won_value": None if hide else _plain(won_value),
            "win_rate": round(len(won) / (len(won) + len(lost)) * 100, 1) if won or lost else None,
            "avg_cycle_days": round(sum(cycles) / len(cycles), 1) if cycles else None,
        },
        "attention": {k: {"count": len(v), "items": v[:5]} for k, v in attention.items()},
        "unfilled_decision_roles": unfilled,
        "proposals": {"by_status": {r["status"]: int(r["n"]) for r in proposals}, "awaiting_approval": awaiting},
        "contracts": {
            "by_state": dict(contract_states), "expiring": expiring[:5], "active_value": _plain(active_value) if terms_all else None,
            "conditions_visible": bool(terms_all),
        },
        "ndas": dict(nda_states),
        "projects": {
            "by_phase": dict(phases), "customer_active": sum(1 for p in projects if p["classification"] == "customer" and p["phase"] not in ("completed", "archived")),
            "internal_active": sum(1 for p in projects if p["classification"] == "internal" and p["phase"] not in ("completed", "archived")),
            "research": sum(1 for p in projects if p["is_research"]),
            "finance": None if hide else [{"currency": f["currency"], "projects": int(f["n"]), "budget": float(f["budget"] or 0), "costs": float(f["costs"] or 0), "funding": float(f["funding"] or 0)} for f in finance],
        },
        "capacity": {"overloaded_people": cap["overloaded_people"], "people_without_capacity": cap["people_without_capacity"], "average_utilization": cap["average_utilization"]},
    }


# ------------------------------------------------------------ forecast


@router.get("/forecast", summary="Revenue forecast per currency: secured, weighted, planned and hypothetical", responses={403: {"description": "Observers see no monetary values"}})
async def forecast(ctx: CtxDep, db: DbDep, months: int = Query(default=6, ge=1, le=24), currency: str | None = Query(default=None, pattern=r"^[A-Z]{3}$")) -> dict:
    if ctx.level == "observer":
        raise err(403, "MONEY_HIDDEN", "Read-only observers do not see monetary values.")
    today = date.today()
    cfg = await _stage_cfg(db, ctx.org_id)
    keys = months_ahead(today, months)
    terms_all = ctx.level == "org_admin" or await _signature_role(db, ctx)
    opps = [o for o in await _opportunities(db, ctx, None, None, None) if currency is None or o["currency"] == currency]
    milestones = []
    if terms_all:
        milestones = await q(
            db,
            """SELECT m.due_date, m.amount, m.currency, m.status FROM contract_milestones m JOIN contracts c ON c.id = m.contract_id AND c.deleted_at IS NULL AND c.status = 'signed'
               WHERE m.organization_id = :o AND m.status <> 'paid'""",
            o=ctx.org_id,
        )
        milestones = [m for m in milestones if currency is None or m["currency"] == currency]
    result = build_forecast(milestones, opps, keys, cfg, today)
    totals = forecast_totals(result)
    return {
        "months": [*keys, "undated"],
        "currencies": {
            cur: {
                "categories": {cat: {m: float(v) for m, v in buckets.items()} for cat, buckets in cats.items()},
                "totals": {cat: float(v) for cat, v in totals[cur].items()},
            }
            for cur, cats in result.items()
        },
        "secured_hidden": not terms_all,
        "assumptions": [
            "secured: payment milestones of signed contracts that are not paid yet; overdue ones count in the current month.",
            "weighted: open opportunities, value x probability, in the month of the expected decision.",
            "planned: won opportunities without a signed contract, at full value.",
            "hypothetical: the part of open opportunities that is not in 'weighted' (value x (1 - probability)). It is never counted as certain.",
            "Currencies are never converted or added together.",
            "Project budgets are not added: they would count the same revenue twice.",
        ],
        "sources": {"opportunities": len(opps), "milestones": len(milestones)},
        "generated_at": datetime.now(timezone.utc),
    }


# ----------------------------------------------------------- analytics


@router.get("/analytics", summary="Win rates, customers, industries, technologies, lost reasons and margin")
async def analytics(ctx: CtxDep, db: DbDep) -> dict:
    hide = ctx.level == "observer"
    cost_ok = await has_cost_access(db, ctx)
    terms_all = ctx.level == "org_admin" or await _signature_role(db, ctx)
    opps = await _opportunities(db, ctx, None, None, None)

    def rate(group: list[dict]) -> dict[str, Any]:
        won = [o for o in group if o["stage"] == "won"]
        lost = [o for o in group if o["stage"] == "lost"]
        value: dict[str, Decimal] = {}
        for o in won:
            _add(value, o["currency"], o["value_amount"])
        return {"won": len(won), "lost": len(lost), "open": len(group) - len(won) - len(lost), "win_rate": round(len(won) / (len(won) + len(lost)) * 100, 1) if won or lost else None, "won_value": None if hide else _plain(value)}

    by_category = defaultdict(list)
    by_customer = defaultdict(list)
    for o in opps:
        by_category[o["category"]].append(o)
        by_customer[(o["crm_org_id"], o["customer_name"])].append(o)
    customers = [{"crm_org_id": k[0], "name": k[1], "opportunities": len(v), **rate(v)} for k, v in by_customer.items()]
    customers.sort(key=lambda c: (-c["won"], -c["opportunities"], c["name"]))

    industries = await q(
        db,
        """SELECT COALESCE(i.name, '-') AS industry, COUNT(DISTINCT po.project_id) AS projects, COUNT(DISTINCT o.id) AS opportunities
           FROM crm_organizations co LEFT JOIN catalog_entries i ON i.id = co.industry_entry_id
           LEFT JOIN project_orgs po ON po.crm_org_id = co.id AND po.relation = 'customer' LEFT JOIN opportunities o ON o.crm_org_id = co.id AND o.deleted_at IS NULL
           WHERE co.organization_id = :o AND co.deleted_at IS NULL GROUP BY i.name ORDER BY projects DESC, opportunities DESC""",
        o=ctx.org_id,
    )
    technologies = await q(
        db,
        """SELECT e.id, e.name, (SELECT COUNT(*) FROM project_catalog_links l JOIN projects p ON p.id = l.project_id AND p.deleted_at IS NULL WHERE l.entry_id = e.id) AS projects,
                  (SELECT COUNT(*) FROM opportunity_catalog_links l JOIN opportunities o ON o.id = l.opportunity_id AND o.deleted_at IS NULL WHERE l.entry_id = e.id) AS opportunities
           FROM catalog_entries e WHERE e.organization_id = :o AND e.deleted_at IS NULL AND e.kind = 'technology' ORDER BY projects DESC, opportunities DESC, e.name LIMIT 15""",
        o=ctx.org_id,
    )
    reasons: dict[str, int] = defaultdict(int)
    for o in opps:
        if o["stage"] == "lost" and o["lost_reason"]:
            reasons[o["lost_reason"].strip().lower()[:120]] += 1
    closed_won = [(o["closed_at"] - o["created_at"]).days for o in opps if o["stage"] == "won" and o["closed_at"]]
    closed_lost = [(o["closed_at"] - o["created_at"]).days for o in opps if o["stage"] == "lost" and o["closed_at"]]
    margin = None
    if cost_ok:
        margin = await q(
            db,
            """SELECT o.category, ROUND(AVG(v.margin_pct), 1) AS avg_margin_pct, COUNT(*) AS versions FROM proposal_versions v JOIN proposals p ON p.id = v.proposal_id AND p.deleted_at IS NULL
               JOIN opportunities o ON o.id = p.opportunity_id AND o.deleted_at IS NULL WHERE v.organization_id = :o AND v.status IN ('approved','submitted') AND v.margin_pct IS NOT NULL GROUP BY o.category""",
            o=ctx.org_id,
        )
    proposals = await q(db, "SELECT status, COUNT(*) AS n FROM proposals WHERE organization_id = :o AND deleted_at IS NULL GROUP BY status", o=ctx.org_id)
    contract_value = None
    if terms_all:
        contract_value = await q(
            db,
            """SELECT co.name AS customer, c.currency, SUM(c.value_amount) AS value FROM contracts c JOIN crm_organizations co ON co.id = c.crm_org_id
               WHERE c.organization_id = :o AND c.deleted_at IS NULL AND c.status = 'signed' GROUP BY co.name, c.currency ORDER BY value DESC NULLS LAST LIMIT 10""",
            o=ctx.org_id,
        )
    return {
        "money_hidden": hide,
        "by_category": [{"category": k, **rate(v)} for k, v in sorted(by_category.items())],
        "customers": customers[:15],
        "industries": industries,
        "technologies": technologies,
        "lost_reasons": [{"reason": k, "count": v} for k, v in sorted(reasons.items(), key=lambda kv: -kv[1])[:10]],
        "cycle_days": {"won": round(sum(closed_won) / len(closed_won), 1) if closed_won else None, "lost": round(sum(closed_lost) / len(closed_lost), 1) if closed_lost else None},
        "proposals": {r["status"]: int(r["n"]) for r in proposals},
        "margin_by_category": [{"category": m["category"], "avg_margin_pct": float(m["avg_margin_pct"]), "versions": int(m["versions"])} for m in margin] if margin is not None else None,
        "contract_value_by_customer": [{"customer": c["customer"], "currency": c["currency"], "value": float(c["value"] or 0)} for c in contract_value] if contract_value is not None else None,
    }


# --------------------------------------------------- 360 degree sections


@router.get("/customers/{crm_org_id}/commercial", summary="Commercial view of a customer: opportunities, proposals, NDAs, contracts", responses={404: {"description": "Customer not found"}})
async def customer_commercial(crm_org_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    org = await q1(db, "SELECT id, name FROM crm_organizations WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=crm_org_id, o=ctx.org_id)
    if org is None:
        raise err(404, "CRM_ORG_NOT_FOUND", "Organization not found.")
    hide = ctx.level == "observer"
    cfg = await _stage_cfg(db, ctx.org_id)
    terms_all = ctx.level == "org_admin" or await _signature_role(db, ctx)
    opps = [o for o in await _opportunities(db, ctx, None, None, None) if o["crm_org_id"] == crm_org_id]
    weighted: dict[str, Decimal] = {}
    won_value: dict[str, Decimal] = {}
    for o in opps:
        if o["stage"] in OPEN_STAGES and o["value_amount"] is not None:
            _add(weighted, o["currency"], weighted_value(o["value_amount"], effective_probability(o["stage"], o["probability"], o["probability_manual"], cfg)))
        if o["stage"] == "won":
            _add(won_value, o["currency"], o["value_amount"])
    proposals = await q(
        db,
        """SELECT p.id, p.number, p.title, p.status, v.price_total, v.currency FROM proposals p JOIN opportunities o ON o.id = p.opportunity_id AND o.deleted_at IS NULL
           LEFT JOIN proposal_versions v ON v.id = p.current_version_id WHERE p.organization_id = :org AND p.deleted_at IS NULL AND o.crm_org_id = :c ORDER BY p.created_at DESC""",
        org=ctx.org_id, c=crm_org_id,
    )
    ndas = await q(db, "SELECT id, number, title, status, valid_from, valid_to FROM ndas WHERE organization_id = :o AND deleted_at IS NULL AND crm_org_id = :c ORDER BY valid_to NULLS LAST", o=ctx.org_id, c=crm_org_id)
    contracts = await q(db, "SELECT id, number, title, status, valid_from, valid_to, value_amount, currency FROM contracts WHERE organization_id = :o AND deleted_at IS NULL AND crm_org_id = :c ORDER BY valid_to NULLS LAST", o=ctx.org_id, c=crm_org_id)
    docs = await q1(db, "SELECT COUNT(*) AS n FROM documents WHERE organization_id = :o AND deleted_at IS NULL AND entity_type = 'crm_organization' AND entity_id = :c AND confidentiality = 'internal'", o=ctx.org_id, c=crm_org_id)
    nda_states = [nda_coverage(n["status"], n["valid_from"], n["valid_to"]) for n in ndas]
    for p in proposals:
        if hide:
            p["price_total"] = None
    for c in contracts:
        c["state"] = contract_state(c["status"], c["valid_from"], c["valid_to"])
        if not terms_all:
            c["value_amount"] = None
    for n in ndas:
        n["coverage"] = nda_coverage(n["status"], n["valid_from"], n["valid_to"])
    return {
        "customer": org,
        "opportunities": [
            {k: (None if hide and k == "value_amount" else o[k]) for k in ("id", "number", "title", "stage", "value_amount", "currency", "expected_close", "owner_user_id", "bid_decision")}
            for o in sorted(opps, key=lambda x: x["created_at"], reverse=True)
        ],
        "weighted_pipeline": None if hide else _plain(weighted), "won_value": None if hide else _plain(won_value),
        "proposals": proposals, "ndas": ndas, "contracts": contracts, "documents": int(docs["n"]) if docs else 0,
        "nda_state": min(nda_states, key=lambda s: ["active", "expiring", "not_started", "expired", "draft", "terminated"].index(s)) if nda_states else "none",
        "conditions_visible": bool(terms_all),
    }


@router.get("/projects/{project_id}/commercial", summary="Commercial view of a project: origin, proposals, contracts, NDAs, payment milestones, planned load", responses={404: {"description": "Project not found"}})
async def project_commercial(project_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    project = await q1(db, "SELECT id, name, source_opportunity_id, effort_days FROM projects WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=project_id, o=ctx.org_id)
    if project is None:
        raise err(404, "PROJECT_NOT_FOUND", "Project not found.")
    hide = ctx.level == "observer"
    terms_all = ctx.level == "org_admin" or await _signature_role(db, ctx)
    opp = await q1(db, "SELECT id, number, title, stage FROM opportunities WHERE id = :i AND deleted_at IS NULL", i=project["source_opportunity_id"]) if project["source_opportunity_id"] else None
    proposals = await q(
        db,
        """SELECT p.id, p.number, p.title, p.status, v.price_total, v.currency FROM proposals p LEFT JOIN proposal_versions v ON v.id = p.current_version_id
           WHERE p.opportunity_id = :op AND p.deleted_at IS NULL ORDER BY p.created_at""",
        op=project["source_opportunity_id"],
    ) if opp else []
    contracts = await q(
        db,
        """SELECT c.id, c.number, c.title, c.status, c.valid_from, c.valid_to, c.value_amount, c.currency FROM contract_projects cp JOIN contracts c ON c.id = cp.contract_id AND c.deleted_at IS NULL
           WHERE cp.project_id = :p ORDER BY c.number""",
        p=project_id,
    )
    ndas = await q(
        db,
        """SELECT n.id, n.number, n.title, n.status, n.valid_from, n.valid_to FROM nda_links l JOIN ndas n ON n.id = l.nda_id AND n.deleted_at IS NULL WHERE l.project_id = :p ORDER BY n.number""",
        p=project_id,
    )
    milestones = await q(
        db,
        """SELECT m.id, m.title, m.due_date, m.amount, m.currency, m.status, c.number AS contract_number FROM contract_milestones m JOIN contracts c ON c.id = m.contract_id AND c.deleted_at IS NULL
           WHERE m.project_id = :p OR m.contract_id IN (SELECT contract_id FROM contract_projects WHERE project_id = :p) ORDER BY m.due_date NULLS LAST""",
        p=project_id,
    )
    allocated = await q1(db, "SELECT COALESCE(SUM(hours_per_week * (GREATEST(end_date - start_date, 0) + 1) / 7.0), 0) AS hours FROM project_allocations WHERE project_id = :p AND deleted_at IS NULL", p=project_id)
    for p in proposals:
        if hide:
            p["price_total"] = None
    for c in contracts:
        c["state"] = contract_state(c["status"], c["valid_from"], c["valid_to"])
        if not terms_all:
            c["value_amount"] = None
    for n in ndas:
        n["coverage"] = nda_coverage(n["status"], n["valid_from"], n["valid_to"])
    if not terms_all:
        for m in milestones:
            m["amount"] = None
    planned_hours = float(allocated["hours"]) if allocated else 0.0
    return {
        "origin": opp, "proposals": proposals, "contracts": contracts, "ndas": ndas, "payment_milestones": milestones,
        "effort": {"estimated_days": float(project["effort_days"]) if project["effort_days"] is not None else None, "allocated_days": round(planned_hours / 8, 1)},
        "conditions_visible": bool(terms_all),
    }


@router.get("/summary", summary="Structured JSON report: cockpit, forecast and data quality in one document")
async def summary(ctx: CtxDep, db: DbDep) -> dict:
    from routes.dataquality import quality_counts

    report: dict[str, Any] = {"generated_at": datetime.now(timezone.utc), "generated_by": ctx.name, "organization_id": ctx.org_id}
    report["cockpit"] = await dashboard(ctx, db, None, None, None, None, None)
    report["forecast"] = None if ctx.level == "observer" else await forecast(ctx, db, 6, None)
    report["data_quality"] = await quality_counts(db, ctx)
    return report
