"""Commercial pipeline: opportunities, stage moves, weighted pipeline and the lead-to-project chain."""

from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from services.commercial import (
    DEFAULT_PROBABILITY,
    OPEN_STAGES,
    STAGES,
    effective_probability,
    is_overdue,
    stage_probabilities,
    stage_transition_error,
    weighted_value,
)
from services.commercial_db import (
    can_edit_opp,
    can_see_cost,
    check_crm_org,
    check_member,
    get_opp,
    next_number,
    require_edit_opp,
    strip_money,
)
from services.ctx import CtxDep, require_admin, require_circle, require_write
from services.dbx import DbDep, err, q, q1, set_clause, x
from services.events import audit, notify

router = APIRouter(prefix="/api/commercial", tags=["commercial"])

Stage = Literal["lead", "qualification", "bid_decision", "proposal", "negotiation", "won", "lost"]
Category = Literal["research", "development", "consulting", "innovation", "operations", "other"]
Risk = Literal["low", "medium", "high"]
Money = Decimal
MAX_MONEY = Decimal("999999999999")
CURRENCY = r"^[A-Z]{3}$"


class OppCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=10000)
    crm_org_id: UUID
    circle_id: UUID | None = None
    category: Category = "other"
    source: str | None = Field(default=None, max_length=40)
    risk: Risk = "medium"
    value_amount: Money | None = Field(default=None, ge=0, le=MAX_MONEY)
    currency: str = Field(default="EUR", pattern=CURRENCY)
    probability: int | None = Field(default=None, ge=0, le=100)
    effort_days: Money | None = Field(default=None, ge=0, le=Decimal("100000"))
    expected_close: date | None = None
    expected_start: date | None = None
    expected_end: date | None = None
    owner_user_id: UUID | None = None
    next_action: str | None = Field(default=None, max_length=300)
    next_action_due: date | None = None


class OppUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    crm_org_id: UUID | None = None
    circle_id: UUID | None = None
    category: Category | None = None
    source: str | None = Field(default=None, max_length=40)
    risk: Risk | None = None
    value_amount: Money | None = Field(default=None, ge=0, le=MAX_MONEY)
    currency: str | None = Field(default=None, pattern=CURRENCY)
    probability: int | None = Field(default=None, ge=0, le=100)
    effort_days: Money | None = Field(default=None, ge=0, le=Decimal("100000"))
    expected_close: date | None = None
    expected_start: date | None = None
    expected_end: date | None = None
    owner_user_id: UUID | None = None
    next_action: str | None = Field(default=None, max_length=300)
    next_action_due: date | None = None


class StageBody(BaseModel):
    stage: Stage
    lost_reason: str | None = Field(default=None, max_length=2000)


class ContactIn(BaseModel):
    contact_id: UUID
    contact_role: str | None = Field(default=None, max_length=60)


class TeamIn(BaseModel):
    user_id: UUID
    role_id: UUID | None = None
    team_role: str | None = Field(default=None, max_length=60)


class LinksBody(BaseModel):
    contacts: list[ContactIn] | None = Field(default=None, max_length=40)
    entry_ids: list[UUID] | None = Field(default=None, max_length=60)
    reference_project_ids: list[UUID] | None = Field(default=None, max_length=30)
    team: list[TeamIn] | None = Field(default=None, max_length=30)


class StageConfigBody(BaseModel):
    probabilities: dict[Stage, int]


# ---------------------------------------------------------------- helpers


async def _stage_config(db, org_id: UUID) -> dict[str, int]:
    rows = await q(db, "SELECT stage, probability FROM pipeline_stage_config WHERE organization_id = :o", o=org_id)
    return {r["stage"]: int(r["probability"]) for r in rows}


def _decorate(row: dict, cfg: dict[str, int], ctx) -> dict:
    prob = effective_probability(row["stage"], row.get("probability"), row.get("probability_manual", False), cfg)
    row["effective_probability"] = prob
    row["weighted_value"] = weighted_value(row.get("value_amount"), prob)
    row["action_overdue"] = is_overdue(row.get("next_action_due"), row["stage"])
    row["close_overdue"] = is_overdue(row.get("expected_close"), row["stage"])
    return strip_money(row, ctx)


