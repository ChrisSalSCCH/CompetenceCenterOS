"""Proposals: versions, calculation, approval steps and immutable snapshots, plus the price list.

An approved version is locked (database triggers enforce this as well); changes always create a new version.
Cost and margin are only returned to people who may see them.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from services.commercial import (
    approval_steps,
    calc_totals,
    currency_error,
    diff_versions,
    line_effort_days,
    resolve_authority,
    snapshot_hash,
)
from services.commercial_db import (
    can_edit_opp,
    can_see_cost,
    get_opp,
    held_role_ids,
    load_rules,
    money_hidden,
    next_number,
    require_edit_opp,
)
from services.ctx import CtxDep, require_admin, require_write
from services.dbx import DbDep, err, jb, q, q1, set_clause, x
from services.events import audit, notify

router = APIRouter(prefix="/api/commercial", tags=["proposals"])

LineKind = Literal["labor", "material", "travel", "external", "other"]
Unit = Literal["day", "hour", "piece", "flat"]
MAX_MONEY = Decimal("999999999999")
CURRENCY = r"^[A-Z]{3}$"
PROPOSAL_NOT_FOUND = "Proposal not found."
VERSION_NOT_FOUND = "Version not found."
EDITABLE = ("draft", "rejected")
COST_KEYS = ("cost_total", "margin", "margin_pct", "unit_cost", "cost_rate")


class WorkPackageIn(BaseModel):
    code: str = Field(default="", max_length=20)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    effort_days: Decimal | None = Field(default=None, ge=0, le=Decimal("100000"))
    start_date: date | None = None
    end_date: date | None = None
    milestone_title: str | None = Field(default=None, max_length=200)
    milestone_due: date | None = None


class LineIn(BaseModel):
    line_kind: LineKind = "labor"
    description: str = Field(min_length=1, max_length=300)
    role_label: str | None = Field(default=None, max_length=120)
    rate_entry_id: UUID | None = None
    quantity: Decimal = Field(default=Decimal(1), ge=0, le=Decimal("1000000"))
    unit: Unit = "day"
    unit_cost: Decimal | None = Field(default=None, ge=0, le=MAX_MONEY)
    unit_price: Decimal | None = Field(default=None, ge=0, le=MAX_MONEY)
    currency: str | None = Field(default=None, pattern=CURRENCY)
    wp_index: int | None = Field(default=None, ge=0, le=500)


class VersionSave(BaseModel):
    label: str | None = Field(default=None, max_length=120)
    summary: str | None = Field(default=None, max_length=20000)
    scope_text: str | None = Field(default=None, max_length=20000)
    assumptions: str | None = Field(default=None, max_length=20000)
    exclusions: str | None = Field(default=None, max_length=20000)
    terms: str | None = Field(default=None, max_length=20000)
    currency: str | None = Field(default=None, pattern=CURRENCY)
    fx_rate: Decimal | None = Field(default=None, gt=0, le=Decimal("1000000"))
    fx_note: str | None = Field(default=None, max_length=300)
    work_packages: list[WorkPackageIn] | None = Field(default=None, max_length=100)
    lines: list[LineIn] | None = Field(default=None, max_length=500)


class ProposalCreate(BaseModel):
    opportunity_id: UUID
    title: str = Field(min_length=3, max_length=200)
    valid_until: date | None = None
    currency: str = Field(default="EUR", pattern=CURRENCY)


class ProposalUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    valid_until: date | None = None


class NewVersion(BaseModel):
    kind: Literal["revision", "alternative"] = "revision"
    from_version_id: UUID | None = None
    label: str | None = Field(default=None, max_length=120)


class ApprovalDecision(BaseModel):
    decision: Literal["approve", "reject"]
    note: str | None = Field(default=None, max_length=2000)


class Outcome(BaseModel):
    outcome: Literal["accepted", "rejected", "withdrawn"]
    note: str | None = Field(default=None, max_length=2000)


class RateBody(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    role_label: str = Field(min_length=2, max_length=120)
    unit: Unit = "day"
    cost_rate: Decimal = Field(default=Decimal(0), ge=0, le=MAX_MONEY)
    sell_rate: Decimal = Field(default=Decimal(0), ge=0, le=MAX_MONEY)
    currency: str = Field(default="EUR", pattern=CURRENCY)
    valid_from: date | None = None
    valid_to: date | None = None


class RateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    role_label: str | None = Field(default=None, min_length=2, max_length=120)
    unit: Unit | None = None
    cost_rate: Decimal | None = Field(default=None, ge=0, le=MAX_MONEY)
    sell_rate: Decimal | None = Field(default=None, ge=0, le=MAX_MONEY)
    currency: str | None = Field(default=None, pattern=CURRENCY)
    valid_from: date | None = None
    valid_to: date | None = None


# ---------------------------------------------------------------- helpers


async def _proposal(db, ctx, proposal_id: UUID) -> dict:
    row = await q1(db, "SELECT * FROM proposals WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=proposal_id, o=ctx.org_id)
    if row is None:
        raise err(404, "PROPOSAL_NOT_FOUND", PROPOSAL_NOT_FOUND)
    return row


async def _version(db, ctx, proposal_id: UUID, version_id: UUID) -> dict:
    row = await q1(db, "SELECT * FROM proposal_versions WHERE id = :v AND proposal_id = :p AND organization_id = :o", v=version_id, p=proposal_id, o=ctx.org_id)
    if row is None:
        raise err(404, "VERSION_NOT_FOUND", VERSION_NOT_FOUND)
    return row


async def _editable(db, ctx, proposal_id: UUID) -> tuple[dict, dict]:
    """Proposal and its opportunity, after checking that the caller may edit."""
    p = await _proposal(db, ctx, proposal_id)
    opp = await require_edit_opp(db, ctx, p["opportunity_id"])
    return p, opp


def _require_editable_version(v: dict) -> None:
    if v["locked_at"] is not None:
        raise err(409, "VERSION_LOCKED", "This version is approved and locked. Create a new version to change it.")
    if v["status"] not in EDITABLE:
        raise err(409, "VERSION_IN_APPROVAL", "This version is in approval and cannot be changed.")


def _strip_cost(obj: dict[str, Any]) -> dict[str, Any]:
    for key in COST_KEYS:
        if key in obj:
            obj[key] = None
    return obj


async def build_snapshot(db, version_id: UUID) -> dict[str, Any]:
    """Complete, hashable content of a version."""
    v = await q1(
        db,
        """SELECT label, summary, scope_text, assumptions, exclusions, terms, currency, fx_rate, fx_note, price_total, cost_total, margin_pct, effort_days
           FROM proposal_versions WHERE id = :v""",
        v=version_id,
    )
    wps = await q(
        db,
        """SELECT code, title, description, effort_days, start_date, end_date, milestone_title, milestone_due, position
           FROM proposal_work_packages WHERE version_id = :v ORDER BY position, code, title""",
        v=version_id,
    )
    lines = await q(
        db,
        """SELECT l.line_kind, l.description, l.role_label, l.quantity, l.unit, l.unit_cost, l.unit_price, l.currency, l.position, w.title AS work_package
           FROM proposal_calc_lines l LEFT JOIN proposal_work_packages w ON w.id = l.work_package_id WHERE l.version_id = :v ORDER BY l.position, l.description""",
        v=version_id,
    )
    return {**(v or {}), "work_packages": wps, "lines": lines}


async def _view_snapshot(db, ctx, opp: dict, snap: dict[str, Any]) -> dict[str, Any]:
    if money_hidden(ctx):
        for key in ("price_total", "cost_total", "margin_pct"):
            snap[key] = None
        for ln in snap.get("lines", []):
            ln["unit_price"] = None
            ln["unit_cost"] = None
    elif not await can_see_cost(db, ctx, opp):
        _strip_cost(snap)
        for ln in snap.get("lines", []):
            _strip_cost(ln)
    return snap


async def _recalculate(db, version_id: UUID) -> dict[str, Any]:
    v = await q1(db, "SELECT currency, fx_rate FROM proposal_versions WHERE id = :v", v=version_id)
    lines = await q(db, "SELECT line_kind, quantity, unit, unit_cost, unit_price, currency FROM proposal_calc_lines WHERE version_id = :v", v=version_id)
    totals = calc_totals(lines, v["currency"], v["fx_rate"])
    await x(
        db,
        "UPDATE proposal_versions SET price_total = :p, cost_total = :c, margin_pct = :m, effort_days = :e, updated_at = NOW() WHERE id = :v",
        p=totals["price_total"], c=totals["cost_total"], m=totals["margin_pct"], e=totals["effort_days"], v=version_id,
    )
    return totals


async def _resolve_rate(db, ctx, line: LineIn, on: date) -> tuple[Decimal, Decimal, str, str]:
    """(unit_cost, unit_price, currency, unit) of a price-list entry that is valid on the given date."""
    rate = await q1(db, "SELECT * FROM rate_entries WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=line.rate_entry_id, o=ctx.org_id)
    if rate is None:
        raise err(404, "RATE_NOT_FOUND", "Price list entry not found.", "lines")
    if rate["valid_from"] > on or (rate["valid_to"] is not None and rate["valid_to"] < on):
        raise err(422, "RATE_NOT_VALID", f"The price list entry “{rate['name']}” is not valid today.", "lines")
    return rate["cost_rate"], rate["sell_rate"], rate["currency"], rate["unit"]


async def _write_content(db, ctx, version_id: UUID, body: VersionSave, currency: str) -> None:
    """Replace work packages and calculation lines of an unlocked version."""
    wps = body.work_packages
    lines = body.lines
    if lines is not None:
        await x(db, "DELETE FROM proposal_calc_lines WHERE version_id = :v", v=version_id)
    if wps is not None:
        await x(db, "DELETE FROM proposal_work_packages WHERE version_id = :v", v=version_id)
    # Lines are validated before anything is written.
    prepared: list[dict[str, Any]] = []
    for ln in lines or []:
        cost, price, cur, unit = ln.unit_cost, ln.unit_price, ln.currency or currency, ln.unit
        if ln.rate_entry_id:
            r_cost, r_price, r_cur, r_unit = await _resolve_rate(db, ctx, ln, date.today())
            cost = r_cost if cost is None else cost
            price = r_price if price is None else price
            cur = ln.currency or r_cur
            unit = r_unit if "unit" not in ln.model_fields_set else ln.unit
        if price is None or cost is None:
            raise err(422, "PRICE_REQUIRED", f"Line “{ln.description}” needs a price and a cost (or a price list entry).", "lines")
        prepared.append({"ln": ln, "cost": cost, "price": price, "cur": cur, "unit": unit})
    fx = await q1(db, "SELECT fx_rate, fx_note FROM proposal_versions WHERE id = :v", v=version_id)
    problem = currency_error([{"currency": p["cur"]} for p in prepared], currency, fx["fx_rate"], fx["fx_note"])
    if problem and lines is not None:
        raise err(422, problem[0], problem[1], "fx_rate")
    wp_ids: list[UUID] = []
    for pos, wp in enumerate(wps or []):
        linked = sum(
            (line_effort_days({"line_kind": p["ln"].line_kind, "quantity": p["ln"].quantity, "unit": p["unit"]}) for p in prepared if p["ln"].wp_index == pos),
            Decimal(0),
        )
        effort = wp.effort_days if wp.effort_days is not None else linked.quantize(Decimal("0.1"))
        row = await q1(
            db,
            """INSERT INTO proposal_work_packages (organization_id, version_id, code, title, description, effort_days, start_date, end_date, milestone_title, milestone_due, position)
               VALUES (:o, :v, :c, :t, :d, :e, :sd, :ed, :mt, :md, :p) RETURNING id""",
            o=ctx.org_id, v=version_id, c=wp.code, t=wp.title, d=wp.description, e=effort, sd=wp.start_date, ed=wp.end_date, mt=wp.milestone_title, md=wp.milestone_due, p=pos,
        )
        wp_ids.append(row["id"])
    for pos, p in enumerate(prepared):
        ln = p["ln"]
        if ln.wp_index is not None and ln.wp_index >= len(wp_ids):
            raise err(422, "INVALID_WORK_PACKAGE", "A line refers to a work package that does not exist.", "lines")
        await x(
            db,
            """INSERT INTO proposal_calc_lines (organization_id, version_id, work_package_id, line_kind, description, role_label, rate_entry_id, quantity, unit, unit_cost, unit_price, currency, position)
               VALUES (:o, :v, :w, :k, :d, :r, :re, :q, :un, :uc, :up, :cu, :p)""",
            o=ctx.org_id, v=version_id, w=wp_ids[ln.wp_index] if ln.wp_index is not None else None, k=ln.line_kind, d=ln.description, r=ln.role_label, re=ln.rate_entry_id,
            q=ln.quantity, un=p["unit"], uc=p["cost"], up=p["price"], cu=p["cur"], p=pos,
        )


async def _approval_rows(db, version_id: UUID, ctx) -> list[dict]:
    rows = await q(
        db,
        """SELECT a.id, a.step_order, a.label, a.role_id, r.name AS role_name, a.status, a.decided_by, u.display_name AS decided_by_name, a.decided_at, a.note, a.admin_override
           FROM proposal_approvals a LEFT JOIN roles r ON r.id = a.role_id LEFT JOIN users u ON u.id = a.decided_by WHERE a.version_id = :v ORDER BY a.step_order""",
        v=version_id,
    )
    held = {str(r) for r in await held_role_ids(db, ctx)}
    pending = [r for r in rows if r["status"] == "pending"]
    first = pending[0]["id"] if pending else None
    for r in rows:
        holds = r["role_id"] is not None and str(r["role_id"]) in held
        r["can_decide"] = r["id"] == first and ctx.level != "observer" and (holds or ctx.level == "org_admin")
        r["needs_override_note"] = r["can_decide"] and not holds
    return rows


async def _version_view(db, ctx, opp: dict, v: dict) -> dict:
    snap = await build_snapshot(db, v["id"])
    snap = await _view_snapshot(db, ctx, opp, snap)
    head = {k: v[k] for k in ("id", "proposal_id", "version_no", "kind", "status", "locked_at", "submitted_at", "snapshot_hash", "created_at", "updated_at")}
    head["currency"] = v["currency"]
    head["effort_days"] = v["effort_days"]
    head["fx_rate"] = v["fx_rate"]
    wps = await q(
        db,
        """SELECT id, code, title, description, effort_days, start_date, end_date, milestone_title, milestone_due, position
           FROM proposal_work_packages WHERE version_id = :v ORDER BY position, code""",
        v=v["id"],
    )
    lines = await q(
        db,
        """SELECT id, work_package_id, line_kind, description, role_label, rate_entry_id, quantity, unit, unit_cost, unit_price, currency, position
           FROM proposal_calc_lines WHERE version_id = :v ORDER BY position""",
        v=v["id"],
    )
    see_cost = await can_see_cost(db, ctx, opp)
    hidden = money_hidden(ctx)
    for ln in lines:
        if hidden:
            ln["unit_price"] = None
        if hidden or not see_cost:
            ln["unit_cost"] = None
    head.update({k: snap.get(k) for k in ("label", "summary", "scope_text", "assumptions", "exclusions", "terms", "fx_note", "price_total", "cost_total", "margin_pct")})
    return {
        **head,
        "work_packages": wps,
        "lines": lines,
        "approvals": await _approval_rows(db, v["id"], ctx),
        "editable": v["locked_at"] is None and v["status"] in EDITABLE and await can_edit_opp(db, ctx, opp),
        "can_see_cost": see_cost,
    }


# ------------------------------------------------------------------ list


@router.get("/proposals", summary="List proposals")
async def list_proposals(ctx: CtxDep, db: DbDep, opportunity_id: UUID | None = None, status: str | None = Query(default=None, max_length=12)) -> list[dict]:
    rows = await q(
        db,
        """SELECT p.id, p.number, p.title, p.status, p.valid_until, p.opportunity_id, o.number AS opportunity_number, o.title AS opportunity_title, co.name AS customer_name,
                  v.version_no, v.status AS version_status, v.price_total, v.currency, p.updated_at,
                  (SELECT COUNT(*) FROM proposal_versions x WHERE x.proposal_id = p.id) AS version_count
           FROM proposals p JOIN opportunities o ON o.id = p.opportunity_id JOIN crm_organizations co ON co.id = o.crm_org_id
           LEFT JOIN proposal_versions v ON v.id = p.current_version_id
           WHERE p.organization_id = :o AND p.deleted_at IS NULL AND o.deleted_at IS NULL AND (CAST(:op AS uuid) IS NULL OR p.opportunity_id = CAST(:op AS uuid))
             AND (CAST(:st AS text) IS NULL OR p.status = CAST(:st AS text)) ORDER BY p.created_at DESC LIMIT 500""",
        o=ctx.org_id, op=opportunity_id, st=status,
    )
    if money_hidden(ctx):
        for r in rows:
            r["price_total"] = None
    return rows


@router.post("/proposals", summary="Create a proposal with its first draft version", responses={422: {"description": "Bid decision missing"}, 403: {"description": "Not on the opportunity team"}})
async def create_proposal(body: ProposalCreate, ctx: CtxDep, db: DbDep) -> dict:
    opp = await require_edit_opp(db, ctx, body.opportunity_id)
    if opp["stage"] in ("won", "lost"):
        raise err(409, "OPPORTUNITY_CLOSED", "Proposals cannot be added to a closed opportunity.")
    bid = await q1(db, "SELECT decision FROM bid_assessments WHERE opportunity_id = :i", i=opp["id"])
    if not bid or bid["decision"] != "bid":
        raise err(422, "BID_DECISION_REQUIRED", "A Bid decision is required before a proposal can be created.", "opportunity_id")
    number = await next_number(db, ctx.org_id, "ANG")
    prop = await q1(
        db,
        "INSERT INTO proposals (organization_id, number, opportunity_id, title, valid_until, created_by, updated_by) VALUES (:o, :n, :op, :t, :vu, :u, :u) RETURNING id",
        o=ctx.org_id, n=number, op=opp["id"], t=body.title.strip(), vu=body.valid_until, u=ctx.user_id,
    )
    ver = await q1(
        db,
        """INSERT INTO proposal_versions (organization_id, proposal_id, version_no, kind, currency, created_by, updated_by)
           VALUES (:o, :p, 1, 'draft', :cu, :u, :u) RETURNING id""",
        o=ctx.org_id, p=prop["id"], cu=body.currency, u=ctx.user_id,
    )
    await x(db, "UPDATE proposals SET current_version_id = :v WHERE id = :p", v=ver["id"], p=prop["id"])
    await audit(db, ctx, "proposal.created", "proposal", prop["id"], f"{number} {body.title}", {"opportunity_id": str(opp["id"])})
    await audit(db, ctx, "opportunity.proposal_created", "opportunity", opp["id"], f"{opp['number']}: proposal {number}")
    await db.commit()
    return {"id": prop["id"], "number": number, "version_id": ver["id"]}


@router.get("/proposals/{proposal_id}", summary="Proposal with all versions and the current one in detail", responses={404: {"description": PROPOSAL_NOT_FOUND}})
async def proposal_detail(proposal_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    p = await _proposal(db, ctx, proposal_id)
    opp = await get_opp(db, ctx, p["opportunity_id"])
    versions = await q(
        db,
        """SELECT v.id, v.version_no, v.kind, v.status, v.label, v.price_total, v.currency, v.locked_at, v.submitted_at, v.created_at, u.display_name AS author_name
           FROM proposal_versions v LEFT JOIN users u ON u.id = v.created_by WHERE v.proposal_id = :p ORDER BY v.version_no DESC""",
        p=proposal_id,
    )
    if money_hidden(ctx):
        for v in versions:
            v["price_total"] = None
    current = next((v for v in versions if v["id"] == p["current_version_id"]), versions[0] if versions else None)
    full = await _version_view(db, ctx, opp, await _version(db, ctx, proposal_id, current["id"])) if current else None
    return {
        **{k: p[k] for k in ("id", "number", "title", "status", "valid_until", "opportunity_id", "current_version_id", "created_at", "updated_at")},
        "opportunity": {"id": opp["id"], "number": opp["number"], "title": opp["title"], "stage": opp["stage"], "crm_org_id": opp["crm_org_id"]},
        "versions": versions, "current": full, "can_edit": await can_edit_opp(db, ctx, opp),
    }


@router.get("/proposals/{proposal_id}/versions/{version_id}", summary="One version in detail", responses={404: {"description": VERSION_NOT_FOUND}})
async def version_detail(proposal_id: UUID, version_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    p = await _proposal(db, ctx, proposal_id)
    opp = await get_opp(db, ctx, p["opportunity_id"])
    return await _version_view(db, ctx, opp, await _version(db, ctx, proposal_id, version_id))


@router.patch("/proposals/{proposal_id}", summary="Change title or validity of a proposal")
async def update_proposal(proposal_id: UUID, body: ProposalUpdate, ctx: CtxDep, db: DbDep) -> dict:
    p, _ = await _editable(db, ctx, proposal_id)
    data = body.model_dump(exclude_unset=True)
    if "title" in data and data["title"] is None:
        raise err(422, "VALIDATION_ERROR", "title cannot be empty.", "title")
    sets, params = set_clause(data, {"title", "valid_until"})
    if sets:
        await x(db, f"UPDATE proposals SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=proposal_id, u=ctx.user_id, **params)  # noqa: S608
        await audit(db, ctx, "proposal.updated", "proposal", proposal_id, p["number"])
    await db.commit()
    return {"ok": True}


@router.delete("/proposals/{proposal_id}", summary="Delete a proposal that was never approved (soft)", responses={409: {"description": "Already approved"}})
async def delete_proposal(proposal_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    p, _ = await _editable(db, ctx, proposal_id)
    locked = await q1(db, "SELECT 1 AS ok FROM proposal_versions WHERE proposal_id = :p AND locked_at IS NOT NULL", p=proposal_id)
    if locked:
        raise err(409, "VERSION_LOCKED", "A proposal with an approved version cannot be deleted. Withdraw it instead.")
    await x(db, "UPDATE proposals SET deleted_at = NOW(), updated_by = :u WHERE id = :i", i=proposal_id, u=ctx.user_id)
    await audit(db, ctx, "proposal.deleted", "proposal", proposal_id, p["number"])
    await db.commit()
    return {"ok": True}


# ------------------------------------------------------ version editing


@router.put("/proposals/{proposal_id}/versions/{version_id}", summary="Save the content and calculation of a draft version", responses={409: {"description": "Version is locked or in approval"}, 422: {"description": "Calculation invalid"}})
async def save_version(proposal_id: UUID, version_id: UUID, body: VersionSave, ctx: CtxDep, db: DbDep) -> dict:
    p, _ = await _editable(db, ctx, proposal_id)
    v = await _version(db, ctx, proposal_id, version_id)
    _require_editable_version(v)
    data = body.model_dump(exclude_unset=True, exclude={"work_packages", "lines"})
    currency = data.get("currency") or v["currency"]
    sets, params = set_clause(data, {"label", "summary", "scope_text", "assumptions", "exclusions", "terms", "currency", "fx_rate", "fx_note"})
    if sets:
        await x(db, f"UPDATE proposal_versions SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=version_id, u=ctx.user_id, **params)  # noqa: S608
    await _write_content(db, ctx, version_id, body, currency)
    if body.lines is None and ("currency" in data or "fx_rate" in data):
        existing = await q(db, "SELECT currency FROM proposal_calc_lines WHERE version_id = :v", v=version_id)
        fx = await q1(db, "SELECT fx_rate, fx_note FROM proposal_versions WHERE id = :v", v=version_id)
        problem = currency_error(existing, currency, fx["fx_rate"], fx["fx_note"])
        if problem:
            raise err(422, problem[0], problem[1], "fx_rate")
    totals = await _recalculate(db, version_id)
    if v["status"] == "rejected":
        await x(db, "UPDATE proposal_versions SET status = 'draft' WHERE id = :v", v=version_id)
    await x(db, "UPDATE proposals SET updated_at = NOW(), updated_by = :u WHERE id = :p", u=ctx.user_id, p=proposal_id)
    await audit(db, ctx, "proposal.version_saved", "proposal", proposal_id, f"{p['number']} v{v['version_no']}", {"version_id": str(version_id), "price_total": str(totals["price_total"])})
    await db.commit()
    return {"ok": True, "price_total": totals["price_total"], "cost_total": totals["cost_total"], "margin_pct": totals["margin_pct"], "effort_days": totals["effort_days"]}


@router.post("/proposals/{proposal_id}/versions", summary="Create a new version (revision or alternative) from an existing one", responses={404: {"description": VERSION_NOT_FOUND}})
async def new_version(proposal_id: UUID, body: NewVersion, ctx: CtxDep, db: DbDep) -> dict:
    p, _ = await _editable(db, ctx, proposal_id)
    source = await _version(db, ctx, proposal_id, body.from_version_id or p["current_version_id"])
    nxt = await q1(db, "SELECT COALESCE(MAX(version_no), 0) + 1 AS n FROM proposal_versions WHERE proposal_id = :p", p=proposal_id)
    row = await q1(
        db,
        """INSERT INTO proposal_versions (organization_id, proposal_id, version_no, kind, label, summary, scope_text, assumptions, exclusions, terms, currency, fx_rate, fx_note,
                                          price_total, cost_total, margin_pct, effort_days, created_by, updated_by)
           VALUES (:o, :p, :n, :k, :lb, :s, :sc, :a, :e, :t, :cu, :fx, :fn, :pt, :ct, :mp, :ef, :u, :u) RETURNING id""",
        o=ctx.org_id, p=proposal_id, n=nxt["n"], k=body.kind, lb=body.label or source["label"], s=source["summary"], sc=source["scope_text"], a=source["assumptions"],
        e=source["exclusions"], t=source["terms"], cu=source["currency"], fx=source["fx_rate"], fn=source["fx_note"], pt=source["price_total"], ct=source["cost_total"],
        mp=source["margin_pct"], ef=source["effort_days"], u=ctx.user_id,
    )
    wps = await q(db, "SELECT id, code, title, description, effort_days, start_date, end_date, milestone_title, milestone_due, position FROM proposal_work_packages WHERE version_id = :v ORDER BY position", v=source["id"])
    mapping: dict[UUID, UUID] = {}
    for wp in wps:
        new_wp = await q1(
            db,
            """INSERT INTO proposal_work_packages (organization_id, version_id, code, title, description, effort_days, start_date, end_date, milestone_title, milestone_due, position)
               VALUES (:o, :v, :c, :t, :d, :e, :sd, :ed, :mt, :md, :p) RETURNING id""",
            o=ctx.org_id, v=row["id"], c=wp["code"], t=wp["title"], d=wp["description"], e=wp["effort_days"], sd=wp["start_date"], ed=wp["end_date"], mt=wp["milestone_title"], md=wp["milestone_due"], p=wp["position"],
        )
        mapping[wp["id"]] = new_wp["id"]
    lines = await q(db, "SELECT * FROM proposal_calc_lines WHERE version_id = :v ORDER BY position", v=source["id"])
    for ln in lines:
        await x(
            db,
            """INSERT INTO proposal_calc_lines (organization_id, version_id, work_package_id, line_kind, description, role_label, rate_entry_id, quantity, unit, unit_cost, unit_price, currency, position)
               VALUES (:o, :v, :w, :k, :d, :r, :re, :q, :un, :uc, :up, :cu, :p)""",
            o=ctx.org_id, v=row["id"], w=mapping.get(ln["work_package_id"]), k=ln["line_kind"], d=ln["description"], r=ln["role_label"], re=ln["rate_entry_id"], q=ln["quantity"], un=ln["unit"],
            uc=ln["unit_cost"], up=ln["unit_price"], cu=ln["currency"], p=ln["position"],
        )
    if body.kind == "revision":
        await x(db, "UPDATE proposals SET current_version_id = :v, updated_at = NOW() WHERE id = :p", v=row["id"], p=proposal_id)
    await audit(db, ctx, "proposal.version_created", "proposal", proposal_id, f"{p['number']} v{nxt['n']} ({body.kind})", {"from_version": source["version_no"]})
    await db.commit()
    return {"id": row["id"], "version_no": nxt["n"]}


@router.get("/proposals/{proposal_id}/compare", summary="Compare two versions of a proposal")
async def compare(proposal_id: UUID, ctx: CtxDep, db: DbDep, a: UUID = Query(), b: UUID = Query()) -> dict:
    p = await _proposal(db, ctx, proposal_id)
    opp = await get_opp(db, ctx, p["opportunity_id"])
    va, vb = await _version(db, ctx, proposal_id, a), await _version(db, ctx, proposal_id, b)
    sa = await _view_snapshot(db, ctx, opp, await build_snapshot(db, a))
    sb = await _view_snapshot(db, ctx, opp, await build_snapshot(db, b))
    return {"from": {"id": a, "version_no": va["version_no"]}, "to": {"id": b, "version_no": vb["version_no"]}, **diff_versions(sa, sb)}


# ------------------------------------------------------------- approval


@router.post("/proposals/{proposal_id}/versions/{version_id}/request-approval", summary="Send a draft version into approval", responses={422: {"description": "Incomplete calculation"}, 409: {"description": "Not editable"}})
async def request_approval(proposal_id: UUID, version_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    p, opp = await _editable(db, ctx, proposal_id)
    v = await _version(db, ctx, proposal_id, version_id)
    _require_editable_version(v)
    lines = await q1(db, "SELECT COUNT(*) AS n FROM proposal_calc_lines WHERE version_id = :v", v=version_id)
    if not lines or lines["n"] == 0:
        raise err(422, "CALCULATION_REQUIRED", "Add at least one calculation line before requesting approval.")
    rules = await load_rules(db, ctx, "proposal_approval")
    auth = resolve_authority(
        rules, set(), value=v["price_total"], category=opp["category"], risk=opp["risk"], circle_id=opp["circle_id"], margin_pct=v["margin_pct"]
    )
    steps = approval_steps(auth["matching"]) or [{"step_order": 1, "label": "Administrator", "rule_id": None, "role_id": None}]
    await x(db, "DELETE FROM proposal_approvals WHERE version_id = :v", v=version_id)
    for s in steps:
        await x(
            db,
            "INSERT INTO proposal_approvals (organization_id, version_id, step_order, label, rule_id, role_id) VALUES (:o, :v, :s, :l, :r, :ro)",
            o=ctx.org_id, v=version_id, s=s["step_order"], l=s["label"], r=s["rule_id"], ro=s["role_id"],
        )
    await x(db, "UPDATE proposal_versions SET status = 'in_approval', updated_at = NOW(), updated_by = :u WHERE id = :v", u=ctx.user_id, v=version_id)
    await x(db, "UPDATE proposals SET status = 'in_approval', updated_at = NOW() WHERE id = :p", p=proposal_id)
    first = steps[0]
    if first["role_id"]:
        holders = await q(db, "SELECT user_id FROM role_assignments WHERE role_id = :r AND organization_id = :o AND deleted_at IS NULL", r=first["role_id"], o=ctx.org_id)
        await notify(db, ctx.org_id, [h["user_id"] for h in holders], "governance", f"Approval needed: {p['number']} v{v['version_no']}", opp["title"], f"/sales/proposals/{proposal_id}", exclude=ctx.user_id)
    await audit(db, ctx, "proposal.approval_requested", "proposal", proposal_id, f"{p['number']} v{v['version_no']}", {"steps": [s["label"] for s in steps], "unclear": auth["unclear"]})
    await db.commit()
    return {"ok": True, "steps": len(steps), "authority_unclear": auth["unclear"]}


@router.post("/proposals/{proposal_id}/versions/{version_id}/approvals/{step_id}", summary="Approve or reject one approval step", responses={403: {"description": "Not the step's role holder"}, 409: {"description": "Step not due"}, 422: {"description": "Note required"}})
async def decide_step(proposal_id: UUID, version_id: UUID, step_id: UUID, body: ApprovalDecision, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    p = await _proposal(db, ctx, proposal_id)
    opp = await get_opp(db, ctx, p["opportunity_id"])
    v = await _version(db, ctx, proposal_id, version_id)
    if v["status"] != "in_approval":
        raise err(409, "NOT_IN_APPROVAL", "This version is not waiting for approval.")
    steps = await _approval_rows(db, version_id, ctx)
    step = next((s for s in steps if s["id"] == step_id), None)
    if step is None:
        raise err(404, "STEP_NOT_FOUND", "Approval step not found.")
    first_pending = next((s for s in steps if s["status"] == "pending"), None)
    if first_pending is None or first_pending["id"] != step_id:
        raise err(409, "STEP_NOT_DUE", "This step is not due: an earlier approval step is still open or it was already decided.")
    if not step["can_decide"]:
        raise err(403, "AUTHORITY_REQUIRED", "Only the holder of the step's role (or an administrator with a note) can decide this step.")
    override = bool(step["needs_override_note"])
    if override and not (body.note or "").strip():
        raise err(422, "OVERRIDE_NOTE_REQUIRED", "An administrator without the step's role must record a note.", "note")
    if body.decision == "reject" and not (body.note or "").strip():
        raise err(422, "NOTE_REQUIRED", "A reason is required when rejecting.", "note")
    status = "approved" if body.decision == "approve" else "rejected"
    await x(
        db,
        "UPDATE proposal_approvals SET status = :s, decided_by = :u, decided_at = NOW(), note = :n, admin_override = :ov WHERE id = :i",
        s=status, u=ctx.user_id, n=body.note, ov=override, i=step_id,
    )
    result = "step_approved"
    if status == "rejected":
        await x(db, "UPDATE proposal_versions SET status = 'rejected', updated_at = NOW() WHERE id = :v", v=version_id)
        await x(db, "UPDATE proposals SET status = 'draft', updated_at = NOW() WHERE id = :p", p=proposal_id)
        result = "rejected"
    elif all(s["status"] == "approved" or s["id"] == step_id for s in steps):
        snap = await build_snapshot(db, version_id)
        digest = snapshot_hash(snap)
        await x(
            db,
            "UPDATE proposal_versions SET status = 'approved', locked_at = NOW(), snapshot = CAST(:sn AS jsonb), snapshot_hash = :h, updated_at = NOW() WHERE id = :v",
            sn=jb(snap), h=digest, v=version_id,
        )
        await x(db, "UPDATE proposals SET status = 'approved', updated_at = NOW() WHERE id = :p", p=proposal_id)
        result = "approved"
    else:
        nxt = next(s for s in steps if s["status"] == "pending" and s["id"] != step_id)
        if nxt["role_id"]:
            holders = await q(db, "SELECT user_id FROM role_assignments WHERE role_id = :r AND organization_id = :o AND deleted_at IS NULL", r=nxt["role_id"], o=ctx.org_id)
            await notify(db, ctx.org_id, [h["user_id"] for h in holders], "governance", f"Approval needed: {p['number']} v{v['version_no']}", opp["title"], f"/sales/proposals/{proposal_id}", exclude=ctx.user_id)
    await audit(db, ctx, f"proposal.{result}", "proposal", proposal_id, f"{p['number']} v{v['version_no']}: {step['label']} {status}", {"step": step["label"], "override": override, "note": body.note})
    if result in ("approved", "rejected") and v["created_by"]:
        await notify(db, ctx.org_id, [v["created_by"]], "governance", f"Proposal {p['number']} v{v['version_no']} {result}", opp["title"], f"/sales/proposals/{proposal_id}", exclude=ctx.user_id)
    await db.commit()
    return {"ok": True, "result": result}


@router.post("/proposals/{proposal_id}/versions/{version_id}/submit", summary="Mark an approved version as sent to the customer", responses={409: {"description": "Not approved or content changed"}})
async def submit_version(proposal_id: UUID, version_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    p, _ = await _editable(db, ctx, proposal_id)
    v = await _version(db, ctx, proposal_id, version_id)
    if v["status"] != "approved" or v["locked_at"] is None:
        raise err(409, "NOT_APPROVED", "Only an approved version can be submitted to the customer.")
    if snapshot_hash(await build_snapshot(db, version_id)) != v["snapshot_hash"]:
        raise err(409, "SNAPSHOT_MISMATCH", "The content no longer matches the approved snapshot. Do not send this version.")
    if v["kind"] != "alternative":
        await x(db, "UPDATE proposal_versions SET status = 'superseded', updated_at = NOW() WHERE proposal_id = :p AND id <> :v AND kind <> 'alternative' AND status IN ('approved','submitted')", p=proposal_id, v=version_id)
    await x(db, "UPDATE proposal_versions SET status = 'submitted', submitted_at = NOW(), updated_at = NOW() WHERE id = :v", v=version_id)
    await x(db, "UPDATE proposals SET status = 'submitted', current_version_id = :v, updated_at = NOW() WHERE id = :p", v=version_id, p=proposal_id)
    await audit(db, ctx, "proposal.submitted", "proposal", proposal_id, f"{p['number']} v{v['version_no']} sent to customer")
    await db.commit()
    return {"ok": True}


@router.post("/proposals/{proposal_id}/outcome", summary="Record the customer's answer", responses={409: {"description": "Not submitted"}})
async def outcome(proposal_id: UUID, body: Outcome, ctx: CtxDep, db: DbDep) -> dict:
    p, opp = await _editable(db, ctx, proposal_id)
    if p["status"] != "submitted" and body.outcome != "withdrawn":
        raise err(409, "NOT_SUBMITTED", "Only a submitted proposal can be accepted or rejected.")
    await x(db, "UPDATE proposals SET status = :s, updated_at = NOW(), updated_by = :u WHERE id = :p", s=body.outcome, u=ctx.user_id, p=proposal_id)
    if body.outcome == "accepted" and opp["stage"] not in ("won", "lost"):
        await x(
            db,
            "UPDATE opportunities SET stage = 'won', stage_changed_at = NOW(), closed_at = NOW(), probability = NULL, probability_manual = FALSE, updated_at = NOW(), updated_by = :u WHERE id = :i",
            u=ctx.user_id, i=opp["id"],
        )
        await audit(db, ctx, "opportunity.stage_changed", "opportunity", opp["id"], f"{opp['number']}: {opp['stage']} -> won", {"from": opp["stage"], "to": "won", "by": "proposal_accepted"})
    await audit(db, ctx, f"proposal.{body.outcome}", "proposal", proposal_id, f"{p['number']} {body.outcome}", {"note": body.note})
    await db.commit()
    return {"ok": True}


# ------------------------------------------------------------ price list


@router.get("/rates", summary="Price list: day rates and unit prices with validity")
async def list_rates(ctx: CtxDep, db: DbDep, valid_on: date | None = None) -> list[dict]:
    if ctx.level == "observer":
        raise err(403, "READ_ONLY", "The price list is not visible to observers.")
    return await q(
        db,
        """SELECT id, name, role_label, unit, cost_rate, sell_rate, currency, valid_from, valid_to
           FROM rate_entries WHERE organization_id = :o AND deleted_at IS NULL AND (CAST(:d AS date) IS NULL OR (valid_from <= CAST(:d AS date) AND (valid_to IS NULL OR valid_to >= CAST(:d AS date))))
           ORDER BY role_label, valid_from DESC""",
        o=ctx.org_id, d=valid_on,
    )


def _check_rate_dates(start: date | None, end: date | None) -> None:
    if start and end and end < start:
        raise err(422, "INVALID_DATES", "The end of validity cannot be before its start.", "valid_to")


@router.post("/rates", summary="Add a price list entry - administrators only")
async def create_rate(body: RateBody, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    _check_rate_dates(body.valid_from, body.valid_to)
    row = await q1(
        db,
        """INSERT INTO rate_entries (organization_id, name, role_label, unit, cost_rate, sell_rate, currency, valid_from, valid_to, created_by, updated_by)
           VALUES (:o, :n, :r, :un, :c, :s, :cu, COALESCE(:vf, CURRENT_DATE), :vt, :u, :u) RETURNING id""",
        o=ctx.org_id, n=body.name.strip(), r=body.role_label.strip(), un=body.unit, c=body.cost_rate, s=body.sell_rate, cu=body.currency, vf=body.valid_from, vt=body.valid_to, u=ctx.user_id,
    )
    await audit(db, ctx, "rate.created", "rate_entry", row["id"], body.name)
    await db.commit()
    return {"id": row["id"]}


@router.patch("/rates/{rate_id}", summary="Change a price list entry - administrators only", responses={404: {"description": "Entry not found"}})
async def update_rate(rate_id: UUID, body: RateUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    rate = await q1(db, "SELECT * FROM rate_entries WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=rate_id, o=ctx.org_id)
    if rate is None:
        raise err(404, "RATE_NOT_FOUND", "Price list entry not found.")
    data = body.model_dump(exclude_unset=True)
    for required in ("name", "role_label", "unit", "cost_rate", "sell_rate", "currency", "valid_from"):
        if required in data and data[required] is None:
            raise err(422, "VALIDATION_ERROR", f"{required} cannot be empty.", required)
    _check_rate_dates(data.get("valid_from", rate["valid_from"]), data.get("valid_to", rate["valid_to"]))
    sets, params = set_clause(data, {"name", "role_label", "unit", "cost_rate", "sell_rate", "currency", "valid_from", "valid_to"})
    if sets:
        await x(db, f"UPDATE rate_entries SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=rate_id, u=ctx.user_id, **params)  # noqa: S608
        await audit(db, ctx, "rate.updated", "rate_entry", rate_id, rate["name"])
    await db.commit()
    return {"ok": True}


@router.delete("/rates/{rate_id}", summary="Delete a price list entry (soft) - administrators only")
async def delete_rate(rate_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    rate = await q1(db, "SELECT name FROM rate_entries WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=rate_id, o=ctx.org_id)
    if rate is None:
        raise err(404, "RATE_NOT_FOUND", "Price list entry not found.")
    await x(db, "UPDATE rate_entries SET deleted_at = NOW(), updated_by = :u WHERE id = :i", i=rate_id, u=ctx.user_id)
    await audit(db, ctx, "rate.deleted", "rate_entry", rate_id, rate["name"])
    await db.commit()
    return {"ok": True}
