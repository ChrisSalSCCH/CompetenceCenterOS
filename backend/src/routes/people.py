"""People directory, personal dashboard and my-roles overview."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter
from services.ctx import CtxDep
from services.dbx import DbDep, err, q, q1
from services.orgdata import history_rows, load_structure

router = APIRouter(prefix="/api", tags=["people"])


@router.get("/people", summary="People directory with role counts")
async def list_people(ctx: CtxDep, db: DbDep) -> list[dict]:
    people = await q(
        db,
        """SELECT u.id, u.display_name AS name, u.email, m.job_title, m.skills, m.availability, m.avatar_color, m.access_level,
                  (SELECT COUNT(*) FROM role_assignments ra JOIN roles r ON r.id = ra.role_id AND r.deleted_at IS NULL
                     WHERE ra.user_id = u.id AND ra.organization_id = :o AND ra.deleted_at IS NULL) AS role_count,
                  (SELECT COUNT(*) FROM tasks t WHERE t.assignee_id = u.id AND t.organization_id = :o AND t.deleted_at IS NULL AND t.status <> 'done') AS open_tasks
           FROM memberships m JOIN users u ON u.id = m.user_id WHERE m.organization_id = :o AND m.active ORDER BY u.display_name""",
        o=ctx.org_id,
    )
    roles = await q(
        db,
        """SELECT ra.user_id, r.id AS role_id, r.name AS role_name, c.id AS circle_id, c.name AS circle_name
           FROM role_assignments ra JOIN roles r ON r.id = ra.role_id AND r.deleted_at IS NULL
           JOIN circles c ON c.id = r.circle_id AND c.deleted_at IS NULL
           WHERE ra.organization_id = :o AND ra.deleted_at IS NULL ORDER BY c.name, r.name""",
        o=ctx.org_id,
    )
    by_user: dict[Any, list[dict]] = {}
    for r in roles:
        by_user.setdefault(r["user_id"], []).append(r)
    for p in people:
        p["roles"] = by_user.get(p["id"], [])
    return people


@router.get("/people/{user_id}", summary="Person detail: roles, circles, work", responses={404: {"description": "Person not found"}})
async def person_detail(user_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    p = await q1(
        db,
        """SELECT u.id, u.display_name AS name, u.email, m.job_title, m.skills, m.availability, m.avatar_color, m.access_level, m.notification_prefs
           FROM memberships m JOIN users u ON u.id = m.user_id WHERE m.organization_id = :o AND u.id = :u AND m.active""",
        o=ctx.org_id, u=user_id,
    )
    if p is None:
        raise err(404, "PERSON_NOT_FOUND", "Person not found.")
    if user_id != ctx.user_id and ctx.level != "org_admin":
        p.pop("notification_prefs", None)
    structure = await load_structure(db, ctx.org_id)
    cname = {c["id"]: c["name"] for c in structure["circles"]}
    roles = []
    for r in structure["roles"]:
        for h in r["holders"]:
            if h["user_id"] == user_id:
                roles.append({"role_id": r["id"], "role_name": r["name"], "purpose": r["purpose"], "circle_id": r["circle_id"], "circle_name": cname.get(r["circle_id"]), "focus": h["focus"], "assignment_id": h["assignment_id"]})
    circles: dict[Any, dict] = {}
    for r in roles:
        circles.setdefault(r["circle_id"], {"id": r["circle_id"], "name": r["circle_name"], "roles": []})["roles"].append(r["role_name"])
    tasks = await q(
        db,
        """SELECT t.id, t.title, t.status, t.priority, t.due_date, (t.due_date < CURRENT_DATE AND t.status <> 'done') AS is_overdue, p.name AS project_name
           FROM tasks t LEFT JOIN projects p ON p.id = t.project_id
           WHERE t.assignee_id = :u AND t.organization_id = :o AND t.deleted_at IS NULL AND t.status <> 'done' ORDER BY t.due_date NULLS LAST LIMIT 30""",
        u=user_id, o=ctx.org_id,
    )
    projects = await q(
        db,
        """SELECT DISTINCT p.id, p.name, p.status FROM projects p
           WHERE p.organization_id = :o AND p.deleted_at IS NULL AND p.status IN ('planned','active','on_hold') AND
             (p.id IN (SELECT project_id FROM project_people WHERE user_id = :u)
              OR p.owning_role_id IN (SELECT role_id FROM role_assignments WHERE user_id = :u AND deleted_at IS NULL))""",
        o=ctx.org_id, u=user_id,
    )
    return {**p, "roles": roles, "circles": list(circles.values()), "tasks": tasks, "projects": projects}


@router.get("/my-roles", summary="Own roles with accountabilities, domains, authorities and linked work")
async def my_roles(ctx: CtxDep, db: DbDep) -> list[dict]:
    structure = await load_structure(db, ctx.org_id)
    cname = {c["id"]: c["name"] for c in structure["circles"]}
    mine = [r for r in structure["roles"] if any(h["user_id"] == ctx.user_id for h in r["holders"])]
    out: list[dict] = []
    for r in mine:
        tasks = await q(db, "SELECT id, title, status, due_date, (due_date < CURRENT_DATE AND status <> 'done') AS is_overdue FROM tasks WHERE role_id = :r AND deleted_at IS NULL AND status <> 'done' ORDER BY due_date NULLS LAST LIMIT 8", r=r["id"])
        projects = await q(db, "SELECT id, name, status FROM projects WHERE owning_role_id = :r AND deleted_at IS NULL AND status IN ('planned','active','on_hold')", r=r["id"])
        metrics = await q(db, "SELECT id, name, unit, target_value, current_value FROM metrics WHERE role_id = :r AND deleted_at IS NULL", r=r["id"])
        focus = next((h["focus"] for h in r["holders"] if h["user_id"] == ctx.user_id), None)
        out.append({**{k: r[k] for k in ("id", "name", "purpose", "circle_id", "accountabilities", "domains", "authorities", "policies", "can_govern")}, "circle_name": cname.get(r["circle_id"]), "focus": focus, "co_holders": [h["name"] for h in r["holders"] if h["user_id"] != ctx.user_id], "tasks": tasks, "projects": projects, "metrics": metrics})
    return out


@router.get("/dashboard", summary="What requires my attention today")
async def dashboard(ctx: CtxDep, db: DbDep) -> dict:
    roles = await q(
        db,
        """SELECT r.id AS role_id, r.name AS role_name, c.id AS circle_id, c.name AS circle_name, r.purpose
           FROM role_assignments ra JOIN roles r ON r.id = ra.role_id AND r.deleted_at IS NULL
           JOIN circles c ON c.id = r.circle_id AND c.deleted_at IS NULL
           WHERE ra.user_id = :u AND ra.organization_id = :o AND ra.deleted_at IS NULL ORDER BY c.name, r.name""",
        u=ctx.user_id, o=ctx.org_id,
    )
    tasks = await q(
        db,
        """SELECT t.id, t.title, t.status, t.priority, t.due_date, (t.due_date < CURRENT_DATE AND t.status <> 'done') AS is_overdue,
                  p.name AS project_name, r.name AS role_name
           FROM tasks t LEFT JOIN projects p ON p.id = t.project_id LEFT JOIN roles r ON r.id = t.role_id
           WHERE t.assignee_id = :u AND t.organization_id = :o AND t.deleted_at IS NULL AND t.status <> 'done'
           ORDER BY (t.due_date < CURRENT_DATE) DESC NULLS LAST, t.due_date NULLS LAST LIMIT 40""",
        u=ctx.user_id, o=ctx.org_id,
    )
    meetings = await q(
        db,
        """SELECT m.id, m.title, m.meeting_type, m.scheduled_at, m.status, c.name AS circle_name
           FROM meetings m JOIN circles c ON c.id = m.circle_id
           WHERE m.organization_id = :o AND m.deleted_at IS NULL AND m.status IN ('scheduled','in_progress')
             AND m.id IN (SELECT meeting_id FROM meeting_participants WHERE user_id = :u) ORDER BY m.scheduled_at LIMIT 6""",
        u=ctx.user_id, o=ctx.org_id,
    )
    tensions = await q(
        db,
        """SELECT t.id, t.title, t.priority, t.status, c.name AS circle_name FROM tensions t LEFT JOIN circles c ON c.id = t.circle_id
           WHERE t.creator_id = :u AND t.organization_id = :o AND t.deleted_at IS NULL AND t.status IN ('open','processing')
           ORDER BY CASE t.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, t.created_at DESC LIMIT 6""",
        u=ctx.user_id, o=ctx.org_id,
    )
    if ctx.level == "org_admin":
        gov = [r["id"] for r in await q(db, "SELECT id FROM circles WHERE organization_id = :o AND deleted_at IS NULL", o=ctx.org_id)]
    elif ctx.level == "observer":
        gov = []
    else:
        gov = [
            r["id"]
            for r in await q(
                db,
                """WITH RECURSIVE g AS (
                       SELECT DISTINCT r.circle_id AS id FROM role_assignments ra JOIN roles r ON r.id = ra.role_id AND r.deleted_at IS NULL AND r.can_govern
                       WHERE ra.user_id = :u AND ra.organization_id = :o AND ra.deleted_at IS NULL
                     UNION SELECT c.id FROM circles c JOIN g ON c.parent_id = g.id WHERE c.deleted_at IS NULL
                   ) SELECT id FROM g""",
                u=ctx.user_id, o=ctx.org_id,
            )
        ]
    proposals = await q(
        db,
        """SELECT gp.id, gp.title, gp.status, gp.workflow, c.name AS circle_name, gp.initiator_id,
                  CASE WHEN gp.initiator_id = :u AND gp.status = 'draft' THEN 'finish_draft'
                       WHEN gp.circle_id = ANY(:gov) THEN 'decide' ELSE 'follow' END AS action
           FROM governance_proposals gp JOIN circles c ON c.id = gp.circle_id
           WHERE gp.organization_id = :o AND gp.deleted_at IS NULL AND gp.status NOT IN ('accepted','rejected','withdrawn')
             AND ((gp.initiator_id = :u AND gp.status = 'draft') OR (gp.circle_id = ANY(:gov) AND gp.status <> 'draft'))
           ORDER BY gp.created_at DESC LIMIT 8""",
        u=ctx.user_id, o=ctx.org_id, gov=gov,
    )
    circle_ids = list({r["circle_id"] for r in roles})
    updates: list[dict[str, Any]] = []
    if circle_ids:
        updates = await history_rows(db, ctx.org_id, "gc.circle_id = ANY(:cids) AND gc.source <> 'seed'", 6, cids=circle_ids)
    counts = await q1(
        db,
        """SELECT
             (SELECT COUNT(*) FROM tasks WHERE assignee_id = :u AND organization_id = :o AND deleted_at IS NULL AND status <> 'done') AS open_tasks,
             (SELECT COUNT(*) FROM tasks WHERE assignee_id = :u AND organization_id = :o AND deleted_at IS NULL AND status <> 'done' AND due_date < CURRENT_DATE) AS overdue_tasks""",
        u=ctx.user_id, o=ctx.org_id,
    )
    return {
        "roles": roles,
        "tasks": tasks,
        "meetings": meetings,
        "tensions": tensions,
        "proposals": proposals,
        "circle_updates": updates,
        "counts": counts,
    }