async def _check_contacts(db, ctx, ids: list[UUID]) -> None:
    for cid in set(ids):
        row = await q1(db, "SELECT 1 AS ok FROM crm_contacts WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=cid, o=ctx.org_id)
        if row is None:
            raise err(404, "CONTACT_NOT_FOUND", "Contact not found.", "contacts")


async def _check_entries(db, ctx, ids: list[UUID]) -> None:
    for eid in set(ids):
        row = await q1(db, "SELECT 1 AS ok FROM catalog_entries WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=eid, o=ctx.org_id)
        if row is None:
            raise err(404, "CATALOG_ENTRY_NOT_FOUND", "Catalog entry not found.", "entry_ids")


async def _check_projects(db, ctx, ids: list[UUID]) -> None:
    for pid in set(ids):
        row = await q1(db, "SELECT 1 AS ok FROM projects WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=pid, o=ctx.org_id)
        if row is None:
            raise err(404, "PROJECT_NOT_FOUND", "Project not found.", "reference_project_ids")


def _check_dates(start: date | None, end: date | None) -> None:
    if start and end and end < start:
        raise err(422, "INVALID_DATES", "The end date cannot be before the start date.", "expected_end")


# ------------------------------------------------------------------- list


@router.get("/opportunities", summary="List and filter opportunities")
async def list_opportunities(  # noqa: PLR0913 - one parameter per filter
    ctx: CtxDep,
    db: DbDep,
    search: str | None = Query(default=None, max_length=100),
    stage: Stage | None = None,
    open_only: bool = False,
    owner_id: UUID | None = None,
    crm_org_id: UUID | None = None,
    category: Category | None = None,
    overdue: bool = False,
) -> list[dict]:
    where = ["o.organization_id = :org", "o.deleted_at IS NULL"]
    params: dict[str, Any] = {"org": ctx.org_id}
    for col, val in (("stage", stage), ("owner_user_id", owner_id), ("crm_org_id", crm_org_id), ("category", category)):
        if val is not None:
            where.append(f"o.{col} = :{col}")
            params[col] = val
    if open_only:
        where.append("o.stage IN ('lead','qualification','bid_decision','proposal','negotiation')")
    if overdue:
        where.append("o.stage IN ('lead','qualification','bid_decision','proposal','negotiation') AND (o.next_action_due < CURRENT_DATE OR o.expected_close < CURRENT_DATE)")
    if search:
        where.append("(o.title ILIKE :s OR o.number ILIKE :s OR co.name ILIKE :s)")
        params["s"] = f"%{search.strip()}%"
    rows = await q(
        db,
        f"""SELECT o.id, o.number, o.title, o.stage, o.category, o.risk, o.value_amount, o.currency, o.probability, o.probability_manual,
                   o.expected_close, o.next_action, o.next_action_due, o.crm_org_id, co.name AS customer_name, o.owner_user_id, u.display_name AS owner_name,
                   o.project_id, o.updated_at, o.stage_changed_at,
                   (SELECT b.decision FROM bid_assessments b WHERE b.opportunity_id = o.id) AS bid_decision,
                   (SELECT COUNT(*) FROM proposals p WHERE p.opportunity_id = o.id AND p.deleted_at IS NULL) AS proposal_count
            FROM opportunities o JOIN crm_organizations co ON co.id = o.crm_org_id LEFT JOIN users u ON u.id = o.owner_user_id
            WHERE {' AND '.join(where)} ORDER BY o.expected_close NULLS LAST, o.created_at DESC LIMIT 500""",  # noqa: S608 - constants only
        **params,
    )
    cfg = await _stage_config(db, ctx.org_id)
    return [_decorate(r, cfg, ctx) for r in rows]


# --------------------------------------------------------------- pipeline


@router.get("/pipeline", summary="Open pipeline per stage: counts, value and weighted value per currency")
async def pipeline(ctx: CtxDep, db: DbDep) -> dict:
    cfg = await _stage_config(db, ctx.org_id)
    probs = stage_probabilities(cfg)
    rows = await q(
        db,
        """SELECT stage, value_amount, currency, probability, probability_manual, next_action_due, expected_close, created_at, closed_at
           FROM opportunities WHERE organization_id = :o AND deleted_at IS NULL""",
        o=ctx.org_id,
    )
    stages: dict[str, dict[str, Any]] = {s: {"stage": s, "count": 0, "overdue": 0, "value": defaultdict(Decimal), "weighted": defaultdict(Decimal)} for s in STAGES}
    for r in rows:
        bucket = stages[r["stage"]]
        bucket["count"] += 1
        if is_overdue(r["next_action_due"], r["stage"]) or is_overdue(r["expected_close"], r["stage"]):
            bucket["overdue"] += 1
        if r["value_amount"] is not None:
            prob = effective_probability(r["stage"], r["probability"], r["probability_manual"], cfg)
            bucket["value"][r["currency"]] += Decimal(str(r["value_amount"]))
            bucket["weighted"][r["currency"]] += weighted_value(r["value_amount"], prob) or Decimal(0)
    hide = ctx.level == "observer"
    out = []
    for s in STAGES:
        b = stages[s]
        out.append({
            "stage": s, "count": b["count"], "overdue": b["overdue"], "probability": probs[s],
            "value": None if hide else dict(b["value"]), "weighted": None if hide else dict(b["weighted"]),
        })
    open_rows = [r for r in rows if r["stage"] in OPEN_STAGES]
    won = sum(1 for r in rows if r["stage"] == "won")
    lost = sum(1 for r in rows if r["stage"] == "lost")
    return {
        "stages": out,
        "open_count": len(open_rows),
        "overdue_count": sum(1 for r in open_rows if is_overdue(r["next_action_due"], r["stage"]) or is_overdue(r["expected_close"], r["stage"])),
        "win_rate": round(won / (won + lost) * 100, 1) if won + lost else None,
        "defaults": DEFAULT_PROBABILITY,
        "money_hidden": hide,
    }


@router.get("/stage-config", summary="Probability per pipeline stage")
async def get_stage_config(ctx: CtxDep, db: DbDep) -> dict:
    cfg = await _stage_config(db, ctx.org_id)
    return {"probabilities": stage_probabilities(cfg), "defaults": DEFAULT_PROBABILITY}


@router.put("/stage-config", summary="Set the default probability per stage - administrators only")
async def set_stage_config(body: StageConfigBody, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    for stage, pct in body.probabilities.items():
        if stage in ("won", "lost"):
            continue
        if not 0 <= pct <= 100:
            raise err(422, "VALIDATION_ERROR", "A probability must be between 0 and 100.", "probabilities")
        await x(
            db,
            """INSERT INTO pipeline_stage_config (organization_id, stage, probability, created_by, updated_by) VALUES (:o, :s, :p, :u, :u)
               ON CONFLICT (organization_id, stage) DO UPDATE SET probability = EXCLUDED.probability, updated_at = NOW(), updated_by = EXCLUDED.updated_by""",
            o=ctx.org_id, s=stage, p=pct, u=ctx.user_id,
        )
    await audit(db, ctx, "pipeline.config_changed", "pipeline", None, "Stage probabilities changed")
    await db.commit()
    return {"ok": True}


# ----------------------------------------------------------------- create


@router.post("/opportunities", summary="Create an opportunity", responses={404: {"description": "Customer, circle or owner not found"}, 422: {"description": "Invalid dates"}})
async def create_opportunity(body: OppCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    await check_crm_org(db, ctx, body.crm_org_id)
    await check_member(db, ctx, body.owner_user_id, "owner_user_id")
    if body.circle_id:
        await require_circle(db, ctx, body.circle_id)
    _check_dates(body.expected_start, body.expected_end)
    number = await next_number(db, ctx.org_id, "OPP")
    owner = body.owner_user_id or ctx.user_id
    row = await q1(
        db,
        """INSERT INTO opportunities (organization_id, number, title, description, crm_org_id, circle_id, category, source, risk, value_amount, currency,
                                      probability, probability_manual, effort_days, expected_close, expected_start, expected_end, owner_user_id,
                                      next_action, next_action_due, created_by, updated_by)
           VALUES (:o, :n, :t, :d, :c, :ci, :ca, :so, :ri, :v, :cu, :p, :pm, :e, :ec, :es, :ee, :ow, :na, :nd, :u, :u) RETURNING id""",
        o=ctx.org_id, n=number, t=body.title.strip(), d=body.description, c=body.crm_org_id, ci=body.circle_id, ca=body.category, so=body.source, ri=body.risk,
        v=body.value_amount, cu=body.currency, p=body.probability, pm=body.probability is not None, e=body.effort_days, ec=body.expected_close,
        es=body.expected_start, ee=body.expected_end, ow=owner, na=body.next_action, nd=body.next_action_due, u=ctx.user_id,
    )
    await audit(db, ctx, "opportunity.created", "opportunity", row["id"], f"{number} {body.title}", {"stage": "lead"})
    await db.commit()
    return {"id": row["id"], "number": number}


# ----------------------------------------------------------------- detail


@router.get("/opportunities/{opp_id}", summary="Opportunity detail with team, bid, proposals, agreements and activities", responses={404: {"description": "Opportunity not found"}})
async def opportunity_detail(opp_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    opp = await get_opp(db, ctx, opp_id)
    cfg = await _stage_config(db, ctx.org_id)
    base = await q1(
        db,
        """SELECT o.*, co.name AS customer_name, u.display_name AS owner_name, c.name AS circle_name, p.name AS project_name
           FROM opportunities o JOIN crm_organizations co ON co.id = o.crm_org_id LEFT JOIN users u ON u.id = o.owner_user_id
           LEFT JOIN circles c ON c.id = o.circle_id LEFT JOIN projects p ON p.id = o.project_id AND p.deleted_at IS NULL WHERE o.id = :i""",
        i=opp_id,
    )
    contacts = await q(
        db,
        """SELECT c.id, c.first_name, c.last_name, c.job_title, oc.contact_role FROM opportunity_contacts oc
           JOIN crm_contacts c ON c.id = oc.contact_id AND c.deleted_at IS NULL WHERE oc.opportunity_id = :i ORDER BY c.last_name""",
        i=opp_id,
    )
    entries = await q(
        db,
        """SELECT e.id, e.kind, e.name FROM opportunity_catalog_links l JOIN catalog_entries e ON e.id = l.entry_id AND e.deleted_at IS NULL
           WHERE l.opportunity_id = :i ORDER BY e.kind, e.name""",
        i=opp_id,
    )
    references = await q(
        db,
        "SELECT p.id, p.name FROM opportunity_references r JOIN projects p ON p.id = r.project_id AND p.deleted_at IS NULL WHERE r.opportunity_id = :i ORDER BY p.name",
        i=opp_id,
    )
    team = await q(
        db,
        """SELECT t.user_id, u.display_name AS name, t.role_id, r.name AS role_name, t.team_role FROM opportunity_team t
           JOIN users u ON u.id = t.user_id LEFT JOIN roles r ON r.id = t.role_id WHERE t.opportunity_id = :i ORDER BY u.display_name""",
        i=opp_id,
    )
    scoped = await q(
        db,
        """SELECT s.id AS scope_id, u.id AS user_id, u.display_name AS name, r.id AS role_id, r.name AS role_name, s.scope_type
           FROM crm_role_scopes s JOIN role_assignments ra ON ra.id = s.role_assignment_id AND ra.deleted_at IS NULL
           JOIN roles r ON r.id = ra.role_id AND r.deleted_at IS NULL JOIN users u ON u.id = ra.user_id
           WHERE s.opportunity_id = :i OR s.crm_org_id = :c ORDER BY r.name, u.display_name""",
        i=opp_id, c=opp["crm_org_id"],
    )
    proposals = await q(
        db,
        """SELECT p.id, p.number, p.title, p.status, p.valid_until, v.version_no, v.price_total, v.currency
           FROM proposals p LEFT JOIN proposal_versions v ON v.id = p.current_version_id WHERE p.opportunity_id = :i AND p.deleted_at IS NULL ORDER BY p.created_at""",
        i=opp_id,
    )
    ndas = await q(
        db,
        """SELECT n.id, n.number, n.title, n.status, n.valid_from, n.valid_to FROM ndas n WHERE n.deleted_at IS NULL AND (
             n.id IN (SELECT nda_id FROM nda_links WHERE opportunity_id = :i) OR n.crm_org_id = :c) ORDER BY n.valid_to NULLS LAST""",
        i=opp_id, c=opp["crm_org_id"],
    )
    contracts = await q(
        db,
        "SELECT id, number, title, status, valid_from, valid_to FROM contracts WHERE opportunity_id = :i AND deleted_at IS NULL ORDER BY created_at",
        i=opp_id,
    )
    activities = await q(
        db,
        """SELECT a.id, a.kind, a.subject, a.body, a.occurred_at, a.follow_up_task_id, t.status AS follow_up_status, t.due_date AS follow_up_due, u.display_name AS author_name
           FROM crm_activities a LEFT JOIN tasks t ON t.id = a.follow_up_task_id AND t.deleted_at IS NULL LEFT JOIN users u ON u.id = a.created_by
           WHERE a.opportunity_id = :i AND a.deleted_at IS NULL ORDER BY a.occurred_at DESC LIMIT 50""",
        i=opp_id,
    )
    bid = await q1(db, "SELECT decision, score, decided_at, authority_unclear FROM bid_assessments WHERE opportunity_id = :i", i=opp_id)
    base = _decorate(dict(base or {}), cfg, ctx)
    if ctx.level == "observer":
        for p in proposals:
            p["price_total"] = None
    return {
        **base, "contacts": contacts, "entries": entries, "references": references, "team": team, "scoped_roles": scoped,
        "proposals": proposals, "ndas": ndas, "contracts": contracts, "activities": activities, "bid": bid,
        "can_edit": await can_edit_opp(db, ctx, opp), "can_see_cost": await can_see_cost(db, ctx, opp),
    }


# ----------------------------------------------------------------- update


@router.patch("/opportunities/{opp_id}", summary="Update an opportunity", responses={403: {"description": "Not on the opportunity team"}, 409: {"description": "Converted to a project"}})
async def update_opportunity(opp_id: UUID, body: OppUpdate, ctx: CtxDep, db: DbDep) -> dict:
    opp = await require_edit_opp(db, ctx, opp_id)
    data = body.model_dump(exclude_unset=True)
    for required in ("title", "crm_org_id", "category", "risk", "currency"):
        if required in data and data[required] is None:
            raise err(422, "VALIDATION_ERROR", f"{required} cannot be empty.", required)
    if opp["project_id"] and ("crm_org_id" in data):
        raise err(409, "ALREADY_CONVERTED", "The customer of a converted opportunity cannot be changed.", "crm_org_id")
    if "crm_org_id" in data:
        await check_crm_org(db, ctx, data["crm_org_id"])
    if "owner_user_id" in data:
        await check_member(db, ctx, data["owner_user_id"], "owner_user_id")
    if data.get("circle_id"):
        await require_circle(db, ctx, data["circle_id"])
    _check_dates(data.get("expected_start", opp["expected_start"]), data.get("expected_end", opp["expected_end"]))
    if "probability" in data:
        data["probability_manual"] = data["probability"] is not None
    if "title" in data:
        data["title"] = data["title"].strip()
    sets, params = set_clause(
        data,
        {"title", "description", "crm_org_id", "circle_id", "category", "source", "risk", "value_amount", "currency", "probability", "probability_manual", "effort_days",
         "expected_close", "expected_start", "expected_end", "owner_user_id", "next_action", "next_action_due"},
    )
    if sets:
        await x(db, f"UPDATE opportunities SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=opp_id, u=ctx.user_id, **params)  # noqa: S608
        await audit(db, ctx, "opportunity.updated", "opportunity", opp_id, f"{opp['number']} {opp['title']}", {"fields": sorted(data)})
        new_owner = data.get("owner_user_id")
        if new_owner and new_owner != opp["owner_user_id"]:
            await notify(db, ctx.org_id, [new_owner], "task", f"You now own opportunity {opp['number']}", opp["title"], f"/sales/opportunities/{opp_id}", exclude=ctx.user_id)
    await db.commit()
    return {"ok": True}


@router.put("/opportunities/{opp_id}/links", summary="Replace contacts, catalog entries, reference projects and team (only the given parts)")
async def set_links(opp_id: UUID, body: LinksBody, ctx: CtxDep, db: DbDep) -> dict:
    opp = await require_edit_opp(db, ctx, opp_id)
    if body.contacts is not None:
        await _check_contacts(db, ctx, [c.contact_id for c in body.contacts])
        await x(db, "DELETE FROM opportunity_contacts WHERE opportunity_id = :i", i=opp_id)
        for c in {c.contact_id: c for c in body.contacts}.values():
            await x(db, "INSERT INTO opportunity_contacts (organization_id, opportunity_id, contact_id, contact_role) VALUES (:o, :i, :c, :r)", o=ctx.org_id, i=opp_id, c=c.contact_id, r=c.contact_role)
    if body.entry_ids is not None:
        await _check_entries(db, ctx, body.entry_ids)
        await x(db, "DELETE FROM opportunity_catalog_links WHERE opportunity_id = :i", i=opp_id)
        for eid in set(body.entry_ids):
            await x(db, "INSERT INTO opportunity_catalog_links (organization_id, opportunity_id, entry_id) VALUES (:o, :i, :e)", o=ctx.org_id, i=opp_id, e=eid)
    if body.reference_project_ids is not None:
        await _check_projects(db, ctx, body.reference_project_ids)
        await x(db, "DELETE FROM opportunity_references WHERE opportunity_id = :i", i=opp_id)
        for pid in set(body.reference_project_ids):
            await x(db, "INSERT INTO opportunity_references (organization_id, opportunity_id, project_id) VALUES (:o, :i, :p)", o=ctx.org_id, i=opp_id, p=pid)
    if body.team is not None:
        for member in body.team:
            await check_member(db, ctx, member.user_id, "team")
        await x(db, "DELETE FROM opportunity_team WHERE opportunity_id = :i", i=opp_id)
        for member in {m.user_id: m for m in body.team}.values():
            await x(db, "INSERT INTO opportunity_team (organization_id, opportunity_id, user_id, role_id, team_role) VALUES (:o, :i, :u, :r, :t)", o=ctx.org_id, i=opp_id, u=member.user_id, r=member.role_id, t=member.team_role)
    await audit(db, ctx, "opportunity.links_changed", "opportunity", opp_id, f"{opp['number']} {opp['title']}")
    await db.commit()
    return {"ok": True}


@router.post("/opportunities/{opp_id}/stage", summary="Move an opportunity to another stage", responses={422: {"description": "Rule violated (reason, bid decision)"}, 403: {"description": "Not allowed"}})
async def move_stage(opp_id: UUID, body: StageBody, ctx: CtxDep, db: DbDep) -> dict:
    opp = await require_edit_opp(db, ctx, opp_id)
    bid = await q1(db, "SELECT decision FROM bid_assessments WHERE opportunity_id = :i", i=opp_id)
    problem = stage_transition_error(opp["stage"], body.stage, body.lost_reason, bid["decision"] if bid else None, opp["project_id"] is not None, ctx.level == "org_admin")
    if problem:
        status = 403 if problem[0] == "REOPEN_ADMIN_ONLY" else (409 if problem[0] == "ALREADY_CONVERTED" else 422)
        raise err(status, problem[0], problem[1], problem[2])
    if body.stage == opp["stage"]:
        return {"ok": True, "stage": opp["stage"]}
    closing = body.stage in ("won", "lost")
    await x(
        db,
        """UPDATE opportunities SET stage = :s, stage_changed_at = NOW(), lost_reason = CASE WHEN :lost THEN :lr END,
               closed_at = CASE WHEN :cl THEN NOW() END, probability = CASE WHEN :cl THEN NULL ELSE probability END,
               probability_manual = CASE WHEN :cl THEN FALSE ELSE probability_manual END, updated_at = NOW(), updated_by = :u WHERE id = :i""",
        s=body.stage, lost=body.stage == "lost", lr=(body.lost_reason or "").strip() or None, cl=closing, u=ctx.user_id, i=opp_id,
    )
    await audit(db, ctx, "opportunity.stage_changed", "opportunity", opp_id, f"{opp['number']}: {opp['stage']} -> {body.stage}", {"from": opp["stage"], "to": body.stage, "lost_reason": body.lost_reason})
    if opp["owner_user_id"] and closing:
        await notify(db, ctx.org_id, [opp["owner_user_id"]], "task", f"Opportunity {opp['number']} {body.stage}", opp["title"], f"/sales/opportunities/{opp_id}", exclude=ctx.user_id)
    await db.commit()
    return {"ok": True, "stage": body.stage}


@router.delete("/opportunities/{opp_id}", summary="Delete an opportunity (soft) - administrators or the owner", responses={409: {"description": "Converted to a project"}})
async def delete_opportunity(opp_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    opp = await get_opp(db, ctx, opp_id)
    if ctx.level != "org_admin" and opp["owner_user_id"] != ctx.user_id:
        raise err(403, "OPPORTUNITY_FORBIDDEN", "Only administrators or the owner can delete an opportunity.")
    if opp["project_id"]:
        raise err(409, "ALREADY_CONVERTED", "An opportunity that became a project cannot be deleted.")
    await x(db, "UPDATE opportunities SET deleted_at = NOW(), updated_by = :u WHERE id = :i", i=opp_id, u=ctx.user_id)
    await audit(db, ctx, "opportunity.deleted", "opportunity", opp_id, f"{opp['number']} {opp['title']}")
    await db.commit()
    return {"ok": True}


# ----------------------------------------------------------- chain/history


CHAIN = ("lead", "qualification", "bid_decision", "proposal", "negotiation", "contract", "project")


@router.get("/opportunities/{opp_id}/chain", summary="The process chain from lead to project with the linked records")
async def chain(opp_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    opp = await get_opp(db, ctx, opp_id)
    events = await q(db, "SELECT data, created_at FROM audit_events WHERE entity_type = 'opportunity' AND entity_id = :i AND action = 'opportunity.stage_changed' ORDER BY created_at", i=opp_id)
    at: dict[str, Any] = {"lead": opp["created_at"]}
    reached = 0
    for e in events:
        to = (e["data"] or {}).get("to")
        if to in STAGES:
            at.setdefault(to, e["created_at"])
            if to in OPEN_STAGES:
                reached = max(reached, OPEN_STAGES.index(to))
    stage = opp["stage"]
    current_idx = OPEN_STAGES.index(stage) if stage in OPEN_STAGES else (len(OPEN_STAGES) if stage == "won" else reached)
    bid = await q1(db, "SELECT id, decision, score, decided_at FROM bid_assessments WHERE opportunity_id = :i", i=opp_id)
    proposals = await q(db, "SELECT id, number, status FROM proposals WHERE opportunity_id = :i AND deleted_at IS NULL ORDER BY created_at", i=opp_id)
    contracts = await q(db, "SELECT id, number, status FROM contracts WHERE opportunity_id = :i AND deleted_at IS NULL ORDER BY created_at", i=opp_id)
    project = await q1(db, "SELECT id, name FROM projects WHERE id = :p AND deleted_at IS NULL", p=opp["project_id"]) if opp["project_id"] else None
    refs: dict[str, list[dict]] = {
        "bid_decision": [{"type": "bid", "id": bid["id"], "label": bid["decision"]}] if bid else [],
        "proposal": [{"type": "proposal", "id": p["id"], "label": p["number"]} for p in proposals],
        "contract": [{"type": "contract", "id": c["id"], "label": c["number"]} for c in contracts],
        "project": [{"type": "project", "id": project["id"], "label": project["name"]}] if project else [],
    }
    steps = []
    for key in CHAIN:
        if key in OPEN_STAGES:
            idx = OPEN_STAGES.index(key)
            if idx < current_idx or (stage == "won" and idx <= current_idx):
                status = "done"
            elif idx == current_idx and stage in OPEN_STAGES:
                status = "current"
            else:
                status = "pending"
            if stage == "lost" and idx <= reached:
                status = "done"
        elif key == "contract":
            status = "done" if any(c["status"] == "signed" for c in contracts) else ("current" if contracts else "pending")
        else:
            status = "done" if project else "pending"
        steps.append({"key": key, "status": status, "at": at.get(key), "refs": refs.get(key, [])})
    return {"stage": stage, "lost": stage == "lost", "lost_reason": opp["lost_reason"], "steps": steps}


@router.get("/opportunities/{opp_id}/history", summary="Audit trail of one opportunity")
async def history(opp_id: UUID, ctx: CtxDep, db: DbDep) -> list[dict]:
    await get_opp(db, ctx, opp_id)
    return await q(
        db,
        """SELECT a.id, a.action, a.summary, a.data, a.created_at, u.display_name AS actor_name FROM audit_events a LEFT JOIN users u ON u.id = a.actor_id
           WHERE a.organization_id = :o AND a.entity_type = 'opportunity' AND a.entity_id = :i ORDER BY a.created_at DESC LIMIT 100""",
        o=ctx.org_id, i=opp_id,
    )
