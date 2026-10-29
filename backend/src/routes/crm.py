"""CRM foundation: one organization entity with several relationship types, contacts, activities.

Opportunities, quotes, NDAs and contracts are a later phase and deliberately not part of this router.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field
from routes.work import _holds_role
from services.catalog import normalize
from services.ctx import CtxDep, can_govern, require_admin, require_write
from services.dbx import DbDep, err, q, q1, set_clause, x
from services.events import audit, notify

router = APIRouter(prefix="/api/crm", tags=["crm"])

RelationType = Literal["customer", "prospect", "partner", "research_partner", "funder", "supplier", "competitor", "other"]
SizeClass = Literal["micro", "small", "medium", "large", "public"]
ActiveState = Literal["active", "inactive"]
ActivityKind = Literal["call", "meeting", "email", "note", "visit", "other"]
EMAIL_RE = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
PHONE_RE = r"^[0-9+()\-./ ]{3,40}$"
ORG_NOT_FOUND = "Organization not found."
CONTACT_NOT_FOUND = "Contact not found."
PLANNED_MODULES = ["opportunities", "quotes", "nda_contracts"]


class OrgCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    legal_name: str | None = Field(default=None, max_length=250)
    vat_id: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9 .\-]{4,40}$")
    website: str | None = Field(default=None, max_length=300, pattern=r"^https?://")
    industry_entry_id: UUID | None = None
    country: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    size_class: SizeClass | None = None
    parent_id: UUID | None = None
    relation_types: list[RelationType] = Field(default_factory=lambda: (["customer"]), max_length=8)
    owner_user_id: UUID | None = None
    customer_since: date | None = None
    status: ActiveState = "active"
    notes: str = Field(default="", max_length=5000)


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    legal_name: str | None = Field(default=None, max_length=250)
    vat_id: str | None = Field(default=None, max_length=40, pattern=r"^[A-Za-z0-9 .\-]{4,40}$")
    website: str | None = Field(default=None, max_length=300, pattern=r"^https?://")
    industry_entry_id: UUID | None = None
    country: str | None = Field(default=None, max_length=80)
    city: str | None = Field(default=None, max_length=120)
    address: str | None = Field(default=None, max_length=300)
    size_class: SizeClass | None = None
    parent_id: UUID | None = None
    relation_types: list[RelationType] | None = Field(default=None, max_length=8)
    owner_user_id: UUID | None = None
    customer_since: date | None = None
    status: ActiveState | None = None
    notes: str | None = Field(default=None, max_length=5000)


class ContactOrgLink(BaseModel):
    crm_org_id: UUID
    contact_role: str | None = Field(default=None, max_length=60)
    is_primary: bool = False


class ContactCreate(BaseModel):
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_RE)
    phone: str | None = Field(default=None, max_length=40, pattern=PHONE_RE)
    job_title: str | None = Field(default=None, max_length=120)
    notes: str = Field(default="", max_length=5000)
    orgs: list[ContactOrgLink] = Field(default_factory=list, max_length=10)
    allow_duplicate: bool = False


class ContactUpdate(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=100)
    last_name: str | None = Field(default=None, min_length=1, max_length=100)
    email: str | None = Field(default=None, max_length=254, pattern=EMAIL_RE)
    phone: str | None = Field(default=None, max_length=40, pattern=PHONE_RE)
    job_title: str | None = Field(default=None, max_length=120)
    notes: str | None = Field(default=None, max_length=5000)
    status: ActiveState | None = None


class ContactOrgLinks(BaseModel):
    items: list[ContactOrgLink] = Field(max_length=10)


class FollowUp(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    due_date: date | None = None
    assignee_id: UUID | None = None


class ActivityCreate(BaseModel):
    crm_org_id: UUID | None = None
    contact_id: UUID | None = None
    project_id: UUID | None = None
    kind: ActivityKind = "note"
    subject: str = Field(min_length=2, max_length=200)
    body: str = Field(default="", max_length=10000)
    occurred_at: datetime | None = None
    follow_up: FollowUp | None = None


class ScopeCreate(BaseModel):
    role_assignment_id: UUID
    scope_type: Literal["organization", "project"]
    crm_org_id: UUID | None = None
    project_id: UUID | None = None


# ---------------------------------------------------------------- helpers


def _dup(existing: dict[str, Any], what: str, field: str) -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={"code": "CRM_DUPLICATE", "message": f"A matching {what} already exists: “{existing['name']}”.", "field": field,
                "details": {"existing": {"id": str(existing["id"]), "name": existing["name"]}}},
    )


def _vat(value: str | None) -> str | None:
    return value.replace(" ", "").upper() if value else None


async def _org(db, ctx, org_id: UUID) -> dict:
    row = await q1(db, "SELECT * FROM crm_organizations WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=org_id, o=ctx.org_id)
    if row is None:
        raise err(404, "CRM_ORG_NOT_FOUND", ORG_NOT_FOUND)
    return row


async def _contact(db, ctx, contact_id: UUID) -> dict:
    row = await q1(db, "SELECT * FROM crm_contacts WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=contact_id, o=ctx.org_id)
    if row is None:
        raise err(404, "CONTACT_NOT_FOUND", CONTACT_NOT_FOUND)
    return row


async def _check_dup_org(db, ctx, name: str | None, vat: str | None, exclude: UUID | None = None) -> None:
    if name:
        hit = await q1(db, "SELECT id, name FROM crm_organizations WHERE organization_id = :o AND norm_name = :n AND deleted_at IS NULL AND (CAST(:x AS uuid) IS NULL OR id <> CAST(:x AS uuid))", o=ctx.org_id, n=normalize(name), x=exclude)
        if hit:
            raise _dup(hit, "organization", "name")
    if vat:
        hit = await q1(db, "SELECT id, name FROM crm_organizations WHERE organization_id = :o AND vat_id = :v AND deleted_at IS NULL AND (CAST(:x AS uuid) IS NULL OR id <> CAST(:x AS uuid))", o=ctx.org_id, v=vat, x=exclude)
        if hit:
            raise _dup(hit, "organization with this VAT ID", "vat_id")


async def _check_member(db, ctx, user_id: UUID | None, field: str) -> None:
    if user_id is None:
        return
    row = await q1(db, "SELECT 1 AS ok FROM memberships WHERE user_id = :u AND organization_id = :o AND active", u=user_id, o=ctx.org_id)
    if row is None:
        raise err(404, "PERSON_NOT_FOUND", "Person is not a member of this organization.", field)


async def _check_industry(db, ctx, entry_id: UUID | None) -> None:
    if entry_id is None:
        return
    row = await q1(db, "SELECT 1 AS ok FROM catalog_entries WHERE id = :i AND organization_id = :o AND kind = 'industry' AND deleted_at IS NULL", i=entry_id, o=ctx.org_id)
    if row is None:
        raise err(404, "CATALOG_ENTRY_NOT_FOUND", "Industry not found in the catalog.", "industry_entry_id")


async def _check_parent(db, ctx, org_id: UUID | None, parent_id: UUID | None) -> None:
    if parent_id is None:
        return
    await _org(db, ctx, parent_id)
    cur: UUID | None = parent_id
    for _ in range(50):
        if cur is None:
            return
        if cur == org_id:
            raise err(422, "PARENT_CYCLE", "An organization cannot be its own parent or ancestor.", "parent_id")
        row = await q1(db, "SELECT parent_id FROM crm_organizations WHERE id = :i", i=cur)
        cur = row["parent_id"] if row else None


def _hide_private(rows: list[dict], ctx) -> list[dict]:
    if ctx.level == "observer":
        for r in rows:
            r["email"] = None
            r["phone"] = None
    return rows


# ----------------------------------------------------------- organizations


@router.get("/organizations", summary="List CRM organizations")
async def list_orgs(
    ctx: CtxDep,
    db: DbDep,
    search: str | None = Query(default=None, max_length=100),
    relation: RelationType | None = None,
    owner_id: UUID | None = None,
    industry_id: UUID | None = None,
    status: ActiveState | None = None,
) -> list[dict]:
    where = ["co.organization_id = :o", "co.deleted_at IS NULL"]
    params: dict[str, Any] = {"o": ctx.org_id}
    if search:
        where.append("(co.name ILIKE :s OR co.legal_name ILIKE :s OR co.city ILIKE :s OR co.vat_id ILIKE :s)")
        params["s"] = f"%{search.strip()}%"
    if relation:
        where.append(":rel = ANY(co.relation_types)")
        params["rel"] = relation
    if owner_id:
        where.append("co.owner_user_id = :ow")
        params["ow"] = owner_id
    if industry_id:
        where.append("co.industry_entry_id = :ind")
        params["ind"] = industry_id
    if status:
        where.append("co.status = :st")
        params["st"] = status
    return await q(
        db,
        f"""SELECT co.id, co.name, co.city, co.country, co.relation_types, co.status, co.owner_user_id, u.display_name AS owner_name,
                   co.industry_entry_id, i.name AS industry, co.parent_id, p.name AS parent_name,
                   (SELECT COUNT(*) FROM crm_contact_orgs cc JOIN crm_contacts c ON c.id = cc.contact_id AND c.deleted_at IS NULL WHERE cc.crm_org_id = co.id) AS contact_count,
                   (SELECT COUNT(*) FROM project_orgs po JOIN projects pr ON pr.id = po.project_id AND pr.deleted_at IS NULL WHERE po.crm_org_id = co.id) AS project_count,
                   (SELECT MAX(a.occurred_at) FROM crm_activities a WHERE a.crm_org_id = co.id AND a.deleted_at IS NULL) AS last_activity_at
            FROM crm_organizations co LEFT JOIN users u ON u.id = co.owner_user_id LEFT JOIN catalog_entries i ON i.id = co.industry_entry_id
            LEFT JOIN crm_organizations p ON p.id = co.parent_id
            WHERE {' AND '.join(where)} ORDER BY co.name LIMIT 500""",  # noqa: S608 - constants only
        **params,
    )


@router.post("/organizations", summary="Create a CRM organization", responses={409: {"description": "Organization with same name or VAT ID exists"}})
async def create_org(body: OrgCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    if not normalize(body.name):
        raise err(422, "INVALID_NAME", "Name must contain letters or digits.", "name")
    vat = _vat(body.vat_id)
    await _check_dup_org(db, ctx, body.name, vat)
    await _check_member(db, ctx, body.owner_user_id, "owner_user_id")
    await _check_industry(db, ctx, body.industry_entry_id)
    await _check_parent(db, ctx, None, body.parent_id)
    row = await q1(
        db,
        """INSERT INTO crm_organizations (organization_id, name, norm_name, legal_name, vat_id, website, industry_entry_id, country, city, address, size_class,
                                          parent_id, relation_types, owner_user_id, customer_since, status, notes, created_by, updated_by)
           VALUES (:o, :n, :nn, :ln, :v, :w, :ind, :co, :ci, :ad, :sz, :pa, :rt, :ow, :cs, :st, :nt, :u, :u) RETURNING id""",
        o=ctx.org_id, n=body.name.strip(), nn=normalize(body.name), ln=body.legal_name, v=vat, w=body.website, ind=body.industry_entry_id, co=body.country, ci=body.city,
        ad=body.address, sz=body.size_class, pa=body.parent_id, rt=sorted(set(body.relation_types)), ow=body.owner_user_id, cs=body.customer_since, st=body.status, nt=body.notes, u=ctx.user_id,
    )
    await audit(db, ctx, "crm.organization_created", "crm_organization", row["id"], body.name)
    await db.commit()
    return {"id": row["id"]}


@router.get("/organizations/{org_id}", summary="360-degree view of a CRM organization", responses={404: {"description": ORG_NOT_FOUND}})
async def org_360(org_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    await _org(db, ctx, org_id)
    base = await q1(
        db,
        """SELECT co.*, u.display_name AS owner_name, i.name AS industry, p.name AS parent_name FROM crm_organizations co
           LEFT JOIN users u ON u.id = co.owner_user_id LEFT JOIN catalog_entries i ON i.id = co.industry_entry_id LEFT JOIN crm_organizations p ON p.id = co.parent_id WHERE co.id = :i""",
        i=org_id,
    )
    children = await q(db, "SELECT id, name FROM crm_organizations WHERE parent_id = :i AND deleted_at IS NULL ORDER BY name", i=org_id)
    contacts = _hide_private(await q(
        db,
        """SELECT c.id, c.first_name, c.last_name, c.email, c.phone, c.job_title, cc.contact_role, cc.is_primary, c.status
           FROM crm_contact_orgs cc JOIN crm_contacts c ON c.id = cc.contact_id AND c.deleted_at IS NULL WHERE cc.crm_org_id = :i ORDER BY cc.is_primary DESC, c.last_name""",
        i=org_id,
    ), ctx)
    projects = await q(
        db,
        """SELECT pr.id, pr.name, pr.classification, pr.status, pr.phase, pr.start_date, pr.due_date, po.relation FROM project_orgs po
           JOIN projects pr ON pr.id = po.project_id AND pr.deleted_at IS NULL WHERE po.crm_org_id = :i ORDER BY (pr.phase IN ('completed','archived')), pr.name""",
        i=org_id,
    )
    activities = await q(
        db,
        """SELECT a.id, a.kind, a.subject, a.body, a.occurred_at, a.contact_id, c.first_name || ' ' || c.last_name AS contact_name, a.project_id, pr.name AS project_name,
                  a.follow_up_task_id, t.title AS follow_up_title, t.status AS follow_up_status, t.due_date AS follow_up_due, u.display_name AS author_name
           FROM crm_activities a LEFT JOIN crm_contacts c ON c.id = a.contact_id LEFT JOIN projects pr ON pr.id = a.project_id
           LEFT JOIN tasks t ON t.id = a.follow_up_task_id AND t.deleted_at IS NULL LEFT JOIN users u ON u.id = a.created_by
           WHERE a.crm_org_id = :i AND a.deleted_at IS NULL ORDER BY a.occurred_at DESC LIMIT 50""",
        i=org_id,
    )
    roles = await q(
        db,
        """SELECT s.id AS scope_id, s.scope_type, u.id AS user_id, u.display_name AS name, r.id AS role_id, r.name AS role_name, ra.id AS role_assignment_id,
                  s.project_id, pr.name AS project_name
           FROM crm_role_scopes s JOIN role_assignments ra ON ra.id = s.role_assignment_id AND ra.deleted_at IS NULL
           JOIN roles r ON r.id = ra.role_id AND r.deleted_at IS NULL JOIN users u ON u.id = ra.user_id LEFT JOIN projects pr ON pr.id = s.project_id
           WHERE s.crm_org_id = :i OR s.project_id IN (SELECT project_id FROM project_orgs WHERE crm_org_id = :i) ORDER BY r.name, u.display_name""",
        i=org_id,
    )
    next_steps = [a for a in activities if a["follow_up_task_id"] and a["follow_up_status"] not in (None, "done")]
    last = activities[0]["occurred_at"] if activities else None
    return {
        **base, "children": children, "contacts": contacts, "projects": projects, "activities": activities, "roles": roles,
        "next_steps": next_steps, "last_activity_at": last,
        "stats": {"contacts": len(contacts), "projects": len(projects), "active_projects": sum(1 for p in projects if p["status"] in ("planned", "active"))},
        "planned_modules": PLANNED_MODULES,
    }


@router.patch("/organizations/{org_id}", summary="Update a CRM organization", responses={404: {"description": ORG_NOT_FOUND}, 409: {"description": "Duplicate name or VAT ID"}})
async def update_org(org_id: UUID, body: OrgUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    current = await _org(db, ctx, org_id)
    data = body.model_dump(exclude_unset=True)
    for required in ("name", "relation_types", "status"):
        if required in data and data[required] is None:
            raise err(422, "VALIDATION_ERROR", f"{required} cannot be empty.", required)
    if "name" in data:
        data["norm_name"] = normalize(data["name"])
        data["name"] = data["name"].strip()
    if "vat_id" in data:
        data["vat_id"] = _vat(data["vat_id"])
    await _check_dup_org(db, ctx, data.get("name"), data.get("vat_id"), exclude=org_id)
    if "owner_user_id" in data:
        await _check_member(db, ctx, data["owner_user_id"], "owner_user_id")
    if "industry_entry_id" in data:
        await _check_industry(db, ctx, data["industry_entry_id"])
    if "parent_id" in data:
        await _check_parent(db, ctx, org_id, data["parent_id"])
    if "relation_types" in data:
        data["relation_types"] = sorted(set(data["relation_types"]))
        if "customer" not in data["relation_types"] and "customer" in current["relation_types"]:
            used = await q1(db, "SELECT COUNT(*) AS n FROM project_orgs po JOIN projects p ON p.id = po.project_id AND p.deleted_at IS NULL AND p.classification = 'customer' WHERE po.crm_org_id = :i AND po.relation = 'customer'", i=org_id)
            if used and used["n"] > 0:
                raise err(422, "CUSTOMER_IN_USE", "This organization is the customer of existing customer projects and must stay a customer.", "relation_types")
    sets, params = set_clause(data, {"name", "norm_name", "legal_name", "vat_id", "website", "industry_entry_id", "country", "city", "address", "size_class", "parent_id", "relation_types", "owner_user_id", "customer_since", "status", "notes"})
    if sets:
        await x(db, f"UPDATE crm_organizations SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=org_id, u=ctx.user_id, **params)  # noqa: S608
        await audit(db, ctx, "crm.organization_updated", "crm_organization", org_id, current["name"])
    await db.commit()
    return {"ok": True}


@router.delete("/organizations/{org_id}", summary="Delete a CRM organization (soft) - administrators only", responses={409: {"description": "Still linked to customer projects"}})
async def delete_org(org_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    org = await _org(db, ctx, org_id)
    used = await q1(db, "SELECT COUNT(*) AS n FROM project_orgs po JOIN projects p ON p.id = po.project_id AND p.deleted_at IS NULL AND p.classification = 'customer' WHERE po.crm_org_id = :i AND po.relation = 'customer'", i=org_id)
    if used and used["n"] > 0:
        raise err(409, "CRM_ORG_IN_USE", "This organization is the customer of existing projects. Re-assign those projects first.")
    await x(db, "UPDATE crm_organizations SET deleted_at = NOW(), updated_by = :u WHERE id = :i", i=org_id, u=ctx.user_id)
    await audit(db, ctx, "crm.organization_deleted", "crm_organization", org_id, org["name"])
    await db.commit()
    return {"ok": True}


# ---------------------------------------------------------------- contacts


@router.get("/contacts", summary="List contacts")
async def list_contacts(ctx: CtxDep, db: DbDep, search: str | None = Query(default=None, max_length=100), crm_org_id: UUID | None = None) -> list[dict]:
    where = ["c.organization_id = :o", "c.deleted_at IS NULL"]
    params: dict[str, Any] = {"o": ctx.org_id}
    if search:
        where.append("(c.first_name ILIKE :s OR c.last_name ILIKE :s OR c.email ILIKE :s OR (c.first_name || ' ' || c.last_name) ILIKE :s)")
        params["s"] = f"%{search.strip()}%"
    if crm_org_id:
        where.append("EXISTS (SELECT 1 FROM crm_contact_orgs x WHERE x.contact_id = c.id AND x.crm_org_id = :co)")
        params["co"] = crm_org_id
    rows = await q(
        db,
        f"""SELECT c.id, c.first_name, c.last_name, c.email, c.phone, c.job_title, c.status,
                   COALESCE((SELECT json_agg(json_build_object('id', co.id, 'name', co.name, 'contact_role', cc.contact_role, 'is_primary', cc.is_primary) ORDER BY co.name)
                             FROM crm_contact_orgs cc JOIN crm_organizations co ON co.id = cc.crm_org_id AND co.deleted_at IS NULL WHERE cc.contact_id = c.id), '[]'::json) AS orgs
            FROM crm_contacts c WHERE {' AND '.join(where)} ORDER BY c.last_name, c.first_name LIMIT 500""",  # noqa: S608 - constants only
        **params,
    )
    return _hide_private(rows, ctx)


async def _set_contact_orgs(db, ctx, contact_id: UUID, links: list[ContactOrgLink]) -> None:
    await x(db, "DELETE FROM crm_contact_orgs WHERE contact_id = :c", c=contact_id)
    seen: set[UUID] = set()
    for link in links:
        if link.crm_org_id in seen:
            continue
        seen.add(link.crm_org_id)
        await _org(db, ctx, link.crm_org_id)
        await x(db, "INSERT INTO crm_contact_orgs (organization_id, contact_id, crm_org_id, contact_role, is_primary) VALUES (:o, :c, :g, :r, :p)", o=ctx.org_id, c=contact_id, g=link.crm_org_id, r=link.contact_role, p=link.is_primary)


@router.post("/contacts", summary="Create a contact", responses={409: {"description": "Contact with this e-mail or name already exists"}})
async def create_contact(body: ContactCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    if body.email:
        hit = await q1(db, "SELECT id, first_name || ' ' || last_name AS name FROM crm_contacts WHERE organization_id = :o AND lower(email) = lower(:e) AND deleted_at IS NULL", o=ctx.org_id, e=body.email)
        if hit:
            raise _dup(hit, "contact with this e-mail", "email")
    if not body.allow_duplicate and body.orgs:
        hit = await q1(
            db,
            """SELECT c.id, c.first_name || ' ' || c.last_name AS name FROM crm_contacts c JOIN crm_contact_orgs cc ON cc.contact_id = c.id
               WHERE c.organization_id = :o AND c.deleted_at IS NULL AND lower(c.first_name) = lower(:f) AND lower(c.last_name) = lower(:l) AND cc.crm_org_id = ANY(:orgs) LIMIT 1""",
            o=ctx.org_id, f=body.first_name.strip(), l=body.last_name.strip(), orgs=[link.crm_org_id for link in body.orgs],
        )
        if hit:
            raise _dup(hit, "contact with this name at the same organization", "last_name")
    row = await q1(
        db,
        """INSERT INTO crm_contacts (organization_id, first_name, last_name, email, phone, job_title, notes, created_by, updated_by)
           VALUES (:o, :f, :l, :e, :p, :j, :n, :u, :u) RETURNING id""",
        o=ctx.org_id, f=body.first_name.strip(), l=body.last_name.strip(), e=body.email, p=body.phone, j=body.job_title, n=body.notes, u=ctx.user_id,
    )
    await _set_contact_orgs(db, ctx, row["id"], body.orgs)
    await audit(db, ctx, "crm.contact_created", "crm_contact", row["id"], f"{body.first_name} {body.last_name}")
    await db.commit()
    return {"id": row["id"]}


@router.get("/contacts/{contact_id}", summary="Contact detail with organizations, projects and activities", responses={404: {"description": CONTACT_NOT_FOUND}})
async def contact_detail(contact_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    c = await _contact(db, ctx, contact_id)
    orgs = await q(
        db,
        """SELECT co.id, co.name, cc.contact_role, cc.is_primary FROM crm_contact_orgs cc JOIN crm_organizations co ON co.id = cc.crm_org_id AND co.deleted_at IS NULL
           WHERE cc.contact_id = :c ORDER BY co.name""",
        c=contact_id,
    )
    projects = await q(db, "SELECT p.id, p.name, pc.contact_role FROM project_contacts pc JOIN projects p ON p.id = pc.project_id AND p.deleted_at IS NULL WHERE pc.contact_id = :c ORDER BY p.name", c=contact_id)
    activities = await q(db, "SELECT id, kind, subject, body, occurred_at FROM crm_activities WHERE contact_id = :c AND deleted_at IS NULL ORDER BY occurred_at DESC LIMIT 30", c=contact_id)
    out = _hide_private([{**c}], ctx)[0]
    return {**out, "orgs": orgs, "projects": projects, "activities": activities}


@router.patch("/contacts/{contact_id}", summary="Update a contact", responses={404: {"description": CONTACT_NOT_FOUND}, 409: {"description": "E-mail already used"}})
async def update_contact(contact_id: UUID, body: ContactUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    c = await _contact(db, ctx, contact_id)
    data = body.model_dump(exclude_unset=True)
    for required in ("first_name", "last_name", "status"):
        if required in data and data[required] is None:
            raise err(422, "VALIDATION_ERROR", f"{required} cannot be empty.", required)
    if data.get("email"):
        hit = await q1(db, "SELECT id, first_name || ' ' || last_name AS name FROM crm_contacts WHERE organization_id = :o AND lower(email) = lower(:e) AND deleted_at IS NULL AND id <> :i", o=ctx.org_id, e=data["email"], i=contact_id)
        if hit:
            raise _dup(hit, "contact with this e-mail", "email")
    sets, params = set_clause(data, {"first_name", "last_name", "email", "phone", "job_title", "notes", "status"})
    if sets:
        await x(db, f"UPDATE crm_contacts SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=contact_id, u=ctx.user_id, **params)  # noqa: S608
        await audit(db, ctx, "crm.contact_updated", "crm_contact", contact_id, f"{c['first_name']} {c['last_name']}")
    await db.commit()
    return {"ok": True}


@router.put("/contacts/{contact_id}/orgs", summary="Replace the organizations of a contact")
async def set_contact_orgs(contact_id: UUID, body: ContactOrgLinks, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    await _contact(db, ctx, contact_id)
    await _set_contact_orgs(db, ctx, contact_id, body.items)
    await db.commit()
    return {"ok": True}


@router.delete("/contacts/{contact_id}", summary="Delete a contact (soft)")
async def delete_contact(contact_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    c = await _contact(db, ctx, contact_id)
    await x(db, "UPDATE crm_contacts SET deleted_at = NOW(), updated_by = :u WHERE id = :i", i=contact_id, u=ctx.user_id)
    await audit(db, ctx, "crm.contact_deleted", "crm_contact", contact_id, f"{c['first_name']} {c['last_name']}")
    await db.commit()
    return {"ok": True}


# -------------------------------------------------------------- activities


@router.get("/activities", summary="Recent activities (optionally for one organization, contact or project)")
async def list_activities(ctx: CtxDep, db: DbDep, crm_org_id: UUID | None = None, contact_id: UUID | None = None, project_id: UUID | None = None, limit: int = Query(default=30, ge=1, le=100)) -> list[dict]:
    where = ["a.organization_id = :o", "a.deleted_at IS NULL"]
    params: dict[str, Any] = {"o": ctx.org_id, "lim": limit}
    for col, val in ("crm_org_id", crm_org_id), ("contact_id", contact_id), ("project_id", project_id):
        if val:
            where.append(f"a.{col} = :{col}")
            params[col] = val
    return await q(
        db,
        f"""SELECT a.id, a.kind, a.subject, a.body, a.occurred_at, a.crm_org_id, co.name AS org_name, a.contact_id, a.project_id, a.follow_up_task_id, u.display_name AS author_name
            FROM crm_activities a LEFT JOIN crm_organizations co ON co.id = a.crm_org_id LEFT JOIN users u ON u.id = a.created_by
            WHERE {' AND '.join(where)} ORDER BY a.occurred_at DESC LIMIT :lim""",  # noqa: S608 - constants only
        **params,
    )


@router.post("/activities", summary="Log an activity and optionally create a follow-up task", responses={422: {"description": "Needs an organization, contact or project"}})
async def create_activity(body: ActivityCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    if not (body.crm_org_id or body.contact_id or body.project_id):
        raise err(422, "ACTIVITY_TARGET_REQUIRED", "Link the activity to an organization, a contact or a project.", "crm_org_id")
    if body.crm_org_id:
        await _org(db, ctx, body.crm_org_id)
    if body.contact_id:
        await _contact(db, ctx, body.contact_id)
    if body.project_id:
        proj = await q1(db, "SELECT 1 AS ok FROM projects WHERE id = :p AND organization_id = :o AND deleted_at IS NULL", p=body.project_id, o=ctx.org_id)
        if proj is None:
            raise err(404, "PROJECT_NOT_FOUND", "Project not found.", "project_id")
    task_id = None
    if body.follow_up:
        await _check_member(db, ctx, body.follow_up.assignee_id, "assignee_id")
        assignee = body.follow_up.assignee_id or ctx.user_id
        trow = await q1(
            db,
            """INSERT INTO tasks (organization_id, project_id, assignee_id, title, description, due_date, created_by, updated_by)
               VALUES (:o, :p, :a, :t, :d, :due, :u, :u) RETURNING id""",
            o=ctx.org_id, p=body.project_id, a=assignee, t=body.follow_up.title, d=f"Follow-up from CRM activity: {body.subject}", due=body.follow_up.due_date, u=ctx.user_id,
        )
        task_id = trow["id"]
        await x(db, "INSERT INTO task_activity (organization_id, task_id, actor_id, action, detail) VALUES (:o, :t, :u, 'created', :d)", o=ctx.org_id, t=task_id, u=ctx.user_id, d=body.follow_up.title)
        await notify(db, ctx.org_id, [assignee], "task", f"New task: {body.follow_up.title}", "", f"/work?task={task_id}", exclude=ctx.user_id)
    row = await q1(
        db,
        """INSERT INTO crm_activities (organization_id, crm_org_id, contact_id, project_id, kind, subject, body, occurred_at, follow_up_task_id, created_by, updated_by)
           VALUES (:o, :co, :c, :p, :k, :s, :b, COALESCE(:at, NOW()), :t, :u, :u) RETURNING id""",
        o=ctx.org_id, co=body.crm_org_id, c=body.contact_id, p=body.project_id, k=body.kind, s=body.subject, b=body.body, at=body.occurred_at, t=task_id, u=ctx.user_id,
    )
    await db.commit()
    return {"id": row["id"], "follow_up_task_id": task_id}


@router.delete("/activities/{activity_id}", summary="Delete an activity (soft) - author or administrator")
async def delete_activity(activity_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    a = await q1(db, "SELECT created_by FROM crm_activities WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=activity_id, o=ctx.org_id)
    if a is None:
        raise err(404, "ACTIVITY_NOT_FOUND", "Activity not found.")
    if ctx.level != "org_admin" and a["created_by"] != ctx.user_id:
        raise err(403, "ACTIVITY_FORBIDDEN", "Only the author or an administrator can delete this activity.")
    await x(db, "UPDATE crm_activities SET deleted_at = NOW(), updated_by = :u WHERE id = :i", i=activity_id, u=ctx.user_id)
    await db.commit()
    return {"ok": True}


# -------------------------------------------------------------- role scopes


@router.get("/role-scopes", summary="Customer and project scopes of role assignments")
async def list_scopes(ctx: CtxDep, db: DbDep, role_id: UUID | None = None, crm_org_id: UUID | None = None, user_id: UUID | None = None) -> list[dict]:
    where = ["s.organization_id = :o"]
    params: dict[str, Any] = {"o": ctx.org_id}
    for col, expr, val in (("role_id", "ra.role_id", role_id), ("crm_org_id", "s.crm_org_id", crm_org_id), ("user_id", "ra.user_id", user_id)):
        if val:
            where.append(f"{expr} = :{col}")
            params[col] = val
    return await q(
        db,
        f"""SELECT s.id, s.scope_type, s.crm_org_id, co.name AS org_name, s.project_id, p.name AS project_name, ra.id AS role_assignment_id,
                   ra.role_id, r.name AS role_name, ra.user_id, u.display_name AS user_name
            FROM crm_role_scopes s JOIN role_assignments ra ON ra.id = s.role_assignment_id AND ra.deleted_at IS NULL JOIN roles r ON r.id = ra.role_id AND r.deleted_at IS NULL
            JOIN users u ON u.id = ra.user_id LEFT JOIN crm_organizations co ON co.id = s.crm_org_id AND co.deleted_at IS NULL LEFT JOIN projects p ON p.id = s.project_id AND p.deleted_at IS NULL
            WHERE {' AND '.join(where)} ORDER BY r.name, u.display_name""",  # noqa: S608 - constants only
        **params,
    )


async def _can_scope(db, ctx, assignment: dict) -> bool:
    if ctx.level == "org_admin":
        return True
    if ctx.level == "observer":
        return False
    role = await q1(db, "SELECT circle_id FROM roles WHERE id = :r", r=assignment["role_id"])
    return assignment["user_id"] == ctx.user_id or await _holds_role(db, ctx, assignment["role_id"]) or bool(role and await can_govern(db, ctx, role["circle_id"]))


@router.post("/role-scopes", summary="Scope a role assignment to a customer or project (e.g. Key Account)", responses={403: {"description": "Not allowed"}})
async def create_scope(body: ScopeCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    ra = await q1(db, "SELECT id, role_id, user_id FROM role_assignments WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=body.role_assignment_id, o=ctx.org_id)
    if ra is None:
        raise err(404, "ASSIGNMENT_NOT_FOUND", "Role assignment not found.", "role_assignment_id")
    if not await _can_scope(db, ctx, ra):
        raise err(403, "SCOPE_FORBIDDEN", "Only the role holder, governance roles or administrators can scope an assignment.")
    if body.scope_type == "organization":
        if body.crm_org_id is None or body.project_id is not None:
            raise err(422, "SCOPE_INVALID", "An organization scope needs crm_org_id only.", "crm_org_id")
        await _org(db, ctx, body.crm_org_id)
    else:
        if body.project_id is None or body.crm_org_id is not None:
            raise err(422, "SCOPE_INVALID", "A project scope needs project_id only.", "project_id")
        proj = await q1(db, "SELECT 1 AS ok FROM projects WHERE id = :p AND organization_id = :o AND deleted_at IS NULL", p=body.project_id, o=ctx.org_id)
        if proj is None:
            raise err(404, "PROJECT_NOT_FOUND", "Project not found.", "project_id")
    row = await q1(
        db,
        """INSERT INTO crm_role_scopes (organization_id, role_assignment_id, scope_type, crm_org_id, project_id, created_by) VALUES (:o, :ra, :t, :c, :p, :u)
           ON CONFLICT DO NOTHING RETURNING id""",
        o=ctx.org_id, ra=body.role_assignment_id, t=body.scope_type, c=body.crm_org_id, p=body.project_id, u=ctx.user_id,
    )
    await audit(db, ctx, "crm.role_scoped", "role_assignment", body.role_assignment_id, f"{body.scope_type} scope added")
    await db.commit()
    return {"id": row["id"] if row else None}


@router.delete("/role-scopes/{scope_id}", summary="Remove a scope from a role assignment")
async def delete_scope(scope_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    s = await q1(db, "SELECT s.id, ra.role_id, ra.user_id FROM crm_role_scopes s JOIN role_assignments ra ON ra.id = s.role_assignment_id WHERE s.id = :i AND s.organization_id = :o", i=scope_id, o=ctx.org_id)
    if s is None:
        raise err(404, "SCOPE_NOT_FOUND", "Scope not found.")
    if not await _can_scope(db, ctx, s):
        raise err(403, "SCOPE_FORBIDDEN", "Only the role holder, governance roles or administrators can change this scope.")
    await x(db, "DELETE FROM crm_role_scopes WHERE id = :i", i=scope_id)
    await db.commit()
    return {"ok": True}


# --------------------------------------------------------------- dashboard


@router.get("/dashboard", summary="CRM dashboard figures (foundation phase)")
async def dashboard(ctx: CtxDep, db: DbDep) -> dict:
    counts = await q1(
        db,
        """SELECT
             COUNT(*) FILTER (WHERE 'customer' = ANY(relation_types) AND status = 'active') AS active_customers,
             COUNT(*) FILTER (WHERE 'prospect' = ANY(relation_types) AND status = 'active') AS prospects,
             COUNT(*) FILTER (WHERE ('partner' = ANY(relation_types) OR 'research_partner' = ANY(relation_types)) AND status = 'active') AS partners,
             COUNT(*) FILTER (WHERE 'customer' = ANY(relation_types) AND status = 'active' AND owner_user_id IS NULL) AS without_owner
           FROM crm_organizations WHERE organization_id = :o AND deleted_at IS NULL""",
        o=ctx.org_id,
    )
    contacts = await q1(db, "SELECT COUNT(*) AS n FROM crm_contacts WHERE organization_id = :o AND deleted_at IS NULL", o=ctx.org_id)
    projects = await q1(
        db,
        """SELECT COUNT(DISTINCT p.id) AS n FROM projects p JOIN project_orgs po ON po.project_id = p.id AND po.relation = 'customer'
           WHERE p.organization_id = :o AND p.deleted_at IS NULL AND p.classification = 'customer' AND p.status IN ('planned','active')""",
        o=ctx.org_id,
    )
    stale = await q1(
        db,
        """SELECT COUNT(*) AS n FROM crm_organizations co WHERE co.organization_id = :o AND co.deleted_at IS NULL AND co.status = 'active' AND 'customer' = ANY(co.relation_types)
             AND COALESCE((SELECT MAX(a.occurred_at) FROM crm_activities a WHERE a.crm_org_id = co.id AND a.deleted_at IS NULL), TIMESTAMPTZ '1970-01-01') < NOW() - INTERVAL '90 days'""",
        o=ctx.org_id,
    )
    follow_ups = await q1(
        db,
        """SELECT COUNT(*) AS n, COUNT(*) FILTER (WHERE t.due_date < CURRENT_DATE) AS overdue FROM crm_activities a JOIN tasks t ON t.id = a.follow_up_task_id AND t.deleted_at IS NULL AND t.status <> 'done'
           WHERE a.organization_id = :o AND a.deleted_at IS NULL""",
        o=ctx.org_id,
    )
    recent = await list_activities(ctx, db, limit=8)
    unowned = await q(db, "SELECT id, name FROM crm_organizations WHERE organization_id = :o AND deleted_at IS NULL AND status = 'active' AND 'customer' = ANY(relation_types) AND owner_user_id IS NULL ORDER BY name LIMIT 8", o=ctx.org_id)
    return {
        **(counts or {}), "contacts": contacts["n"] if contacts else 0, "active_customer_projects": projects["n"] if projects else 0,
        "customers_without_recent_activity": stale["n"] if stale else 0, "open_follow_ups": follow_ups["n"] if follow_ups else 0,
        "overdue_follow_ups": follow_ups["overdue"] if follow_ups else 0, "recent_activities": recent, "customers_without_owner": unowned,
        "planned_modules": PLANNED_MODULES,
    }
