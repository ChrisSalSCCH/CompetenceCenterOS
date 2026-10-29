"""NDAs and contracts: coverage, signature authority, framework agreements, milestones, amendments, reminders.

A signed NDA is evidence of confidentiality only - it is never a release for publication.
Contract conditions (value, milestones, notes) are visible only to people with a reason to see them.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from services.commercial import contract_state, nda_coverage, reminder_dates
from services.commercial_db import (
    check_authority,
    check_crm_org,
    check_member,
    held_role_ids,
    load_rules,
    next_number,
    on_opp_team,
    strip_money,
)
from services.ctx import CtxDep, require_write
from services.dbx import DbDep, err, q, q1, set_clause, x
from services.events import audit, notify

router = APIRouter(prefix="/api/commercial", tags=["agreements"])

NdaKind = Literal["mutual", "one_way_in", "one_way_out"]
ContractKind = Literal["framework", "project", "service", "license", "research", "other"]
Money = Decimal
MAX_MONEY = Decimal("999999999999")
CURRENCY = r"^[A-Z]{3}$"
NDA_NOT_FOUND = "NDA not found."
CONTRACT_NOT_FOUND = "Contract not found."
NO_PUBLICATION_RELEASE = "A signed NDA proves confidentiality. It does not release anything for publication or as a reference."
COVERAGE_RANK = {"active": 0, "expiring": 1, "not_started": 2, "expired": 3, "draft": 4, "terminated": 5}
REMINDER_WINDOW_DAYS = 30
MILESTONE_WINDOW_DAYS = 14


class NdaCreate(BaseModel):
    crm_org_id: UUID
    title: str = Field(min_length=3, max_length=200)
    nda_kind: NdaKind = "mutual"
    purpose: str = Field(default="", max_length=5000)
    recipients: str = Field(default="", max_length=2000)
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str = Field(default="", max_length=5000)
    opportunity_ids: list[UUID] = Field(default_factory=list, max_length=30)
    project_ids: list[UUID] = Field(default_factory=list, max_length=30)


class NdaUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    nda_kind: NdaKind | None = None
    purpose: str | None = Field(default=None, max_length=5000)
    recipients: str | None = Field(default=None, max_length=2000)
    valid_from: date | None = None
    valid_to: date | None = None
    notes: str | None = Field(default=None, max_length=5000)


class NdaLinks(BaseModel):
    opportunity_ids: list[UUID] = Field(default_factory=list, max_length=30)
    project_ids: list[UUID] = Field(default_factory=list, max_length=30)


class SignBody(BaseModel):
    signed_at: date | None = None
    signatory_name: str | None = Field(default=None, max_length=160)
    override_note: str | None = Field(default=None, max_length=2000)


class ContractCreate(BaseModel):
    crm_org_id: UUID
    title: str = Field(min_length=3, max_length=200)
    contract_kind: ContractKind = "project"
    parent_contract_id: UUID | None = None
    opportunity_id: UUID | None = None
    proposal_id: UUID | None = None
    value_amount: Money | None = Field(default=None, ge=0, le=MAX_MONEY)
    currency: str = Field(default="EUR", pattern=CURRENCY)
    valid_from: date | None = None
    valid_to: date | None = None
    notice_period_days: int | None = Field(default=None, ge=0, le=3650)
    auto_renew: bool = False
    owner_user_id: UUID | None = None
    notes: str = Field(default="", max_length=10000)
    project_ids: list[UUID] = Field(default_factory=list, max_length=30)


class ContractUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    contract_kind: ContractKind | None = None
    value_amount: Money | None = Field(default=None, ge=0, le=MAX_MONEY)
    currency: str | None = Field(default=None, pattern=CURRENCY)
    valid_from: date | None = None
    valid_to: date | None = None
    notice_period_days: int | None = Field(default=None, ge=0, le=3650)
    auto_renew: bool | None = None
    owner_user_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=10000)


class ProjectIds(BaseModel):
    project_ids: list[UUID] = Field(max_length=30)


class MilestoneBody(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    due_date: date | None = None
    amount: Money | None = Field(default=None, ge=0, le=MAX_MONEY)
    currency: str = Field(default="EUR", pattern=CURRENCY)
    project_id: UUID | None = None
    status: Literal["planned", "invoiced", "paid"] = "planned"


class MilestoneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    due_date: date | None = None
    amount: Money | None = Field(default=None, ge=0, le=MAX_MONEY)
    project_id: UUID | None = None
    status: Literal["planned", "invoiced", "paid"] | None = None


class AmendmentBody(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=5000)
    effective_date: date | None = None
    value_delta: Money | None = Field(default=None, ge=-MAX_MONEY, le=MAX_MONEY)
    new_valid_to: date | None = None
    signed: bool = False


# ---------------------------------------------------------------- helpers


def _check_range(start: date | None, end: date | None, field: str = "valid_to") -> None:
    if start and end and end < start:
        raise err(422, "INVALID_DATES", "The end date cannot be before the start date.", field)


async def _check_opps(db, ctx, ids: list[UUID]) -> None:
    for oid in set(ids):
        if await q1(db, "SELECT 1 AS ok FROM opportunities WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=oid, o=ctx.org_id) is None:
            raise err(404, "OPPORTUNITY_NOT_FOUND", "Opportunity not found.", "opportunity_ids")


async def _check_projects(db, ctx, ids: list[UUID], field: str = "project_ids") -> None:
    for pid in set(ids):
        if await q1(db, "SELECT 1 AS ok FROM projects WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=pid, o=ctx.org_id) is None:
            raise err(404, "PROJECT_NOT_FOUND", "Project not found.", field)


# ------------------------------------------------------------------ NDAs


async def _nda(db, ctx, nda_id: UUID) -> dict:
    row = await q1(db, "SELECT * FROM ndas WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=nda_id, o=ctx.org_id)
    if row is None:
        raise err(404, "NDA_NOT_FOUND", NDA_NOT_FOUND)
    return row


async def _can_edit_nda(db, ctx, nda: dict) -> bool:
    if ctx.level == "observer":
        return False
    if ctx.level == "org_admin" or nda["created_by"] == ctx.user_id:
        return True
    owner = await q1(db, "SELECT owner_user_id FROM crm_organizations WHERE id = :c", c=nda["crm_org_id"])
    return bool(owner and owner["owner_user_id"] == ctx.user_id)


async def _require_edit_nda(db, ctx, nda_id: UUID) -> dict:
    require_write(ctx)
    nda = await _nda(db, ctx, nda_id)
    if not await _can_edit_nda(db, ctx, nda):
        raise err(403, "NDA_FORBIDDEN", "Only administrators, the creator or the customer owner can change this NDA.")
    return nda


def _nda_view(row: dict) -> dict:
    row["coverage"] = nda_coverage(row["status"], row["valid_from"], row["valid_to"])
    return row


async def _set_nda_links(db, ctx, nda_id: UUID, opp_ids: list[UUID], project_ids: list[UUID]) -> None:
    await _check_opps(db, ctx, opp_ids)
    await _check_projects(db, ctx, project_ids)
    await x(db, "DELETE FROM nda_links WHERE nda_id = :n", n=nda_id)
    for oid in set(opp_ids):
        await x(db, "INSERT INTO nda_links (organization_id, nda_id, opportunity_id) VALUES (:o, :n, :l)", o=ctx.org_id, n=nda_id, l=oid)
    for pid in set(project_ids):
        await x(db, "INSERT INTO nda_links (organization_id, nda_id, project_id) VALUES (:o, :n, :l)", o=ctx.org_id, n=nda_id, l=pid)


@router.get("/ndas", summary="List NDAs with their current coverage")
async def list_ndas(ctx: CtxDep, db: DbDep, crm_org_id: UUID | None = None, coverage: str | None = Query(default=None, max_length=14)) -> list[dict]:
    rows = await q(
        db,
        """SELECT n.id, n.number, n.title, n.nda_kind, n.status, n.valid_from, n.valid_to, n.signed_at, n.crm_org_id, co.name AS customer_name
           FROM ndas n JOIN crm_organizations co ON co.id = n.crm_org_id
           WHERE n.organization_id = :o AND n.deleted_at IS NULL AND (CAST(:c AS uuid) IS NULL OR n.crm_org_id = CAST(:c AS uuid)) ORDER BY n.valid_to NULLS LAST, n.created_at DESC LIMIT 500""",
        o=ctx.org_id, c=crm_org_id,
    )
    rows = [_nda_view(r) for r in rows]
    return [r for r in rows if r["coverage"] == coverage] if coverage else rows


@router.get("/nda-coverage", summary="Is there a valid NDA for a customer, opportunity or project?")
async def nda_coverage_for(ctx: CtxDep, db: DbDep, crm_org_id: UUID, opportunity_id: UUID | None = None, project_id: UUID | None = None) -> dict:
    rows = await q(
        db,
        """SELECT n.id, n.number, n.title, n.nda_kind, n.status, n.valid_from, n.valid_to FROM ndas n
           WHERE n.organization_id = :o AND n.deleted_at IS NULL AND (n.crm_org_id = :c
             OR n.id IN (SELECT nda_id FROM nda_links WHERE opportunity_id = CAST(:op AS uuid) OR project_id = CAST(:pr AS uuid)))""",
        o=ctx.org_id, c=crm_org_id, op=opportunity_id, pr=project_id,
    )
    rows = sorted((_nda_view(r) for r in rows), key=lambda r: COVERAGE_RANK[r["coverage"]])
    return {"state": rows[0]["coverage"] if rows else "none", "ndas": rows, "notice": NO_PUBLICATION_RELEASE}


@router.post("/ndas", summary="Create an NDA (draft)")
async def create_nda(body: NdaCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    await check_crm_org(db, ctx, body.crm_org_id)
    _check_range(body.valid_from, body.valid_to)
    number = await next_number(db, ctx.org_id, "NDA")
    row = await q1(
        db,
        """INSERT INTO ndas (organization_id, number, crm_org_id, title, nda_kind, purpose, recipients, valid_from, valid_to, notes, created_by, updated_by)
           VALUES (:o, :n, :c, :t, :k, :p, :r, :vf, :vt, :nt, :u, :u) RETURNING id""",
        o=ctx.org_id, n=number, c=body.crm_org_id, t=body.title.strip(), k=body.nda_kind, p=body.purpose, r=body.recipients, vf=body.valid_from, vt=body.valid_to, nt=body.notes, u=ctx.user_id,
    )
    await _set_nda_links(db, ctx, row["id"], body.opportunity_ids, body.project_ids)
    await audit(db, ctx, "nda.created", "nda", row["id"], f"{number} {body.title}")
    await db.commit()
    return {"id": row["id"], "number": number}


@router.get("/ndas/{nda_id}", summary="NDA detail with links", responses={404: {"description": NDA_NOT_FOUND}})
async def nda_detail(nda_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    nda = await _nda(db, ctx, nda_id)
    customer = await q1(db, "SELECT id, name FROM crm_organizations WHERE id = :c", c=nda["crm_org_id"])
    opps = await q(db, "SELECT o.id, o.number, o.title FROM nda_links l JOIN opportunities o ON o.id = l.opportunity_id AND o.deleted_at IS NULL WHERE l.nda_id = :n ORDER BY o.number", n=nda_id)
    projects = await q(db, "SELECT p.id, p.name FROM nda_links l JOIN projects p ON p.id = l.project_id AND p.deleted_at IS NULL WHERE l.nda_id = :n ORDER BY p.name", n=nda_id)
    signer = await q1(db, "SELECT display_name FROM users WHERE id = :u", u=nda["signed_by_user_id"]) if nda["signed_by_user_id"] else None
    return {
        **_nda_view(dict(nda)), "customer": customer, "opportunities": opps, "projects": projects, "signed_by_name": signer["display_name"] if signer else None,
        "notice": NO_PUBLICATION_RELEASE, "can_edit": await _can_edit_nda(db, ctx, nda),
    }


@router.patch("/ndas/{nda_id}", summary="Update an NDA", responses={403: {"description": "Not allowed"}, 422: {"description": "Invalid dates"}})
async def update_nda(nda_id: UUID, body: NdaUpdate, ctx: CtxDep, db: DbDep) -> dict:
    nda = await _require_edit_nda(db, ctx, nda_id)
    data = body.model_dump(exclude_unset=True)
    for required in ("title", "nda_kind"):
        if required in data and data[required] is None:
            raise err(422, "VALIDATION_ERROR", f"{required} cannot be empty.", required)
    _check_range(data.get("valid_from", nda["valid_from"]), data.get("valid_to", nda["valid_to"]))
    sets, params = set_clause(data, {"title", "nda_kind", "purpose", "recipients", "valid_from", "valid_to", "notes"})
    if sets:
        await x(db, f"UPDATE ndas SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=nda_id, u=ctx.user_id, **params)  # noqa: S608
        await audit(db, ctx, "nda.updated", "nda", nda_id, nda["number"], {"fields": sorted(data)})
    await db.commit()
    return {"ok": True}


@router.put("/ndas/{nda_id}/links", summary="Replace the opportunities and projects an NDA covers")
async def set_nda_links(nda_id: UUID, body: NdaLinks, ctx: CtxDep, db: DbDep) -> dict:
    nda = await _require_edit_nda(db, ctx, nda_id)
    await _set_nda_links(db, ctx, nda_id, body.opportunity_ids, body.project_ids)
    await audit(db, ctx, "nda.links_changed", "nda", nda_id, nda["number"])
    await db.commit()
    return {"ok": True}


@router.post("/ndas/{nda_id}/sign", summary="Record the signature of an NDA", responses={403: {"description": "No signature authority"}, 409: {"description": "Already signed"}, 422: {"description": "Note required"}})
async def sign_nda(nda_id: UUID, body: SignBody, ctx: CtxDep, db: DbDep) -> dict:
    nda = await _require_edit_nda(db, ctx, nda_id)
    if nda["status"] in ("signed", "terminated"):
        raise err(409, "NDA_FINAL", "This NDA is already signed or terminated.")
    auth = await check_authority(db, ctx, "nda_signature", value=None, category=None, risk=None, circle_id=None, override_note=body.override_note)
    signed_at = body.signed_at or date.today()
    await x(
        db,
        """UPDATE ndas SET status = 'signed', signed_at = :sa, signed_by_user_id = :u, signatory_name = :sn, valid_from = COALESCE(valid_from, :sa),
               updated_at = NOW(), updated_by = :u WHERE id = :i""",
        sa=signed_at, u=ctx.user_id, sn=body.signatory_name, i=nda_id,
    )
    await audit(db, ctx, "nda.signed", "nda", nda_id, f"{nda['number']} signed", {"override": auth["override"], "override_note": body.override_note if auth["override"] else None})
    await db.commit()
    return {"ok": True, "admin_override": auth["override"]}


@router.post("/ndas/{nda_id}/terminate", summary="Terminate an NDA")
async def terminate_nda(nda_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    nda = await _require_edit_nda(db, ctx, nda_id)
    await x(db, "UPDATE ndas SET status = 'terminated', updated_at = NOW(), updated_by = :u WHERE id = :i", u=ctx.user_id, i=nda_id)
    await audit(db, ctx, "nda.terminated", "nda", nda_id, nda["number"])
    await db.commit()
    return {"ok": True}


@router.delete("/ndas/{nda_id}", summary="Delete an unsigned NDA (soft)", responses={409: {"description": "Signed NDAs are terminated, not deleted"}})
async def delete_nda(nda_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    nda = await _require_edit_nda(db, ctx, nda_id)
    if nda["status"] == "signed":
        raise err(409, "NDA_SIGNED", "A signed NDA cannot be deleted. Terminate it instead.")
    await x(db, "UPDATE ndas SET deleted_at = NOW(), updated_by = :u WHERE id = :i", u=ctx.user_id, i=nda_id)
    await audit(db, ctx, "nda.deleted", "nda", nda_id, nda["number"])
    await db.commit()
    return {"ok": True}


# ------------------------------------------------------------- contracts


async def _contract(db, ctx, contract_id: UUID) -> dict:
    row = await q1(db, "SELECT * FROM contracts WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=contract_id, o=ctx.org_id)
    if row is None:
        raise err(404, "CONTRACT_NOT_FOUND", CONTRACT_NOT_FOUND)
    return row


async def _signature_role(db, ctx) -> bool:
    held = {str(r) for r in await held_role_ids(db, ctx)}
    return any(str(r["role_id"]) in held for r in await load_rules(db, ctx, "contract_signature"))


async def _can_edit_contract(db, ctx, c: dict) -> bool:
    if ctx.level == "observer":
        return False
    if ctx.level == "org_admin" or ctx.user_id in (c["owner_user_id"], c["created_by"]):
        return True
    if c["opportunity_id"]:
        opp = await q1(db, "SELECT * FROM opportunities WHERE id = :i", i=c["opportunity_id"])
        return bool(opp and await on_opp_team(db, ctx, opp))
    return False


async def _can_see_terms(db, ctx, c: dict) -> bool:
    return await _can_edit_contract(db, ctx, c) or (ctx.level != "observer" and await _signature_role(db, ctx))


async def _require_edit_contract(db, ctx, contract_id: UUID) -> dict:
    require_write(ctx)
    c = await _contract(db, ctx, contract_id)
    if not await _can_edit_contract(db, ctx, c):
        raise err(403, "CONTRACT_FORBIDDEN", "Only administrators, the owner or the opportunity team can change this contract.")
    return c


def _contract_view(row: dict) -> dict:
    row["state"] = contract_state(row["status"], row["valid_from"], row["valid_to"])
    return row


async def _check_parent(db, ctx, parent_id: UUID | None, crm_org_id: UUID, own_id: UUID | None = None) -> None:
    if parent_id is None:
        return
    if own_id is not None and parent_id == own_id:
        raise err(422, "PARENT_CYCLE", "A contract cannot be its own parent.", "parent_contract_id")
    parent = await _contract(db, ctx, parent_id)
    if parent["contract_kind"] != "framework":
        raise err(422, "PARENT_NOT_FRAMEWORK", "The parent must be a framework agreement.", "parent_contract_id")
    if parent["crm_org_id"] != crm_org_id:
        raise err(422, "PARENT_OTHER_CUSTOMER", "A call-off must belong to the same customer as its framework agreement.", "parent_contract_id")


@router.get("/contracts", summary="List contracts (conditions only where permitted)")
async def list_contracts(ctx: CtxDep, db: DbDep, crm_org_id: UUID | None = None, kind: ContractKind | None = None, state: str | None = Query(default=None, max_length=12)) -> list[dict]:
    sig = ctx.level != "observer" and await _signature_role(db, ctx)
    rows = await q(
        db,
        """SELECT c.id, c.number, c.title, c.contract_kind, c.status, c.valid_from, c.valid_to, c.value_amount, c.currency, c.crm_org_id, co.name AS customer_name,
                  c.parent_contract_id, c.opportunity_id, c.owner_user_id, c.created_by,
                  (SELECT COUNT(*) FROM contract_projects cp WHERE cp.contract_id = c.id) AS project_count,
                  EXISTS (SELECT 1 FROM opportunity_team t WHERE t.opportunity_id = c.opportunity_id AND t.user_id = :u) AS team_member
           FROM contracts c JOIN crm_organizations co ON co.id = c.crm_org_id
           WHERE c.organization_id = :o AND c.deleted_at IS NULL AND (CAST(:cu AS uuid) IS NULL OR c.crm_org_id = CAST(:cu AS uuid))
             AND (CAST(:k AS text) IS NULL OR c.contract_kind = CAST(:k AS text)) ORDER BY c.valid_to NULLS LAST, c.created_at DESC LIMIT 500""",
        o=ctx.org_id, u=ctx.user_id, cu=crm_org_id, k=kind,
    )
    out = []
    for r in rows:
        allowed = ctx.level != "observer" and (ctx.level == "org_admin" or sig or r["team_member"] or ctx.user_id in (r["owner_user_id"], r["created_by"]))
        if not allowed:
            r["value_amount"] = None
        r["terms_visible"] = bool(allowed)
        for key in ("team_member", "created_by"):
            r.pop(key, None)
        out.append(_contract_view(r))
    return [r for r in out if r["state"] == state] if state else out


@router.post("/contracts", summary="Create a contract (draft)", responses={404: {"description": "Reference not found"}, 422: {"description": "Invalid parent or dates"}})
async def create_contract(body: ContractCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    await check_crm_org(db, ctx, body.crm_org_id)
    await check_member(db, ctx, body.owner_user_id, "owner_user_id")
    _check_range(body.valid_from, body.valid_to)
    await _check_parent(db, ctx, body.parent_contract_id, body.crm_org_id)
    if body.opportunity_id:
        await _check_opps(db, ctx, [body.opportunity_id])
    if body.proposal_id:
        prop = await q1(db, "SELECT opportunity_id FROM proposals WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=body.proposal_id, o=ctx.org_id)
        if prop is None:
            raise err(404, "PROPOSAL_NOT_FOUND", "Proposal not found.", "proposal_id")
        if body.opportunity_id and prop["opportunity_id"] != body.opportunity_id:
            raise err(422, "PROPOSAL_MISMATCH", "The proposal belongs to a different opportunity.", "proposal_id")
    await _check_projects(db, ctx, body.project_ids)
    number = await next_number(db, ctx.org_id, "CON")
    row = await q1(
        db,
        """INSERT INTO contracts (organization_id, number, crm_org_id, title, contract_kind, parent_contract_id, opportunity_id, proposal_id, value_amount, currency,
                                  valid_from, valid_to, notice_period_days, auto_renew, owner_user_id, notes, created_by, updated_by)
           VALUES (:o, :n, :c, :t, :k, :pa, :op, :pr, :v, :cu, :vf, :vt, :np, :ar, :ow, :nt, :u, :u) RETURNING id""",
        o=ctx.org_id, n=number, c=body.crm_org_id, t=body.title.strip(), k=body.contract_kind, pa=body.parent_contract_id, op=body.opportunity_id, pr=body.proposal_id,
        v=body.value_amount, cu=body.currency, vf=body.valid_from, vt=body.valid_to, np=body.notice_period_days, ar=body.auto_renew, ow=body.owner_user_id or ctx.user_id, nt=body.notes, u=ctx.user_id,
    )
    for pid in set(body.project_ids):
        await x(db, "INSERT INTO contract_projects (organization_id, contract_id, project_id) VALUES (:o, :c, :p)", o=ctx.org_id, c=row["id"], p=pid)
    await audit(db, ctx, "contract.created", "contract", row["id"], f"{number} {body.title}")
    await db.commit()
    return {"id": row["id"], "number": number}


@router.get("/contracts/{contract_id}", summary="Contract detail", responses={404: {"description": CONTRACT_NOT_FOUND}})
async def contract_detail(contract_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    c = await _contract(db, ctx, contract_id)
    terms = await _can_see_terms(db, ctx, c)
    customer = await q1(db, "SELECT id, name FROM crm_organizations WHERE id = :c", c=c["crm_org_id"])
    parent = await q1(db, "SELECT id, number, title FROM contracts WHERE id = :p AND deleted_at IS NULL", p=c["parent_contract_id"]) if c["parent_contract_id"] else None
    children = await q(db, "SELECT id, number, title, status, valid_from, valid_to FROM contracts WHERE parent_contract_id = :c AND deleted_at IS NULL ORDER BY number", c=contract_id)
    projects = await q(db, "SELECT p.id, p.name, p.phase FROM contract_projects cp JOIN projects p ON p.id = cp.project_id AND p.deleted_at IS NULL WHERE cp.contract_id = :c ORDER BY p.name", c=contract_id)
    opp = await q1(db, "SELECT id, number, title FROM opportunities WHERE id = :o AND deleted_at IS NULL", o=c["opportunity_id"]) if c["opportunity_id"] else None
    prop = await q1(db, "SELECT id, number, title FROM proposals WHERE id = :p AND deleted_at IS NULL", p=c["proposal_id"]) if c["proposal_id"] else None
    milestones = await q(db, "SELECT m.id, m.title, m.due_date, m.amount, m.currency, m.status, m.project_id, p.name AS project_name FROM contract_milestones m LEFT JOIN projects p ON p.id = m.project_id WHERE m.contract_id = :c ORDER BY m.due_date NULLS LAST", c=contract_id)
    amendments = await q(db, "SELECT id, title, description, effective_date, value_delta, new_valid_to, signed, created_at FROM contract_amendments WHERE contract_id = :c ORDER BY created_at", c=contract_id)
    signer = await q1(db, "SELECT display_name FROM users WHERE id = :u", u=c["signed_by_user_id"]) if c["signed_by_user_id"] else None
    owner = await q1(db, "SELECT display_name FROM users WHERE id = :u", u=c["owner_user_id"]) if c["owner_user_id"] else None
    view = _contract_view(dict(c))
    if not terms:
        for key in ("value_amount", "notes"):
            view[key] = None
        milestones = [{**m, "amount": None} for m in milestones]
        amendments = [{**a, "value_delta": None, "description": ""} for a in amendments]
    elif ctx.level == "observer":
        strip_money(view, ctx)
    return {
        **view, "customer": customer, "parent": parent, "children": children, "projects": projects, "opportunity": opp, "proposal": prop, "milestones": milestones,
        "amendments": amendments, "signed_by_name": signer["display_name"] if signer else None, "owner_name": owner["display_name"] if owner else None,
        "terms_visible": terms, "can_edit": await _can_edit_contract(db, ctx, c),
    }


@router.patch("/contracts/{contract_id}", summary="Update a contract", responses={409: {"description": "Signed - use an amendment"}, 403: {"description": "Not allowed"}})
async def update_contract(contract_id: UUID, body: ContractUpdate, ctx: CtxDep, db: DbDep) -> dict:
    c = await _require_edit_contract(db, ctx, contract_id)
    data = body.model_dump(exclude_unset=True)
    for required in ("title", "contract_kind", "currency", "auto_renew"):
        if required in data and data[required] is None:
            raise err(422, "VALIDATION_ERROR", f"{required} cannot be empty.", required)
    if c["status"] == "signed" and {"value_amount", "valid_from", "valid_to", "currency", "contract_kind"} & data.keys():
        raise err(409, "USE_AMENDMENT", "Value, term and kind of a signed contract change through an amendment.")
    if "owner_user_id" in data:
        await check_member(db, ctx, data["owner_user_id"], "owner_user_id")
    _check_range(data.get("valid_from", c["valid_from"]), data.get("valid_to", c["valid_to"]))
    sets, params = set_clause(data, {"title", "contract_kind", "value_amount", "currency", "valid_from", "valid_to", "notice_period_days", "auto_renew", "owner_user_id", "notes"})
    if sets:
        await x(db, f"UPDATE contracts SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=contract_id, u=ctx.user_id, **params)  # noqa: S608
        await audit(db, ctx, "contract.updated", "contract", contract_id, c["number"], {"fields": sorted(data)})
    await db.commit()
    return {"ok": True}


@router.put("/contracts/{contract_id}/projects", summary="Replace the projects a contract covers")
async def set_contract_projects(contract_id: UUID, body: ProjectIds, ctx: CtxDep, db: DbDep) -> dict:
    c = await _require_edit_contract(db, ctx, contract_id)
    await _check_projects(db, ctx, body.project_ids)
    await x(db, "DELETE FROM contract_projects WHERE contract_id = :c", c=contract_id)
    for pid in set(body.project_ids):
        await x(db, "INSERT INTO contract_projects (organization_id, contract_id, project_id) VALUES (:o, :c, :p)", o=ctx.org_id, c=contract_id, p=pid)
    await audit(db, ctx, "contract.projects_changed", "contract", contract_id, c["number"])
    await db.commit()
    return {"ok": True}


@router.post("/contracts/{contract_id}/sign", summary="Record the signature of a contract", responses={403: {"description": "No signature authority"}, 409: {"description": "Already signed"}})
async def sign_contract(contract_id: UUID, body: SignBody, ctx: CtxDep, db: DbDep) -> dict:
    c = await _require_edit_contract(db, ctx, contract_id)
    if c["status"] in ("signed", "terminated"):
        raise err(409, "CONTRACT_FINAL", "This contract is already signed or terminated.")
    opp = await q1(db, "SELECT category, risk, circle_id FROM opportunities WHERE id = :i", i=c["opportunity_id"]) if c["opportunity_id"] else None
    auth = await check_authority(
        db, ctx, "contract_signature", value=c["value_amount"], category=opp["category"] if opp else None, risk=opp["risk"] if opp else None,
        circle_id=opp["circle_id"] if opp else None, override_note=body.override_note,
    )
    signed_at = body.signed_at or date.today()
    await x(
        db,
        """UPDATE contracts SET status = 'signed', signed_at = :sa, signed_by_user_id = :u, signatory_name = :sn, valid_from = COALESCE(valid_from, :sa),
               updated_at = NOW(), updated_by = :u WHERE id = :i""",
        sa=signed_at, u=ctx.user_id, sn=body.signatory_name, i=contract_id,
    )
    await audit(db, ctx, "contract.signed", "contract", contract_id, f"{c['number']} signed", {"override": auth["override"], "override_note": body.override_note if auth["override"] else None})
    await db.commit()
    return {"ok": True, "admin_override": auth["override"]}


@router.post("/contracts/{contract_id}/terminate", summary="Terminate a contract")
async def terminate_contract(contract_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    c = await _require_edit_contract(db, ctx, contract_id)
    await x(db, "UPDATE contracts SET status = 'terminated', updated_at = NOW(), updated_by = :u WHERE id = :i", u=ctx.user_id, i=contract_id)
    await audit(db, ctx, "contract.terminated", "contract", contract_id, c["number"])
    await db.commit()
    return {"ok": True}


@router.delete("/contracts/{contract_id}", summary="Delete an unsigned contract (soft)", responses={409: {"description": "Signed contracts are terminated, not deleted"}})
async def delete_contract(contract_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    c = await _require_edit_contract(db, ctx, contract_id)
    if c["status"] == "signed":
        raise err(409, "CONTRACT_SIGNED", "A signed contract cannot be deleted. Terminate it instead.")
    await x(db, "UPDATE contracts SET deleted_at = NOW(), updated_by = :u WHERE id = :i", u=ctx.user_id, i=contract_id)
    await audit(db, ctx, "contract.deleted", "contract", contract_id, c["number"])
    await db.commit()
    return {"ok": True}


@router.post("/contracts/{contract_id}/milestones", summary="Add a payment milestone")
async def add_milestone(contract_id: UUID, body: MilestoneBody, ctx: CtxDep, db: DbDep) -> dict:
    await _require_edit_contract(db, ctx, contract_id)
    if body.project_id:
        await _check_projects(db, ctx, [body.project_id], "project_id")
    row = await q1(
        db,
        "INSERT INTO contract_milestones (organization_id, contract_id, project_id, title, due_date, amount, currency, status) VALUES (:o, :c, :p, :t, :d, :a, :cu, :s) RETURNING id",
        o=ctx.org_id, c=contract_id, p=body.project_id, t=body.title, d=body.due_date, a=body.amount, cu=body.currency, s=body.status,
    )
    await db.commit()
    return {"id": row["id"]}


@router.patch("/contracts/{contract_id}/milestones/{milestone_id}", summary="Update a payment milestone", responses={404: {"description": "Milestone not found"}})
async def update_milestone(contract_id: UUID, milestone_id: UUID, body: MilestoneUpdate, ctx: CtxDep, db: DbDep) -> dict:
    await _require_edit_contract(db, ctx, contract_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("project_id"):
        await _check_projects(db, ctx, [data["project_id"]], "project_id")
    sets, params = set_clause(data, {"title", "due_date", "amount", "project_id", "status"})
    if sets:
        got = await q(db, f"UPDATE contract_milestones SET {sets} WHERE id = :id AND contract_id = :c RETURNING id", id=milestone_id, c=contract_id, **params)  # noqa: S608
        if not got:
            raise err(404, "MILESTONE_NOT_FOUND", "Milestone not found.")
    await db.commit()
    return {"ok": True}


@router.delete("/contracts/{contract_id}/milestones/{milestone_id}", summary="Remove a payment milestone")
async def delete_milestone(contract_id: UUID, milestone_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    await _require_edit_contract(db, ctx, contract_id)
    await x(db, "DELETE FROM contract_milestones WHERE id = :id AND contract_id = :c", id=milestone_id, c=contract_id)
    await db.commit()
    return {"ok": True}


@router.post("/contracts/{contract_id}/amendments", summary="Add an amendment; a signed amendment adjusts value and term")
async def add_amendment(contract_id: UUID, body: AmendmentBody, ctx: CtxDep, db: DbDep) -> dict:
    c = await _require_edit_contract(db, ctx, contract_id)
    row = await q1(
        db,
        """INSERT INTO contract_amendments (organization_id, contract_id, title, description, effective_date, value_delta, new_valid_to, signed, created_by)
           VALUES (:o, :c, :t, :d, :e, :v, :n, :s, :u) RETURNING id""",
        o=ctx.org_id, c=contract_id, t=body.title, d=body.description, e=body.effective_date, v=body.value_delta, n=body.new_valid_to, s=body.signed, u=ctx.user_id,
    )
    if body.signed:
        new_value = (Decimal(str(c["value_amount"] or 0)) + body.value_delta) if body.value_delta is not None else c["value_amount"]
        if new_value is not None and Decimal(str(new_value)) < 0:
            raise err(422, "NEGATIVE_VALUE", "The amendment would make the contract value negative.", "value_delta")
        _check_range(c["valid_from"], body.new_valid_to or c["valid_to"], "new_valid_to")
        await x(db, "UPDATE contracts SET value_amount = :v, valid_to = COALESCE(:vt, valid_to), updated_at = NOW(), updated_by = :u WHERE id = :i", v=new_value, vt=body.new_valid_to, u=ctx.user_id, i=contract_id)
    await audit(db, ctx, "contract.amended", "contract", contract_id, f"{c['number']}: {body.title}", {"signed": body.signed})
    await db.commit()
    return {"id": row["id"]}


# ------------------------------------------------------------- reminders


async def _reminder_items(db, ctx, today: date) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    ndas = await q(db, "SELECT id, number, title, valid_to, created_by FROM ndas WHERE organization_id = :o AND deleted_at IS NULL AND status = 'signed' AND valid_to IS NOT NULL", o=ctx.org_id)
    for n in ndas:
        for kind, due in reminder_dates(n["valid_to"], None, today, REMINDER_WINDOW_DAYS):
            items.append({"entity_type": "nda", "entity_id": n["id"], "kind": kind, "due_date": due, "number": n["number"], "title": n["title"], "owner_user_id": n["created_by"], "link": f"/sales/ndas/{n['id']}"})
    contracts = await q(db, "SELECT id, number, title, valid_to, notice_period_days, owner_user_id, created_by FROM contracts WHERE organization_id = :o AND deleted_at IS NULL AND status = 'signed' AND valid_to IS NOT NULL", o=ctx.org_id)
    for c in contracts:
        for kind, due in reminder_dates(c["valid_to"], c["notice_period_days"], today, REMINDER_WINDOW_DAYS):
            items.append({"entity_type": "contract", "entity_id": c["id"], "kind": kind, "due_date": due, "number": c["number"], "title": c["title"], "owner_user_id": c["owner_user_id"] or c["created_by"], "link": f"/sales/contracts/{c['id']}"})
    stones = await q(
        db,
        """SELECT m.id, m.title, m.due_date, c.number, c.owner_user_id, c.created_by, c.id AS contract_id FROM contract_milestones m JOIN contracts c ON c.id = m.contract_id AND c.deleted_at IS NULL
           WHERE m.organization_id = :o AND m.status = 'planned' AND m.due_date IS NOT NULL AND m.due_date <= :lim""",
        o=ctx.org_id, lim=today + timedelta(days=MILESTONE_WINDOW_DAYS),
    )
    for m in stones:
        items.append({"entity_type": "milestone", "entity_id": m["id"], "kind": "overdue" if m["due_date"] < today else "due_soon", "due_date": m["due_date"], "number": m["number"], "title": m["title"], "owner_user_id": m["owner_user_id"] or m["created_by"], "link": f"/sales/contracts/{m['contract_id']}"})
    return sorted(items, key=lambda i: i["due_date"])


@router.get("/reminders", summary="Upcoming expiries, notice deadlines and payment milestones")
async def reminders(ctx: CtxDep, db: DbDep) -> list[dict]:
    return await _reminder_items(db, ctx, date.today())


@router.post("/reminders/run", summary="Send each due reminder once as a notification")
async def run_reminders(ctx: CtxDep, db: DbDep) -> dict:
    if ctx.level == "observer":
        return {"sent": 0}
    admins = [r["user_id"] for r in await q(db, "SELECT user_id FROM memberships WHERE organization_id = :o AND access_level = 'org_admin' AND active", o=ctx.org_id)]
    sent = 0
    for item in await _reminder_items(db, ctx, date.today()):
        fresh = await q1(
            db,
            """INSERT INTO commercial_reminders (organization_id, entity_type, entity_id, kind, due_date) VALUES (:o, :t, :e, :k, :d)
               ON CONFLICT (entity_type, entity_id, kind, due_date) DO NOTHING RETURNING id""",
            o=ctx.org_id, t=item["entity_type"], e=item["entity_id"], k=item["kind"], d=item["due_date"],
        )
        if fresh is None:
            continue
        sent += 1
        who = [item["owner_user_id"]] if item["owner_user_id"] else admins
        title = f"{item['number']}: {item['kind'].replace('_', ' ')} on {item['due_date']}"
        await notify(db, ctx.org_id, who, "task", title, item["title"], item["link"])
    await db.commit()
    return {"sent": sent}
