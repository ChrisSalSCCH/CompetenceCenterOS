"""Project portfolio: internal and customer projects with structured, searchable knowledge.

Builds on the existing `projects` entity (tasks, milestones and OKRs stay attached to it).
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from routes.work import _can_manage_project, _project, project_detail
from services.ctx import CtxDep, require_admin, require_circle, require_write
from services.dbx import DbDep, err, q, q1, set_clause, x
from services.events import audit
from services.portfolio import (
    CALCULATED_FIELDS,
    KNOWLEDGE_SECTIONS,
    can_set_verification,
    customer_rule_violated,
    finance_metrics,
    knowledge_completeness,
    normalize_communication,
    public_reference,
)

router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])

Classification = Literal["internal", "customer"]
Category = Literal["research", "development", "consulting", "innovation", "operations", "other"]
Phase = Literal["idea", "proposal", "running", "closing", "completed", "archived"]
ProjectStatusT = Literal["planned", "active", "on_hold", "done", "cancelled"]
PriorityT = Literal["low", "medium", "high"]
OrgRelation = Literal["customer", "partner", "research_partner", "funder", "subcontractor", "other"]
KnowledgeSection = Literal["business_context", "solution", "challenges", "results", "reuse", "architecture", "ai_usage"]
Verification = Literal["unverified", "verified", "ai_draft", "approved"]
Money = Decimal
NOT_ALLOWED = "Only administrators, the project manager or the project team can change this project."


class PortfolioCreate(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=10000)
    circle_id: UUID
    classification: Classification = "internal"
    category: Category = "other"
    phase: Phase = "running"
    status: ProjectStatusT = "planned"
    priority: PriorityT = "medium"
    short_name: str | None = Field(default=None, max_length=60)
    project_no: str | None = Field(default=None, max_length=40)
    org_unit: str | None = Field(default=None, max_length=120)
    manager_id: UUID | None = None
    owning_role_id: UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    is_research: bool = False
    funding_program: str | None = Field(default=None, max_length=160)
    funding_agency: str | None = Field(default=None, max_length=160)
    funding_ref: str | None = Field(default=None, max_length=80)
    research_note: str = Field(default="", max_length=5000)
    ai_relevant: bool = False
    customer_org_ids: list[UUID] = Field(default_factory=list, max_length=20)
    entry_ids: list[UUID] = Field(default_factory=list, max_length=60)


class PortfolioUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    classification: Classification | None = None
    category: Category | None = None
    phase: Phase | None = None
    status: ProjectStatusT | None = None
    priority: PriorityT | None = None
    short_name: str | None = Field(default=None, max_length=60)
    project_no: str | None = Field(default=None, max_length=40)
    org_unit: str | None = Field(default=None, max_length=120)
    manager_id: UUID | None = None
    owning_role_id: UUID | None = None
    start_date: date | None = None
    due_date: date | None = None
    is_research: bool | None = None
    funding_program: str | None = Field(default=None, max_length=160)
    funding_agency: str | None = Field(default=None, max_length=160)
    funding_ref: str | None = Field(default=None, max_length=80)
    research_note: str | None = Field(default=None, max_length=5000)
    ai_relevant: bool | None = None


class OrgLink(BaseModel):
    crm_org_id: UUID
    relation: OrgRelation = "customer"


class OrgLinks(BaseModel):
    items: list[OrgLink] = Field(max_length=40)


class ContactLink(BaseModel):
    contact_id: UUID
    contact_role: str | None = Field(default=None, max_length=60)


class ContactLinks(BaseModel):
    items: list[ContactLink] = Field(max_length=60)


class EntryLink(BaseModel):
    entry_id: UUID
    usage_note: str | None = Field(default=None, max_length=300)


class EntryLinks(BaseModel):
    items: list[EntryLink] = Field(max_length=80)


class KnowledgeBody(BaseModel):
    content: str | None = Field(default=None, max_length=20000)
    verification: Verification | None = None


class WorkPackageBody(BaseModel):
    code: str = Field(default="", max_length=20)
    title: str = Field(min_length=1, max_length=200)
    description: str = Field(default="", max_length=5000)
    status: Literal["planned", "active", "done"] = "planned"
    start_date: date | None = None
    end_date: date | None = None
    lead_user_id: UUID | None = None


class WorkPackageUpdate(BaseModel):
    code: str | None = Field(default=None, max_length=20)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    status: Literal["planned", "active", "done"] | None = None
    start_date: date | None = None
    end_date: date | None = None
    lead_user_id: UUID | None = None


class ResultBody(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["deliverable", "kpi", "publication", "prototype", "other"] = "deliverable"
    work_package_id: UUID | None = None
    planned_value: str | None = Field(default=None, max_length=200)
    demonstrated_value: str | None = Field(default=None, max_length=200)
    unit: str | None = Field(default=None, max_length=30)
    evidence_url: str | None = Field(default=None, max_length=1000, pattern=r"^https?://")
    status: Literal["planned", "achieved", "partial", "missed"] = "planned"


class ResultUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    kind: Literal["deliverable", "kpi", "publication", "prototype", "other"] | None = None
    work_package_id: UUID | None = None
    planned_value: str | None = Field(default=None, max_length=200)
    demonstrated_value: str | None = Field(default=None, max_length=200)
    unit: str | None = Field(default=None, max_length=30)
    evidence_url: str | None = Field(default=None, max_length=1000, pattern=r"^https?://")
    status: Literal["planned", "achieved", "partial", "missed"] | None = None


class FinanceBody(BaseModel):
    budget_total: Money | None = Field(default=None, ge=0, le=Decimal("999999999999"))
    budget_funding: Money | None = Field(default=None, ge=0, le=Decimal("999999999999"))
    budget_own: Money | None = Field(default=None, ge=0, le=Decimal("999999999999"))
    costs_to_date: Money | None = Field(default=None, ge=0, le=Decimal("999999999999"))
    revenue_expected: Money | None = Field(default=None, ge=0, le=Decimal("999999999999"))
    currency: str = Field(default="EUR", pattern=r"^[A-Z]{3}$")
    reporting_cycle: Literal["none", "monthly", "quarterly", "semiannual", "yearly"] = "none"
    next_report_due: date | None = None
    last_report_at: date | None = None
    notes: str = Field(default="", max_length=5000)


class FinanceViewers(BaseModel):
    user_ids: list[UUID] = Field(max_length=30)


class CommunicationBody(BaseModel):
    reference_allowed: bool = False
    allow_name: bool = False
    allow_logo: bool = False
    allow_images: bool = False
    allow_description: bool = False
    allow_results: bool = False
    approved_by_name: str | None = Field(default=None, max_length=160)
    approved_at: date | None = None
    notes: str = Field(default="", max_length=3000)


class RelationLink(BaseModel):
    related_project_id: UUID
    relation: Literal["follow_up", "predecessor", "reuses", "related"] = "related"
    note: str | None = Field(default=None, max_length=300)


class RelationLinks(BaseModel):
    items: list[RelationLink] = Field(max_length=40)


class DocumentBody(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    url: str = Field(min_length=8, max_length=1000, pattern=r"^https?://")


# ---------------------------------------------------------------- helpers


async def _can_edit(db, ctx, p: dict) -> bool:
    return await _can_manage_project(db, ctx, p) or (ctx.level != "observer" and p.get("manager_id") == ctx.user_id)


async def _require_edit(db, ctx, project_id: UUID) -> dict:
    require_write(ctx)
    p = await _project(db, ctx, project_id)
    if not await _can_edit(db, ctx, p):
        raise err(403, "PROJECT_FORBIDDEN", NOT_ALLOWED)
    return p


def _is_finance_owner(ctx, p: dict) -> bool:
    return ctx.level == "org_admin" or p.get("manager_id") == ctx.user_id


async def _can_view_finance(db, ctx, p: dict) -> bool:
    if _is_finance_owner(ctx, p):
        return True
    row = await q1(db, "SELECT 1 AS ok FROM project_finance_viewers WHERE project_id = :p AND user_id = :u", p=p["id"], u=ctx.user_id)
    return row is not None


async def _check_entries(db, ctx, ids: list[UUID]) -> None:
    for eid in set(ids):
        row = await q1(db, "SELECT 1 AS ok FROM catalog_entries WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=eid, o=ctx.org_id)
        if row is None:
            raise err(404, "CATALOG_ENTRY_NOT_FOUND", "Catalog entry not found.", "entry_ids")


async def _check_crm_orgs(db, ctx, ids: list[UUID]) -> None:
    for oid in set(ids):
        row = await q1(db, "SELECT 1 AS ok FROM crm_organizations WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=oid, o=ctx.org_id)
        if row is None:
            raise err(404, "CRM_ORG_NOT_FOUND", "Customer organization not found.", "customer_org_ids")


async def _check_member(db, ctx, user_id: UUID | None, field: str) -> None:
    if user_id is None:
        return
    row = await q1(db, "SELECT 1 AS ok FROM memberships WHERE user_id = :u AND organization_id = :o AND active", u=user_id, o=ctx.org_id)
    if row is None:
        raise err(404, "PERSON_NOT_FOUND", "Person is not a member of this organization.", field)


async def _customer_count(db, project_id: UUID) -> int:
    row = await q1(db, "SELECT COUNT(*) AS n FROM project_orgs WHERE project_id = :p AND relation = 'customer'", p=project_id)
    return int(row["n"]) if row else 0


def _customer_error() -> Any:
    return err(422, "CUSTOMER_REQUIRED", "A customer project needs at least one linked customer organization.", "customer_org_ids")


# ------------------------------------------------------------------ list


@router.get("", summary="Search and filter the project portfolio")
async def list_portfolio(  # noqa: PLR0913 - one parameter per filter
    ctx: CtxDep,
    db: DbDep,
    search: str | None = Query(default=None, max_length=100),
    classification: Classification | None = None,
    category: Category | None = None,
    phase: Phase | None = None,
    status: str | None = Query(default=None, max_length=20),
    crm_org_id: UUID | None = None,
    manager_id: UUID | None = None,
    org_unit: str | None = Query(default=None, max_length=120),
    entry_ids: list[UUID] = Query(default=[]),
    reference_eligible: bool | None = None,
    is_research: bool | None = None,
) -> list[dict]:
    where = ["p.organization_id = :o", "p.deleted_at IS NULL"]
    params: dict[str, Any] = {"o": ctx.org_id}
    simple = {"classification": classification, "category": category, "phase": phase, "manager_id": manager_id, "org_unit": org_unit}
    for col, val in simple.items():
        if val is not None:
            where.append(f"p.{col} = :{col}")
            params[col] = val
    if status == "open":
        where.append("p.status IN ('planned','active','on_hold')")
    elif status:
        where.append("p.status = :status")
        params["status"] = status
    if is_research is not None:
        where.append("p.is_research = :isr")
        params["isr"] = is_research
    if crm_org_id:
        where.append("EXISTS (SELECT 1 FROM project_orgs po WHERE po.project_id = p.id AND po.crm_org_id = :corg)")
        params["corg"] = crm_org_id
    for i, eid in enumerate(entry_ids):
        where.append(f"EXISTS (SELECT 1 FROM project_catalog_links l{i} WHERE l{i}.project_id = p.id AND l{i}.entry_id = :e{i})")
        params[f"e{i}"] = eid
    if reference_eligible is not None:
        where.append(f"{'' if reference_eligible else 'NOT '}COALESCE((SELECT pc.reference_allowed FROM project_communication pc WHERE pc.project_id = p.id), FALSE)")
    if search:
        where.append(
            """(p.name ILIKE :s OR p.short_name ILIKE :s OR p.project_no ILIKE :s OR p.description ILIKE :s
                OR EXISTS (SELECT 1 FROM project_catalog_links l JOIN catalog_entries e ON e.id = l.entry_id
                           LEFT JOIN catalog_aliases a ON a.entry_id = e.id
                           WHERE l.project_id = p.id AND (e.name ILIKE :s OR a.alias ILIKE :s))
                OR EXISTS (SELECT 1 FROM project_orgs po JOIN crm_organizations co ON co.id = po.crm_org_id WHERE po.project_id = p.id AND co.name ILIKE :s))"""
        )
        params["s"] = f"%{search.strip()}%"
    return await q(
        db,
        f"""SELECT p.id, p.name, p.short_name, p.project_no, p.classification, p.category, p.phase, p.status, p.priority,
                   p.start_date, p.due_date, p.org_unit, p.is_research, p.ai_relevant, p.circle_id, c.name AS circle_name,
                   p.manager_id, u.display_name AS manager_name,
                   COALESCE((SELECT json_agg(json_build_object('id', co.id, 'name', co.name) ORDER BY co.name) FROM project_orgs po JOIN crm_organizations co ON co.id = po.crm_org_id
                             WHERE po.project_id = p.id AND po.relation = 'customer'), '[]'::json) AS customers,
                   COALESCE((SELECT json_agg(json_build_object('id', e.id, 'name', e.name, 'kind', e.kind) ORDER BY e.name) FROM project_catalog_links l JOIN catalog_entries e ON e.id = l.entry_id AND e.deleted_at IS NULL
                             WHERE l.project_id = p.id), '[]'::json) AS entries,
                   COALESCE((SELECT pc.reference_allowed FROM project_communication pc WHERE pc.project_id = p.id), FALSE) AS reference_allowed,
                   (SELECT COUNT(*) FROM project_knowledge k WHERE k.project_id = p.id AND k.content <> '') AS knowledge_filled,
                   (SELECT COUNT(*) FROM project_knowledge k WHERE k.project_id = p.id AND k.content <> '' AND k.verification IN ('verified','approved')) AS knowledge_verified,
                   (SELECT COUNT(*) FROM project_knowledge k WHERE k.project_id = p.id AND k.content <> '' AND k.verification IN ('unverified','ai_draft')) AS knowledge_review
            FROM projects p JOIN circles c ON c.id = p.circle_id LEFT JOIN users u ON u.id = p.manager_id
            WHERE {' AND '.join(where)} ORDER BY (p.phase IN ('completed','archived')), p.name LIMIT 500""",  # noqa: S608 - constants only
        **params,
    )


@router.get("/references", summary="Projects released as references - only the permitted content")
async def references(
    ctx: CtxDep, db: DbDep, entry_ids: list[UUID] = Query(default=[]), industry_id: UUID | None = None
) -> list[dict]:
    where = ["p.organization_id = :o", "p.deleted_at IS NULL", "pc.reference_allowed"]
    params: dict[str, Any] = {"o": ctx.org_id}
    for i, eid in enumerate(entry_ids):
        where.append(f"EXISTS (SELECT 1 FROM project_catalog_links l{i} WHERE l{i}.project_id = p.id AND l{i}.entry_id = :e{i})")
        params[f"e{i}"] = eid
    if industry_id:
        where.append("EXISTS (SELECT 1 FROM project_orgs po JOIN crm_organizations co ON co.id = po.crm_org_id WHERE po.project_id = p.id AND co.industry_entry_id = :ind)")
        params["ind"] = industry_id
    rows = await q(
        db,
        f"""SELECT p.id, p.name, p.description, pc.allow_name, pc.allow_logo, pc.allow_images, pc.allow_description, pc.allow_results,
                   pc.approved_by_name, pc.approved_at,
                   (SELECT i.name FROM project_orgs po JOIN crm_organizations co ON co.id = po.crm_org_id JOIN catalog_entries i ON i.id = co.industry_entry_id
                    WHERE po.project_id = p.id AND po.relation = 'customer' ORDER BY i.name LIMIT 1) AS industry,
                   COALESCE((SELECT json_agg(json_build_object('id', e.id, 'name', e.name, 'kind', e.kind) ORDER BY e.name) FROM project_catalog_links l JOIN catalog_entries e ON e.id = l.entry_id AND e.deleted_at IS NULL
                             WHERE l.project_id = p.id AND e.kind IN ('technology','solution_type','application_domain')), '[]'::json) AS entries
            FROM projects p JOIN project_communication pc ON pc.project_id = p.id WHERE {' AND '.join(where)} ORDER BY p.name""",  # noqa: S608 - constants only
        **params,
    )
    out = []
    for r in rows:
        ref = public_reference(r, r, r["industry"])
        ref.update({"entries": r["entries"], "approved_by_name": r["approved_by_name"], "approved_at": r["approved_at"]})
        out.append(ref)
    return out


# ---------------------------------------------------------------- create


@router.post("", summary="Create a portfolio project", responses={422: {"description": "Customer project without customer organization"}})
async def create_portfolio_project(body: PortfolioCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    if customer_rule_violated(body.classification, len(set(body.customer_org_ids))):
        raise _customer_error()
    await require_circle(db, ctx, body.circle_id)
    await _check_member(db, ctx, body.manager_id, "manager_id")
    await _check_crm_orgs(db, ctx, body.customer_org_ids)
    await _check_entries(db, ctx, body.entry_ids)
    row = await q1(
        db,
        """INSERT INTO projects (organization_id, circle_id, owning_role_id, name, description, status, priority, start_date, due_date,
                                classification, category, phase, short_name, project_no, org_unit, manager_id, is_research,
                                funding_program, funding_agency, funding_ref, research_note, ai_relevant, created_by, updated_by)
           VALUES (:o, :c, :r, :n, :d, :s, :pr, :sd, :dd, :cl, :ca, :ph, :sn, :no, :ou, :m, :rs, :fp, :fa, :fr, :rn, :ai, :u, :u) RETURNING id""",
        o=ctx.org_id, c=body.circle_id, r=body.owning_role_id, n=body.name.strip(), d=body.description, s=body.status, pr=body.priority,
        sd=body.start_date, dd=body.due_date, cl=body.classification, ca=body.category, ph=body.phase, sn=body.short_name, no=body.project_no or None,
        ou=body.org_unit, m=body.manager_id, rs=body.is_research, fp=body.funding_program, fa=body.funding_agency, fr=body.funding_ref,
        rn=body.research_note, ai=body.ai_relevant, u=ctx.user_id,
    )
    pid = row["id"]
    for oid in set(body.customer_org_ids):
        await x(db, "INSERT INTO project_orgs (organization_id, project_id, crm_org_id, relation) VALUES (:o, :p, :c, 'customer')", o=ctx.org_id, p=pid, c=oid)
    for eid in set(body.entry_ids):
        await x(db, "INSERT INTO project_catalog_links (organization_id, project_id, entry_id) VALUES (:o, :p, :e)", o=ctx.org_id, p=pid, e=eid)
    await audit(db, ctx, "project.created", "project", pid, body.name)
    await db.commit()
    return {"id": pid}


# ---------------------------------------------------------------- detail


async def _finance_block(db, ctx, p: dict) -> dict:
    if not await _can_view_finance(db, ctx, p):
        return {"restricted": True, "data": None, "metrics": None, "calculated": CALCULATED_FIELDS, "can_edit": False, "viewers": []}
    fin = await q1(db, "SELECT * FROM project_finance WHERE project_id = :p", p=p["id"])
    viewers = await q(db, "SELECT u.id AS user_id, u.display_name AS name FROM project_finance_viewers v JOIN users u ON u.id = v.user_id WHERE v.project_id = :p ORDER BY u.display_name", p=p["id"])
    return {"restricted": False, "data": fin, "metrics": finance_metrics(fin), "calculated": CALCULATED_FIELDS, "can_edit": _is_finance_owner(ctx, p), "viewers": viewers}


async def _knowledge_block(db, p: dict) -> dict:
    rows = await q(
        db,
        """SELECT k.section, k.content, k.verification, k.verified_at, k.updated_at, u.display_name AS verified_by_name
           FROM project_knowledge k LEFT JOIN users u ON u.id = k.verified_by WHERE k.project_id = :p""",
        p=p["id"],
    )
    by_key = {r["section"]: r for r in rows}
    sections = [by_key.get(s) or {"section": s, "content": "", "verification": "unverified", "verified_at": None, "updated_at": None, "verified_by_name": None} for s in KNOWLEDGE_SECTIONS]
    return {"sections": sections, "completeness": knowledge_completeness(sections, p["ai_relevant"], p["classification"] == "customer")}


@router.get("/{project_id}", summary="Full portfolio detail of a project", responses={404: {"description": "Project not found"}})
async def portfolio_detail(project_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    p = await _project(db, ctx, project_id)
    base = await q1(
        db,
        """SELECT p.*, c.name AS circle_name, u.display_name AS manager_name, r.name AS owning_role_name
           FROM projects p JOIN circles c ON c.id = p.circle_id LEFT JOIN users u ON u.id = p.manager_id LEFT JOIN roles r ON r.id = p.owning_role_id WHERE p.id = :p""",
        p=project_id,
    )
    work = await project_detail(project_id, ctx, db)
    orgs = await q(
        db,
        """SELECT po.crm_org_id AS id, co.name, po.relation, co.relation_types, i.name AS industry
           FROM project_orgs po JOIN crm_organizations co ON co.id = po.crm_org_id AND co.deleted_at IS NULL LEFT JOIN catalog_entries i ON i.id = co.industry_entry_id
           WHERE po.project_id = :p ORDER BY po.relation, co.name""",
        p=project_id,
    )
    contacts = await q(
        db,
        """SELECT c.id, c.first_name, c.last_name, c.job_title, pc.contact_role, c.email, c.phone
           FROM project_contacts pc JOIN crm_contacts c ON c.id = pc.contact_id AND c.deleted_at IS NULL WHERE pc.project_id = :p ORDER BY c.last_name""",
        p=project_id,
    )
    if ctx.level == "observer":
        for c in contacts:
            c["email"] = None
            c["phone"] = None
    entries = await q(
        db,
        """SELECT e.id, e.kind, e.name, e.category, l.usage_note FROM project_catalog_links l JOIN catalog_entries e ON e.id = l.entry_id AND e.deleted_at IS NULL
           WHERE l.project_id = :p ORDER BY e.kind, e.name""",
        p=project_id,
    )
    packages = await q(
        db,
        """SELECT w.id, w.code, w.title, w.description, w.status, w.start_date, w.end_date, w.lead_user_id, u.display_name AS lead_name
           FROM project_work_packages w LEFT JOIN users u ON u.id = w.lead_user_id WHERE w.project_id = :p AND w.deleted_at IS NULL ORDER BY w.position, w.code""",
        p=project_id,
    )
    results = await q(
        db,
        """SELECT r.id, r.title, r.kind, r.work_package_id, r.planned_value, r.demonstrated_value, r.unit, r.evidence_url, r.status
           FROM project_results r WHERE r.project_id = :p AND r.deleted_at IS NULL ORDER BY r.created_at""",
        p=project_id,
    )
    relations = await q(
        db,
        """SELECT pr.related_project_id AS id, rp.name, pr.relation, pr.note, 'outgoing' AS direction FROM project_relations pr
             JOIN projects rp ON rp.id = pr.related_project_id AND rp.deleted_at IS NULL WHERE pr.project_id = :p
           UNION ALL
           SELECT pr.project_id, rp.name, pr.relation, pr.note, 'incoming' FROM project_relations pr
             JOIN projects rp ON rp.id = pr.project_id AND rp.deleted_at IS NULL WHERE pr.related_project_id = :p""",
        p=project_id,
    )
    comm = await q1(db, "SELECT * FROM project_communication WHERE project_id = :p", p=project_id)
    docs = work.get("documents", [])
    role_holders = await q(
        db,
        """SELECT u.id AS user_id, u.display_name AS name, r.name AS role_name, ra.focus FROM role_assignments ra
             JOIN roles r ON r.id = ra.role_id AND r.deleted_at IS NULL JOIN users u ON u.id = ra.user_id
           WHERE ra.deleted_at IS NULL AND r.id = :r ORDER BY u.display_name""",
        r=p["owning_role_id"],
    ) if p["owning_role_id"] else []
    scoped = await q(
        db,
        """SELECT u.id AS user_id, u.display_name AS name, r.id AS role_id, r.name AS role_name FROM crm_role_scopes s
             JOIN role_assignments ra ON ra.id = s.role_assignment_id AND ra.deleted_at IS NULL JOIN roles r ON r.id = ra.role_id JOIN users u ON u.id = ra.user_id
           WHERE s.project_id = :p OR s.crm_org_id IN (SELECT crm_org_id FROM project_orgs WHERE project_id = :p) ORDER BY r.name, u.display_name""",
        p=project_id,
    )
    return {
        **base,
        "work": work,
        "orgs": orgs,
        "contacts": contacts,
        "entries": entries,
        "work_packages": packages,
        "results": results,
        "relations": relations,
        "communication": comm,
        "documents": docs,
        "team": {"people": work.get("people", []), "role_holders": role_holders, "customer_roles": scoped},
        "knowledge": await _knowledge_block(db, p),
        "finance": await _finance_block(db, ctx, p),
        "can_manage": await _can_edit(db, ctx, p),
    }


# ---------------------------------------------------------------- update


@router.patch("/{project_id}", summary="Update portfolio fields of a project", responses={403: {"description": NOT_ALLOWED}, 422: {"description": "Customer project without customer organization"}})
async def update_portfolio_project(project_id: UUID, body: PortfolioUpdate, ctx: CtxDep, db: DbDep) -> dict:
    p = await _require_edit(db, ctx, project_id)
    data = body.model_dump(exclude_unset=True)
    for required in ("name", "classification", "category", "phase", "status", "priority"):
        if required in data and data[required] is None:
            raise err(422, "VALIDATION_ERROR", f"{required} cannot be empty.", required)
    if "manager_id" in data:
        await _check_member(db, ctx, data["manager_id"], "manager_id")
    if customer_rule_violated(data.get("classification", p["classification"]), await _customer_count(db, project_id)):
        raise _customer_error()
    if "project_no" in data and not data["project_no"]:
        data["project_no"] = None
    sets, params = set_clause(
        data,
        {"name", "description", "classification", "category", "phase", "status", "priority", "short_name", "project_no", "org_unit", "manager_id", "owning_role_id",
         "start_date", "due_date", "is_research", "funding_program", "funding_agency", "funding_ref", "research_note", "ai_relevant"},
    )
    if sets:
        await x(db, f"UPDATE projects SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=project_id, u=ctx.user_id, **params)  # noqa: S608
        await audit(db, ctx, "project.updated", "project", project_id, p["name"])
    await db.commit()
    return {"ok": True}


@router.put("/{project_id}/orgs", summary="Replace the linked organizations (customers, partners, funders)", responses={422: {"description": "Customer project needs a customer"}})
async def set_orgs(project_id: UUID, body: OrgLinks, ctx: CtxDep, db: DbDep) -> dict:
    p = await _require_edit(db, ctx, project_id)
    customers = {i.crm_org_id for i in body.items if i.relation == "customer"}
    if customer_rule_violated(p["classification"], len(customers)):
        raise _customer_error()
    await _check_crm_orgs(db, ctx, [i.crm_org_id for i in body.items])
    await x(db, "DELETE FROM project_orgs WHERE project_id = :p", p=project_id)
    for item in {(i.crm_org_id, i.relation) for i in body.items}:
        await x(db, "INSERT INTO project_orgs (organization_id, project_id, crm_org_id, relation) VALUES (:o, :p, :c, :r)", o=ctx.org_id, p=project_id, c=item[0], r=item[1])
    await audit(db, ctx, "project.orgs_changed", "project", project_id, p["name"])
    await db.commit()
    return {"ok": True}


@router.put("/{project_id}/contacts", summary="Replace the customer contacts of a project")
async def set_contacts(project_id: UUID, body: ContactLinks, ctx: CtxDep, db: DbDep) -> dict:
    await _require_edit(db, ctx, project_id)
    await x(db, "DELETE FROM project_contacts WHERE project_id = :p", p=project_id)
    seen: set[UUID] = set()
    for item in body.items:
        if item.contact_id in seen:
            continue
        seen.add(item.contact_id)
        row = await q1(db, "SELECT 1 AS ok FROM crm_contacts WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=item.contact_id, o=ctx.org_id)
        if row is None:
            raise err(404, "CONTACT_NOT_FOUND", "Contact not found.", "contact_id")
        await x(db, "INSERT INTO project_contacts (organization_id, project_id, contact_id, contact_role) VALUES (:o, :p, :c, :r)", o=ctx.org_id, p=project_id, c=item.contact_id, r=item.contact_role)
    await db.commit()
    return {"ok": True}


@router.put("/{project_id}/entries", summary="Replace the catalog links (technologies, industries, research areas ...)")
async def set_entries(project_id: UUID, body: EntryLinks, ctx: CtxDep, db: DbDep) -> dict:
    p = await _require_edit(db, ctx, project_id)
    await _check_entries(db, ctx, [i.entry_id for i in body.items])
    await x(db, "DELETE FROM project_catalog_links WHERE project_id = :p", p=project_id)
    seen: set[UUID] = set()
    for item in body.items:
        if item.entry_id in seen:
            continue
        seen.add(item.entry_id)
        await x(db, "INSERT INTO project_catalog_links (organization_id, project_id, entry_id, usage_note) VALUES (:o, :p, :e, :n)", o=ctx.org_id, p=project_id, e=item.entry_id, n=item.usage_note)
    await audit(db, ctx, "project.entries_changed", "project", project_id, p["name"])
    await db.commit()
    return {"ok": True}


@router.put("/{project_id}/knowledge/{section}", summary="Write a knowledge section and its verification state", responses={403: {"description": "Not allowed to set this verification state"}})
async def set_knowledge(project_id: UUID, section: KnowledgeSection, body: KnowledgeBody, ctx: CtxDep, db: DbDep) -> dict:
    p = await _require_edit(db, ctx, project_id)
    existing = await q1(db, "SELECT content, verification FROM project_knowledge WHERE project_id = :p AND section = :s", p=project_id, s=section)
    content = body.content if body.content is not None else (existing["content"] if existing else "")
    changed = existing is None or content != existing["content"]
    # Editing the text of a verified section resets it to unverified unless a state is requested explicitly.
    verification = body.verification or ("unverified" if changed else existing["verification"])
    if body.verification and not can_set_verification(ctx.level, p.get("manager_id") == ctx.user_id or ctx.user_id == p["created_by"], body.verification):
        raise err(403, "VERIFICATION_FORBIDDEN", "Only administrators or the project manager can verify or approve content.")
    stamp = verification in ("verified", "approved")
    await x(
        db,
        """INSERT INTO project_knowledge (organization_id, project_id, section, content, verification, verified_by, verified_at, created_by, updated_by)
           VALUES (:o, :p, :s, :c, :v, CASE WHEN :st THEN CAST(:u AS uuid) END, CASE WHEN :st THEN NOW() END, :u, :u)
           ON CONFLICT (project_id, section) DO UPDATE SET content = EXCLUDED.content, verification = EXCLUDED.verification,
             verified_by = EXCLUDED.verified_by, verified_at = EXCLUDED.verified_at, updated_at = NOW(), updated_by = EXCLUDED.updated_by""",
        o=ctx.org_id, p=project_id, s=section, c=content, v=verification, st=stamp, u=ctx.user_id,
    )
    await audit(db, ctx, "project.knowledge_changed", "project", project_id, f"{p['name']} / {section} / {verification}")
    await db.commit()
    return {"ok": True, "verification": verification}


# ------------------------------------------------------- work packages


@router.post("/{project_id}/work-packages", summary="Add a work package")
async def add_work_package(project_id: UUID, body: WorkPackageBody, ctx: CtxDep, db: DbDep) -> dict:
    await _require_edit(db, ctx, project_id)
    await _check_member(db, ctx, body.lead_user_id, "lead_user_id")
    pos = await q1(db, "SELECT COALESCE(MAX(position), 0) + 1 AS n FROM project_work_packages WHERE project_id = :p", p=project_id)
    row = await q1(
        db,
        """INSERT INTO project_work_packages (organization_id, project_id, code, title, description, status, start_date, end_date, lead_user_id, position, created_by, updated_by)
           VALUES (:o, :p, :c, :t, :d, :s, :sd, :ed, :l, :pos, :u, :u) RETURNING id""",
        o=ctx.org_id, p=project_id, c=body.code, t=body.title, d=body.description, s=body.status, sd=body.start_date, ed=body.end_date, l=body.lead_user_id, pos=pos["n"], u=ctx.user_id,
    )
    await db.commit()
    return {"id": row["id"]}


@router.patch("/{project_id}/work-packages/{wp_id}", summary="Update a work package", responses={404: {"description": "Work package not found"}})
async def update_work_package(project_id: UUID, wp_id: UUID, body: WorkPackageUpdate, ctx: CtxDep, db: DbDep) -> dict:
    await _require_edit(db, ctx, project_id)
    data = body.model_dump(exclude_unset=True)
    if "lead_user_id" in data:
        await _check_member(db, ctx, data["lead_user_id"], "lead_user_id")
    sets, params = set_clause(data, {"code", "title", "description", "status", "start_date", "end_date", "lead_user_id"})
    if sets:
        got = await q(db, f"UPDATE project_work_packages SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id AND project_id = :p AND deleted_at IS NULL RETURNING id", id=wp_id, p=project_id, u=ctx.user_id, **params)  # noqa: S608
        if not got:
            raise err(404, "WORK_PACKAGE_NOT_FOUND", "Work package not found.")
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/work-packages/{wp_id}", summary="Delete a work package (soft)")
async def delete_work_package(project_id: UUID, wp_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    await _require_edit(db, ctx, project_id)
    await x(db, "UPDATE project_work_packages SET deleted_at = NOW(), updated_by = :u WHERE id = :id AND project_id = :p", id=wp_id, p=project_id, u=ctx.user_id)
    await db.commit()
    return {"ok": True}


# --------------------------------------------------------------- results


async def _check_wp(db, project_id: UUID, wp_id: UUID | None) -> None:
    if wp_id is None:
        return
    row = await q1(db, "SELECT 1 AS ok FROM project_work_packages WHERE id = :w AND project_id = :p AND deleted_at IS NULL", w=wp_id, p=project_id)
    if row is None:
        raise err(404, "WORK_PACKAGE_NOT_FOUND", "Work package not found.", "work_package_id")


@router.post("/{project_id}/results", summary="Add a result (planned vs demonstrated)")
async def add_result(project_id: UUID, body: ResultBody, ctx: CtxDep, db: DbDep) -> dict:
    await _require_edit(db, ctx, project_id)
    await _check_wp(db, project_id, body.work_package_id)
    row = await q1(
        db,
        """INSERT INTO project_results (organization_id, project_id, work_package_id, title, kind, planned_value, demonstrated_value, unit, evidence_url, status, created_by, updated_by)
           VALUES (:o, :p, :w, :t, :k, :pv, :dv, :un, :ev, :s, :u, :u) RETURNING id""",
        o=ctx.org_id, p=project_id, w=body.work_package_id, t=body.title, k=body.kind, pv=body.planned_value, dv=body.demonstrated_value, un=body.unit, ev=body.evidence_url, s=body.status, u=ctx.user_id,
    )
    await db.commit()
    return {"id": row["id"]}


@router.patch("/{project_id}/results/{result_id}", summary="Update a result", responses={404: {"description": "Result not found"}})
async def update_result(project_id: UUID, result_id: UUID, body: ResultUpdate, ctx: CtxDep, db: DbDep) -> dict:
    await _require_edit(db, ctx, project_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("work_package_id"):
        await _check_wp(db, project_id, data["work_package_id"])
    sets, params = set_clause(data, {"title", "kind", "work_package_id", "planned_value", "demonstrated_value", "unit", "evidence_url", "status"})
    if sets:
        got = await q(db, f"UPDATE project_results SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id AND project_id = :p AND deleted_at IS NULL RETURNING id", id=result_id, p=project_id, u=ctx.user_id, **params)  # noqa: S608
        if not got:
            raise err(404, "RESULT_NOT_FOUND", "Result not found.")
    await db.commit()
    return {"ok": True}


@router.delete("/{project_id}/results/{result_id}", summary="Delete a result (soft)")
async def delete_result(project_id: UUID, result_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    await _require_edit(db, ctx, project_id)
    await x(db, "UPDATE project_results SET deleted_at = NOW(), updated_by = :u WHERE id = :id AND project_id = :p", id=result_id, p=project_id, u=ctx.user_id)
    await db.commit()
    return {"ok": True}


# --------------------------------------------------------------- finance


@router.put("/{project_id}/finance", summary="Enter finance and reporting data", responses={403: {"description": "Only administrators and the project manager manage finance data"}})
async def set_finance(project_id: UUID, body: FinanceBody, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    p = await _project(db, ctx, project_id)
    if not _is_finance_owner(ctx, p):
        raise err(403, "FINANCE_FORBIDDEN", "Only administrators and the project manager manage finance data.")
    if body.budget_total is not None and body.budget_funding is not None and body.budget_funding > body.budget_total:
        raise err(422, "FUNDING_EXCEEDS_BUDGET", "Funding cannot exceed the total budget.", "budget_funding")
    d = body.model_dump()
    await x(
        db,
        """INSERT INTO project_finance (organization_id, project_id, budget_total, budget_funding, budget_own, costs_to_date, revenue_expected, currency,
                                        reporting_cycle, next_report_due, last_report_at, notes, created_by, updated_by)
           VALUES (:o, :p, :bt, :bf, :bo, :ct, :re, :cur, :rc, :nr, :lr, :nt, :u, :u)
           ON CONFLICT (project_id) DO UPDATE SET budget_total = EXCLUDED.budget_total, budget_funding = EXCLUDED.budget_funding, budget_own = EXCLUDED.budget_own,
             costs_to_date = EXCLUDED.costs_to_date, revenue_expected = EXCLUDED.revenue_expected, currency = EXCLUDED.currency, reporting_cycle = EXCLUDED.reporting_cycle,
             next_report_due = EXCLUDED.next_report_due, last_report_at = EXCLUDED.last_report_at, notes = EXCLUDED.notes, updated_at = NOW(), updated_by = EXCLUDED.updated_by""",
        o=ctx.org_id, p=project_id, bt=d["budget_total"], bf=d["budget_funding"], bo=d["budget_own"], ct=d["costs_to_date"], re=d["revenue_expected"], cur=d["currency"],
        rc=d["reporting_cycle"], nr=d["next_report_due"], lr=d["last_report_at"], nt=d["notes"], u=ctx.user_id,
    )
    await audit(db, ctx, "project.finance_changed", "project", project_id, p["name"])
    await db.commit()
    return {"ok": True}


@router.put("/{project_id}/finance-viewers", summary="Choose who besides administrators and the manager may see finance data")
async def set_finance_viewers(project_id: UUID, body: FinanceViewers, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    p = await _project(db, ctx, project_id)
    if not _is_finance_owner(ctx, p):
        raise err(403, "FINANCE_FORBIDDEN", "Only administrators and the project manager manage finance access.")
    await x(db, "DELETE FROM project_finance_viewers WHERE project_id = :p", p=project_id)
    for uid in set(body.user_ids):
        await _check_member(db, ctx, uid, "user_ids")
        await x(db, "INSERT INTO project_finance_viewers (organization_id, project_id, user_id) VALUES (:o, :p, :u)", o=ctx.org_id, p=project_id, u=uid)
    await audit(db, ctx, "project.finance_access_changed", "project", project_id, p["name"])
    await db.commit()
    return {"ok": True}


# ---------------------------------------------- communication, relations, docs


@router.put("/{project_id}/communication", summary="Set the reference permission and which content may be used")
async def set_communication(project_id: UUID, body: CommunicationBody, ctx: CtxDep, db: DbDep) -> dict:
    p = await _require_edit(db, ctx, project_id)
    d = normalize_communication(body.model_dump())
    await x(
        db,
        """INSERT INTO project_communication (organization_id, project_id, reference_allowed, allow_name, allow_logo, allow_images, allow_description, allow_results,
                                              approved_by_name, approved_at, notes, created_by, updated_by)
           VALUES (:o, :p, :ra, :an, :al, :ai, :ad, :ar, :ab, :aa, :nt, :u, :u)
           ON CONFLICT (project_id) DO UPDATE SET reference_allowed = EXCLUDED.reference_allowed, allow_name = EXCLUDED.allow_name, allow_logo = EXCLUDED.allow_logo,
             allow_images = EXCLUDED.allow_images, allow_description = EXCLUDED.allow_description, allow_results = EXCLUDED.allow_results,
             approved_by_name = EXCLUDED.approved_by_name, approved_at = EXCLUDED.approved_at, notes = EXCLUDED.notes, updated_at = NOW(), updated_by = EXCLUDED.updated_by""",
        o=ctx.org_id, p=project_id, ra=d["reference_allowed"], an=d["allow_name"], al=d["allow_logo"], ai=d["allow_images"], ad=d["allow_description"], ar=d["allow_results"],
        ab=d["approved_by_name"], aa=d["approved_at"], nt=d["notes"], u=ctx.user_id,
    )
    await audit(db, ctx, "project.reference_changed", "project", project_id, f"{p['name']} / reference={d['reference_allowed']}")
    await db.commit()
    return {"ok": True}


@router.put("/{project_id}/relations", summary="Replace the relations to other projects")
async def set_relations(project_id: UUID, body: RelationLinks, ctx: CtxDep, db: DbDep) -> dict:
    await _require_edit(db, ctx, project_id)
    await x(db, "DELETE FROM project_relations WHERE project_id = :p", p=project_id)
    seen: set[UUID] = set()
    for item in body.items:
        if item.related_project_id == project_id or item.related_project_id in seen:
            continue
        seen.add(item.related_project_id)
        await _project(db, ctx, item.related_project_id)
        await x(db, "INSERT INTO project_relations (organization_id, project_id, related_project_id, relation, note) VALUES (:o, :p, :r, :k, :n)", o=ctx.org_id, p=project_id, r=item.related_project_id, k=item.relation, n=item.note)
    await db.commit()
    return {"ok": True}


@router.post("/{project_id}/documents", summary="Link a document (URL) to the project")
async def add_document(project_id: UUID, body: DocumentBody, ctx: CtxDep, db: DbDep) -> dict:
    await _require_edit(db, ctx, project_id)
    row = await q1(
        db,
        "INSERT INTO attachments (organization_id, entity_type, entity_id, name, url, created_by) VALUES (:o, 'project', :p, :n, :url, :u) RETURNING id",
        o=ctx.org_id, p=project_id, n=body.name, url=body.url, u=ctx.user_id,
    )
    await db.commit()
    return {"id": row["id"]}


@router.delete("/{project_id}/documents/{doc_id}", summary="Remove a linked document")
async def delete_document(project_id: UUID, doc_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    await _require_edit(db, ctx, project_id)
    await x(db, "UPDATE attachments SET deleted_at = NOW() WHERE id = :d AND entity_type = 'project' AND entity_id = :p AND organization_id = :o", d=doc_id, p=project_id, o=ctx.org_id)
    await db.commit()
    return {"ok": True}


@router.get("/{project_id}/history", summary="Audit trail of one project")
async def project_history(project_id: UUID, ctx: CtxDep, db: DbDep) -> list[dict]:
    await _project(db, ctx, project_id)
    return await q(
        db,
        """SELECT a.id, a.action, a.summary, a.created_at, u.display_name AS actor_name FROM audit_events a LEFT JOIN users u ON u.id = a.actor_id
           WHERE a.organization_id = :o AND a.entity_type = 'project' AND a.entity_id = :p ORDER BY a.created_at DESC LIMIT 100""",
        o=ctx.org_id, p=project_id,
    )


@router.delete("/{project_id}", summary="Delete a project (soft) - administrators only")
async def delete_portfolio_project(project_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    p = await _project(db, ctx, project_id)
    await x(db, "UPDATE projects SET deleted_at = NOW(), updated_by = :u WHERE id = :id", id=project_id, u=ctx.user_id)
    await audit(db, ctx, "project.deleted", "project", project_id, p["name"])
    await db.commit()
    return {"ok": True}
