"""Organization structure: circles, roles, role assignments."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field, HttpUrl
from services.analysis import find_overlaps
from services.ctx import (
    CtxDep,
    can_govern,
    circle_ancestors,
    effective_mode,
    require_circle,
    require_govern,
    require_role,
    require_write,
)
from services.dbx import DbDep, err, q, q1, x
from services.events import audit, notify
from services.governance import ChangeOp, submit_structural_change
from services.orgdata import history_rows, load_structure, load_structure_as_of

router = APIRouter(prefix="/api", tags=["structure"])

GovMode = Literal["direct", "approval", "consent", "holacracy"]


class ItemIn(BaseModel):
    text: str = Field(min_length=1, max_length=600)
    detail: str | None = Field(default=None, max_length=2000)
    level: Literal["decides", "consents", "consulted", "informed"] | None = None


Items = Annotated[list[ItemIn], Field(max_length=60)]


class CircleCreate(BaseModel):
    parent_id: UUID
    name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(default="", max_length=2000)
    description: str = Field(default="", max_length=10000)
    governance_mode: GovMode | None = None
    accountabilities: Items = []
    domains: Items = []
    policies: Items = []
    reason: str = Field(default="", max_length=2000)


class CircleUpdate(BaseModel):
    parent_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    purpose: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=10000)
    governance_mode: GovMode | None = None
    accountabilities: Items | None = None
    domains: Items | None = None
    policies: Items | None = None
    reason: str = Field(default="", max_length=2000)


class RoleCreate(BaseModel):
    circle_id: UUID
    name: str = Field(min_length=1, max_length=120)
    purpose: str = Field(default="", max_length=2000)
    description: str = Field(default="", max_length=10000)
    allow_multiple: bool = False
    can_govern: bool = False
    template_key: str | None = Field(default=None, max_length=60)
    accountabilities: Items = []
    domains: Items = []
    policies: Items = []
    authorities: Items = []
    reason: str = Field(default="", max_length=2000)


class RoleUpdate(BaseModel):
    circle_id: UUID | None = None
    name: str | None = Field(default=None, min_length=1, max_length=120)
    purpose: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=10000)
    allow_multiple: bool | None = None
    can_govern: bool | None = None
    accountabilities: Items | None = None
    domains: Items | None = None
    policies: Items | None = None
    authorities: Items | None = None
    reason: str = Field(default="", max_length=2000)


class AssignmentCreate(BaseModel):
    user_id: UUID
    focus: str | None = Field(default=None, max_length=200)


class LeadUpdate(BaseModel):
    lead_user_id: UUID | None = None


class AttachmentCreate(BaseModel):
    entity_type: Literal["task", "role", "project", "circle"]
    entity_id: UUID
    name: str = Field(min_length=1, max_length=200)
    url: HttpUrl


# ------------------------------------------------------------------ reads


@router.get("/structure", summary="All circles and roles (optionally as of a past date)")
async def structure(ctx: CtxDep, db: DbDep, as_of: datetime | None = None) -> dict:
    if as_of is not None:
        data = await load_structure_as_of(db, ctx.org_id, as_of)
        return {**data, "as_of": as_of, "historical": True}
    data = await load_structure(db, ctx.org_id)
    return {**data, "as_of": None, "historical": False}


@router.get("/structure/analysis", summary="Unfilled roles and overlapping responsibilities")
async def structure_analysis(ctx: CtxDep, db: DbDep) -> dict:
    data = await load_structure(db, ctx.org_id)
    cname = {c["id"]: c["name"] for c in data["circles"]}
    unfilled = [
        {"role_id": r["id"], "role_name": r["name"], "circle_id": r["circle_id"], "circle_name": cname.get(r["circle_id"])}
        for r in data["roles"]
        if not r["holders"]
    ]
    flat: list[dict[str, Any]] = []
    for r in data["roles"]:
        for key, kind in (("accountabilities", "accountability"), ("domains", "domain"), ("authorities", "decision_authority")):
            for it in r[key]:
                flat.append({"role_id": r["id"], "role_name": r["name"], "kind": kind, "text": it["text"]})
    return {"unfilled_roles": unfilled, "overlaps": find_overlaps(flat)}


@router.get("/circles/{circle_id}", summary="Circle detail", responses={404: {"description": "Circle not found"}})
async def circle_detail(circle_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    await require_circle(db, ctx, circle_id)
    data = await load_structure(db, ctx.org_id)
    circle = next(c for c in data["circles"] if c["id"] == circle_id)
    ancestors = await circle_ancestors(db, ctx.org_id, circle_id)
    breadcrumb = [{"id": a["id"], "name": a["name"]} for a in reversed(ancestors)]
    subs = [c for c in data["circles"] if c["parent_id"] == circle_id]
    roles = [r for r in data["roles"] if r["circle_id"] == circle_id]
    members: dict[UUID, dict[str, Any]] = {}
    for r in roles:
        for h in r["holders"]:
            m = members.setdefault(h["user_id"], {"user_id": h["user_id"], "name": h["name"], "avatar_color": h["avatar_color"], "roles": []})
            m["roles"].append({"id": r["id"], "name": r["name"]})
    projects = await q(
        db,
        """SELECT p.id, p.name, p.status, p.priority, p.due_date, r.name AS owning_role_name
           FROM projects p LEFT JOIN roles r ON r.id = p.owning_role_id
           WHERE p.circle_id = :c AND p.organization_id = :o AND p.deleted_at IS NULL AND p.status IN ('planned','active','on_hold')
           ORDER BY p.due_date NULLS LAST""",
        c=circle_id, o=ctx.org_id,
    )
    tasks = await q(
        db,
        """SELECT t.id, t.title, t.status, t.priority, t.due_date, u.display_name AS assignee_name
           FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id
           WHERE t.organization_id = :o AND t.deleted_at IS NULL AND t.status <> 'done'
             AND (t.circle_id = :c OR t.project_id IN (SELECT id FROM projects WHERE circle_id = :c))
           ORDER BY t.due_date NULLS LAST LIMIT 50""",
        c=circle_id, o=ctx.org_id,
    )
    proposals = await q(
        db,
        """SELECT id, title, status, workflow, proposal_type, created_at FROM governance_proposals
           WHERE circle_id = :c AND organization_id = :o AND deleted_at IS NULL ORDER BY created_at DESC LIMIT 20""",
        c=circle_id, o=ctx.org_id,
    )
    meetings = await q(
        db,
        """SELECT id, title, meeting_type, scheduled_at, status FROM meetings
           WHERE circle_id = :c AND organization_id = :o AND deleted_at IS NULL ORDER BY scheduled_at DESC LIMIT 20""",
        c=circle_id, o=ctx.org_id,
    )
    history = await history_rows(db, ctx.org_id, "gc.circle_id = :c", 40, c=circle_id)
    mode = await effective_mode(db, ctx, circle_id)
    return {
        **circle,
        "breadcrumb": breadcrumb,
        "subcircles": subs,
        "roles": roles,
        "members": list(members.values()),
        "projects": projects,
        "tasks": tasks,
        "proposals": proposals,
        "meetings": meetings,
        "history": history,
        "effective_mode": mode,
        "can_govern": await can_govern(db, ctx, circle_id),
    }


@router.get("/roles/{role_id}", summary="Role detail", responses={404: {"description": "Role not found"}})
async def role_detail(role_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    await require_role(db, ctx, role_id)
    data = await load_structure(db, ctx.org_id)
    role = next(r for r in data["roles"] if r["id"] == role_id)
    circle_id = role["circle_id"]
    ancestors = await circle_ancestors(db, ctx.org_id, circle_id)
    breadcrumb = [{"id": a["id"], "name": a["name"]} for a in reversed(ancestors)]
    related: dict[UUID, dict[str, Any]] = {}
    for r in data["roles"]:
        if r["id"] != role_id and r["circle_id"] == circle_id:
            related[r["id"]] = {"id": r["id"], "name": r["name"], "circle_id": r["circle_id"], "relation": "same_circle", "note": None}
    flat: list[dict[str, Any]] = []
    for r in data["roles"]:
        for key, kind in (("accountabilities", "accountability"), ("domains", "domain"), ("authorities", "decision_authority")):
            for it in r[key]:
                flat.append({"role_id": r["id"], "role_name": r["name"], "kind": kind, "text": it["text"]})
    overlaps = [o for o in find_overlaps(flat) if role_id in (o["a"]["role_id"], o["b"]["role_id"])]
    rname = {r["id"]: r for r in data["roles"]}
    for o in overlaps:
        other = o["b"] if o["a"]["role_id"] == role_id else o["a"]
        orole = rname[other["role_id"]]
        related[orole["id"]] = {
            "id": orole["id"], "name": orole["name"], "circle_id": orole["circle_id"],
            "relation": "overlap", "note": f"{o['severity']}: {other['text']}",
        }
    tasks = await q(
        db,
        """SELECT t.id, t.title, t.status, t.priority, t.due_date, u.display_name AS assignee_name
           FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id
           WHERE t.role_id = :r AND t.organization_id = :o AND t.deleted_at IS NULL AND t.status <> 'done'
           ORDER BY t.due_date NULLS LAST LIMIT 50""",
        r=role_id, o=ctx.org_id,
    )
    projects = await q(
        db,
        """SELECT id, name, status, priority, due_date FROM projects
           WHERE owning_role_id = :r AND organization_id = :o AND deleted_at IS NULL ORDER BY created_at DESC""",
        r=role_id, o=ctx.org_id,
    )
    metrics = await q(
        db,
        """SELECT id, name, unit, target_value, current_value, direction FROM metrics
           WHERE role_id = :r AND organization_id = :o AND deleted_at IS NULL""",
        r=role_id, o=ctx.org_id,
    )
    docs = await q(
        db,
        """SELECT id, name, url, created_at FROM attachments
           WHERE entity_type = 'role' AND entity_id = :r AND organization_id = :o AND deleted_at IS NULL ORDER BY created_at DESC""",
        r=role_id, o=ctx.org_id,
    )
    tensions = await q(
        db,
        """SELECT id, title, status, priority FROM tensions
           WHERE role_id = :r AND organization_id = :o AND deleted_at IS NULL AND status IN ('open','processing')""",
        r=role_id, o=ctx.org_id,
    )
    history = await history_rows(db, ctx.org_id, "gc.entity_type = 'role' AND gc.entity_id = :r", 40, r=role_id)
    circle = next(c for c in data["circles"] if c["id"] == circle_id)
    return {
        **role,
        "circle_name": circle["name"],
        "breadcrumb": breadcrumb,
        "related_roles": list(related.values()),
        "tasks": tasks,
        "projects": projects,
        "metrics": metrics,
        "documents": docs,
        "tensions": tensions,
        "history": history,
        "effective_mode": await effective_mode(db, ctx, circle_id),
        "can_govern": await can_govern(db, ctx, circle_id),
    }


# ------------------------------------------------------------------ writes


def _result(res: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {"applied": res["applied"], "mode": res["mode"]}
    if res["applied"]:
        out["entity_id"] = res["changes"][0]["entity_id"]
    else:
        out["proposal_id"] = res["proposal_id"]
    return out


@router.post("/circles", summary="Create a circle (directly or via governance proposal)")
async def create_circle(body: CircleCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    await require_circle(db, ctx, body.parent_id)
    data = body.model_dump(mode="json", exclude={"reason"})
    res = await submit_structural_change(
        db, ctx, body.parent_id, [ChangeOp(op="create_circle", data=data)],
        title=f"Create circle “{body.name}”", reason=body.reason,
    )
    await db.commit()
    return _result(res)


@router.patch("/circles/{circle_id}", summary="Edit or move a circle", responses={409: {"description": "Cycle or root restriction"}})
async def update_circle(circle_id: UUID, body: CircleUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    circle = await require_circle(db, ctx, circle_id)
    data = body.model_dump(mode="json", exclude_unset=True, exclude={"reason"})
    if not data:
        raise err(422, "NO_CHANGES", "Nothing to change.")
    res = await submit_structural_change(
        db, ctx, circle_id, [ChangeOp(op="update_circle", id=circle_id, data=data)],
        title=f"Change circle “{circle['name']}”", reason=body.reason,
    )
    await db.commit()
    return _result(res)


@router.delete("/circles/{circle_id}", summary="Remove an empty circle")
async def delete_circle(circle_id: UUID, ctx: CtxDep, db: DbDep, reason: str = "") -> dict:
    require_write(ctx)
    circle = await require_circle(db, ctx, circle_id)
    scope = circle["parent_id"] or circle_id
    res = await submit_structural_change(
        db, ctx, scope, [ChangeOp(op="delete_circle", id=circle_id)],
        title=f"Remove circle “{circle['name']}”", reason=reason[:2000],
    )
    await db.commit()
    return _result(res)


@router.post("/roles", summary="Create a role (directly or via governance proposal)")
async def create_role(body: RoleCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    await require_circle(db, ctx, body.circle_id)
    data = body.model_dump(mode="json", exclude={"reason"})
    res = await submit_structural_change(
        db, ctx, body.circle_id, [ChangeOp(op="create_role", data=data)],
        title=f"Create role “{body.name}”", reason=body.reason,
    )
    await db.commit()
    return _result(res)


@router.patch("/roles/{role_id}", summary="Edit a role")
async def update_role(role_id: UUID, body: RoleUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    role = await require_role(db, ctx, role_id)
    data = body.model_dump(mode="json", exclude_unset=True, exclude={"reason"})
    if not data:
        raise err(422, "NO_CHANGES", "Nothing to change.")
    res = await submit_structural_change(
        db, ctx, role["circle_id"], [ChangeOp(op="update_role", id=role_id, data=data)],
        title=f"Change role “{role['name']}”", reason=body.reason,
    )
    await db.commit()
    return _result(res)


@router.delete("/roles/{role_id}", summary="Remove a role")
async def delete_role(role_id: UUID, ctx: CtxDep, db: DbDep, reason: str = "") -> dict:
    require_write(ctx)
    role = await require_role(db, ctx, role_id)
    res = await submit_structural_change(
        db, ctx, role["circle_id"], [ChangeOp(op="delete_role", id=role_id)],
        title=f"Remove role “{role['name']}”", reason=reason[:2000],
    )
    await db.commit()
    return _result(res)


# ------------------------------------------------------- operational: assignments


@router.post("/roles/{role_id}/assignments", summary="Assign a person to a role", responses={409: {"description": "Role already filled or duplicate"}})
async def assign_role(role_id: UUID, body: AssignmentCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    role = await require_role(db, ctx, role_id)
    await require_govern(db, ctx, role["circle_id"])
    member = await q1(db, "SELECT 1 AS ok FROM memberships WHERE organization_id = :o AND user_id = :u AND active", o=ctx.org_id, u=body.user_id)
    if member is None:
        raise err(404, "PERSON_NOT_FOUND", "This person is not a member of the organization.", "user_id")
    existing = await q(db, "SELECT user_id FROM role_assignments WHERE role_id = :r AND deleted_at IS NULL", r=role_id)
    if any(e["user_id"] == body.user_id for e in existing):
        raise err(409, "ALREADY_ASSIGNED", "This person already holds the role.")
    if existing and not role["allow_multiple"]:
        raise err(409, "ROLE_ALREADY_FILLED", "This role allows a single role holder. Unassign the current holder first or enable multiple holders.")
    row = await q1(
        db,
        """INSERT INTO role_assignments (organization_id, role_id, user_id, focus, created_by, updated_by)
           VALUES (:o, :r, :u, :f, :a, :a) RETURNING id""",
        o=ctx.org_id, r=role_id, u=body.user_id, f=body.focus, a=ctx.user_id,
    )
    await audit(db, ctx, "role.assigned", "role", role_id, f"Assigned {body.user_id} to {role['name']}")
    await notify(db, ctx.org_id, [body.user_id], "governance", f"You now hold the role {role['name']}", "", f"/organization/roles/{role_id}", exclude=ctx.user_id)
    await db.commit()
    return {"id": row["id"]}


@router.delete("/assignments/{assignment_id}", summary="Remove a role assignment")
async def unassign(assignment_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    a = await q1(
        db,
        """SELECT ra.id, ra.user_id, ra.role_id, r.circle_id, r.name FROM role_assignments ra
           JOIN roles r ON r.id = ra.role_id WHERE ra.id = :id AND ra.organization_id = :o AND ra.deleted_at IS NULL""",
        id=assignment_id, o=ctx.org_id,
    )
    if a is None:
        raise err(404, "ASSIGNMENT_NOT_FOUND", "Assignment not found.")
    if a["user_id"] != ctx.user_id:
        await require_govern(db, ctx, a["circle_id"])
    await x(db, "UPDATE role_assignments SET deleted_at = NOW(), updated_by = :u WHERE id = :id", id=assignment_id, u=ctx.user_id)
    await x(db, "UPDATE roles SET lead_user_id = NULL WHERE id = :r AND lead_user_id = :u", r=a["role_id"], u=a["user_id"])
    await audit(db, ctx, "role.unassigned", "role", a["role_id"], f"Removed assignment from {a['name']}")
    await db.commit()
    return {"ok": True}


@router.put("/roles/{role_id}/lead", summary="Set or clear the optional role lead")
async def set_lead(role_id: UUID, body: LeadUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    role = await require_role(db, ctx, role_id)
    await require_govern(db, ctx, role["circle_id"])
    if body.lead_user_id is not None:
        holder = await q1(db, "SELECT 1 AS ok FROM role_assignments WHERE role_id = :r AND user_id = :u AND deleted_at IS NULL", r=role_id, u=body.lead_user_id)
        if holder is None:
            raise err(422, "LEAD_NOT_HOLDER", "The role lead must be one of the role holders.", "lead_user_id")
    await x(db, "UPDATE roles SET lead_user_id = :l, updated_at = NOW() WHERE id = :r", l=body.lead_user_id, r=role_id)
    await db.commit()
    return {"ok": True}


@router.post("/attachments", summary="Attach a document link to a role, task, project or circle")
async def add_attachment(body: AttachmentCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    table = {"task": "tasks", "role": "roles", "project": "projects", "circle": "circles"}[body.entity_type]
    owner = await q1(db, f"SELECT id FROM {table} WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=body.entity_id, o=ctx.org_id)  # noqa: S608
    if owner is None:
        raise err(404, "ENTITY_NOT_FOUND", "The target of the attachment was not found.")
    row = await q1(
        db,
        """INSERT INTO attachments (organization_id, entity_type, entity_id, name, url, created_by)
           VALUES (:o, :t, :i, :n, :u, :a) RETURNING id""",
        o=ctx.org_id, t=body.entity_type, i=body.entity_id, n=body.name, u=str(body.url), a=ctx.user_id,
    )
    await db.commit()
    return {"id": row["id"]}


@router.delete("/attachments/{attachment_id}", summary="Remove an attachment")
async def delete_attachment(attachment_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    await x(db, "UPDATE attachments SET deleted_at = NOW() WHERE id = :id AND organization_id = :o", id=attachment_id, o=ctx.org_id)
    await db.commit()
    return {"ok": True}


# --------------------------------------------------------------- role templates

ROLE_TEMPLATES: list[dict[str, Any]] = [
    {
        "key": "facilitator", "name": "Facilitator",
        "purpose": "Meetings in this circle are effective, inclusive and follow the agreed process.",
        "accountabilities": ["Facilitating the circle's governance and tactical meetings", "Coaching members on the meeting process"],
        "domains": ["Meeting process and agenda rules"], "authorities": ["Deciding how to apply the meeting process in edge cases"],
    },
    {
        "key": "secretary", "name": "Secretary",
        "purpose": "The circle's records are complete, accessible and trustworthy.",
        "accountabilities": ["Scheduling the circle's meetings", "Capturing and publishing meeting outcomes", "Maintaining the circle's governance records"],
        "domains": ["Circle records and meeting minutes"], "authorities": [],
    },
    {
        "key": "project_manager", "name": "Project Manager",
        "purpose": "Projects are planned, tracked and delivered with transparent status.",
        "accountabilities": ["Planning milestones and tracking progress of the circle's projects", "Surfacing risks and blockers early", "Keeping project status up to date"],
        "domains": ["Project plans and timelines"], "authorities": ["Deciding project sequencing within agreed scope"],
    },
    {
        "key": "product_owner", "name": "Product Owner",
        "purpose": "Customer value is maximised through a clear, prioritised product backlog.",
        "accountabilities": ["Maintaining and prioritising the product backlog", "Clarifying requirements with stakeholders", "Accepting delivered increments"],
        "domains": ["Product backlog"], "authorities": ["Deciding backlog priority"],
    },
    {
        "key": "quality_steward", "name": "Quality Steward",
        "purpose": "Deliverables meet the agreed quality standards.",
        "accountabilities": ["Defining and maintaining quality standards", "Reviewing deliverables against the standards"],
        "domains": ["Quality standards and checklists"], "authorities": ["Deciding whether a deliverable meets the quality bar"],
    },
    {
        "key": "people_lead", "name": "People Lead",
        "purpose": "People grow, feel supported and contribute their strengths.",
        "accountabilities": ["Supporting personal development conversations", "Coordinating onboarding of new members", "Maintaining the skills overview"],
        "domains": ["Development plans"], "authorities": [],
    },
    {
        "key": "community_steward", "name": "Community Steward",
        "purpose": "Relationships with customers and partners are healthy and long lasting.",
        "accountabilities": ["Maintaining relationships with key customers and partners", "Collecting and relaying external feedback"],
        "domains": ["Customer and partner contact data"], "authorities": [],
    },
    {
        "key": "finance_steward", "name": "Finance Steward",
        "purpose": "The circle uses its financial resources transparently and sustainably.",
        "accountabilities": ["Tracking the circle's budget", "Preparing financial reports"],
        "domains": ["Circle budget"], "authorities": ["Approving expenses within the circle budget"],
    },
]


@router.get("/role-templates", summary="Reusable role templates")
async def role_templates(ctx: CtxDep) -> list[dict]:
    _ = ctx
    return ROLE_TEMPLATES
