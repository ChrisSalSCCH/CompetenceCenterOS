"""Operational work: projects (accountability sits with a role) and tasks (executed by people)."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from services.ctx import CtxDep, can_govern, require_circle, require_write
from services.dbx import DbDep, err, q, q1, set_clause, x
from services.events import audit, notify

router = APIRouter(prefix="/api", tags=["work"])

Priority = Literal["low", "medium", "high"]
TaskStatus = Literal["todo", "doing", "blocked", "done"]
ProjectStatus = Literal["planned", "active", "on_hold", "done", "cancelled"]
PROJECT_NOT_FOUND = "Project not found."
TASK_NOT_FOUND = "Task not found."


class ProjectCreate(BaseModel):
    name: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=10000)
    circle_id: UUID
    owning_role_id: UUID | None = None
    status: ProjectStatus = "planned"
    priority: Priority = "medium"
    start_date: date | None = None
    due_date: date | None = None
    objective_id: UUID | None = None
    person_ids: list[UUID] = Field(default_factory=list, max_length=50)


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    owning_role_id: UUID | None = None
    status: ProjectStatus | None = None
    priority: Priority | None = None
    start_date: date | None = None
    due_date: date | None = None
    objective_id: UUID | None = None
    person_ids: list[UUID] | None = Field(default=None, max_length=50)


class MilestoneCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    due_date: date | None = None


class MilestoneUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    due_date: date | None = None
    done: bool | None = None


class TaskCreate(BaseModel):
    title: str = Field(min_length=2, max_length=200)
    description: str = Field(default="", max_length=10000)
    assignee_id: UUID | None = None
    role_id: UUID | None = None
    project_id: UUID | None = None
    circle_id: UUID | None = None
    meeting_id: UUID | None = None
    due_date: date | None = None
    priority: Priority = "medium"
    status: TaskStatus = "todo"


class TaskUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    assignee_id: UUID | None = None
    role_id: UUID | None = None
    project_id: UUID | None = None
    circle_id: UUID | None = None
    due_date: date | None = None
    priority: Priority | None = None
    status: TaskStatus | None = None


class CommentBody(BaseModel):
    body: str = Field(min_length=1, max_length=4000)


async def _holds_role(db, ctx, role_id: UUID | None) -> bool:
    if role_id is None:
        return False
    row = await q1(db, "SELECT 1 AS ok FROM role_assignments WHERE role_id = :r AND user_id = :u AND deleted_at IS NULL", r=role_id, u=ctx.user_id)
    return row is not None


async def _project(db, ctx, project_id: UUID) -> dict:
    p = await q1(db, "SELECT * FROM projects WHERE id = :id AND organization_id = :o AND deleted_at IS NULL", id=project_id, o=ctx.org_id)
    if p is None:
        raise err(404, "PROJECT_NOT_FOUND", PROJECT_NOT_FOUND)
    return p


async def _can_manage_project(db, ctx, p: dict) -> bool:
    if ctx.level == "observer":
        return False
    if ctx.level == "org_admin" or p["created_by"] == ctx.user_id or await _holds_role(db, ctx, p["owning_role_id"]):
        return True
    member = await q1(db, "SELECT 1 AS ok FROM project_people WHERE project_id = :p AND user_id = :u", p=p["id"], u=ctx.user_id)
    return member is not None or await can_govern(db, ctx, p["circle_id"])


async def _check_role_in_org(db, ctx, role_id: UUID | None) -> None:
    if role_id is None:
        return
    row = await q1(db, "SELECT 1 AS ok FROM roles WHERE id = :r AND organization_id = :o AND deleted_at IS NULL", r=role_id, o=ctx.org_id)
    if row is None:
        raise err(404, "ROLE_NOT_FOUND", "Role not found.", "role_id")


async def _check_person(db, ctx, user_id: UUID | None) -> None:
    if user_id is None:
        return
    row = await q1(db, "SELECT 1 AS ok FROM memberships WHERE user_id = :u AND organization_id = :o AND active", u=user_id, o=ctx.org_id)
    if row is None:
        raise err(404, "PERSON_NOT_FOUND", "Person is not a member of this organization.", "assignee_id")


# -------------------------------------------------------------------- projects


@router.get("/projects", summary="List projects with progress")
async def list_projects(ctx: CtxDep, db: DbDep, circle_id: UUID | None = None, status: str | None = Query(default=None, max_length=20), mine: bool = False) -> list[dict]:
    where = ["p.organization_id = :o", "p.deleted_at IS NULL"]
    params: dict[str, Any] = {"o": ctx.org_id}
    if circle_id:
        where.append("p.circle_id = :c")
        params["c"] = circle_id
    if status == "open":
        where.append("p.status IN ('planned','active','on_hold')")
    elif status:
        where.append("p.status = :st")
        params["st"] = status
    if mine:
        where.append("(p.id IN (SELECT project_id FROM project_people WHERE user_id = :u) OR p.owning_role_id IN (SELECT role_id FROM role_assignments WHERE user_id = :u AND deleted_at IS NULL))")
        params["u"] = ctx.user_id
    return await q(
        db,
        f"""SELECT p.id, p.name, p.description, p.status, p.priority, p.start_date, p.due_date, p.circle_id, c.name AS circle_name,
                   p.owning_role_id, r.name AS owning_role_name, p.objective_id,
                   (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.deleted_at IS NULL) AS task_count,
                   (SELECT COUNT(*) FROM tasks t WHERE t.project_id = p.id AND t.deleted_at IS NULL AND t.status = 'done') AS tasks_done,
                   (SELECT COUNT(*) FROM project_milestones m WHERE m.project_id = p.id) AS milestone_count,
                   (SELECT COUNT(*) FROM project_milestones m WHERE m.project_id = p.id AND m.done) AS milestones_done,
                   COALESCE((SELECT json_agg(json_build_object('user_id', u.id, 'name', u.display_name)) FROM project_people pp JOIN users u ON u.id = pp.user_id WHERE pp.project_id = p.id), '[]'::json) AS people
            FROM projects p JOIN circles c ON c.id = p.circle_id LEFT JOIN roles r ON r.id = p.owning_role_id
            WHERE {' AND '.join(where)} ORDER BY (p.status IN ('done','cancelled')), p.due_date NULLS LAST, p.name""",  # noqa: S608 - constants only
        **params,
    )


async def _set_people(db, ctx, project_id: UUID, ids: list[UUID]) -> None:
    await x(db, "DELETE FROM project_people WHERE project_id = :p", p=project_id)
    for uid in set(ids):
        await _check_person(db, ctx, uid)
        await x(db, "INSERT INTO project_people (organization_id, project_id, user_id) VALUES (:o, :p, :u)", o=ctx.org_id, p=project_id, u=uid)


@router.post("/projects", summary="Create a project owned by a role")
async def create_project(body: ProjectCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    await require_circle(db, ctx, body.circle_id)
    await _check_role_in_org(db, ctx, body.owning_role_id)
    row = await q1(
        db,
        """INSERT INTO projects (organization_id, circle_id, owning_role_id, name, description, status, priority, start_date, due_date, objective_id, created_by, updated_by)
           VALUES (:o, :c, :r, :n, :d, :s, :p, :sd, :dd, :obj, :u, :u) RETURNING id""",
        o=ctx.org_id, c=body.circle_id, r=body.owning_role_id, n=body.name, d=body.description, s=body.status, p=body.priority,
        sd=body.start_date, dd=body.due_date, obj=body.objective_id, u=ctx.user_id,
    )
    await _set_people(db, ctx, row["id"], body.person_ids)
    await audit(db, ctx, "project.created", "project", row["id"], body.name)
    await db.commit()
    return {"id": row["id"]}


@router.get("/projects/{project_id}", summary="Project detail", responses={404: {"description": PROJECT_NOT_FOUND}})
async def project_detail(project_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    p = await _project(db, ctx, project_id)
    base = (await list_projects(ctx, db, circle_id=None, status=None, mine=False))
    summary = next((b for b in base if b["id"] == project_id), {})
    tasks = await q(
        db,
        """SELECT t.id, t.title, t.status, t.priority, t.due_date, t.assignee_id, u.display_name AS assignee_name,
                  (t.due_date < CURRENT_DATE AND t.status <> 'done') AS is_overdue
           FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id
           WHERE t.project_id = :p AND t.deleted_at IS NULL ORDER BY t.position, t.created_at""",
        p=project_id,
    )
    milestones = await q(db, "SELECT id, title, due_date, done FROM project_milestones WHERE project_id = :p ORDER BY due_date NULLS LAST, created_at", p=project_id)
    docs = await q(db, "SELECT id, name, url FROM attachments WHERE entity_type = 'project' AND entity_id = :p AND deleted_at IS NULL", p=project_id)
    objective = await q1(db, "SELECT id, title FROM objectives WHERE id = :i", i=p["objective_id"]) if p["objective_id"] else None
    return {**summary, "tasks": tasks, "milestones": milestones, "documents": docs, "objective": objective, "can_manage": await _can_manage_project(db, ctx, p)}


@router.patch("/projects/{project_id}", summary="Update a project", responses={403: {"description": "Not allowed to manage this project"}})
async def update_project(project_id: UUID, body: ProjectUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    p = await _project(db, ctx, project_id)
    if not await _can_manage_project(db, ctx, p):
        raise err(403, "PROJECT_FORBIDDEN", "Only the owning role, project team or governance roles can change this project.")
    data = body.model_dump(exclude_unset=True)
    people = data.pop("person_ids", None)
    if "owning_role_id" in data:
        await _check_role_in_org(db, ctx, data["owning_role_id"])
    sets, params = set_clause(data, {"name", "description", "owning_role_id", "status", "priority", "start_date", "due_date", "objective_id"})
    if sets:
        await x(db, f"UPDATE projects SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=project_id, u=ctx.user_id, **params)  # noqa: S608
    if people is not None:
        await _set_people(db, ctx, project_id, people)
    await audit(db, ctx, "project.updated", "project", project_id, p["name"])
    await db.commit()
    return {"ok": True}


@router.delete("/projects/{project_id}", summary="Delete a project (soft)")
async def delete_project(project_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    p = await _project(db, ctx, project_id)
    if not await _can_manage_project(db, ctx, p):
        raise err(403, "PROJECT_FORBIDDEN", "Only the owning role, project team or governance roles can delete this project.")
    await x(db, "UPDATE projects SET deleted_at = NOW(), updated_by = :u WHERE id = :id", id=project_id, u=ctx.user_id)
    await audit(db, ctx, "project.deleted", "project", project_id, p["name"])
    await db.commit()
    return {"ok": True}


@router.post("/projects/{project_id}/milestones", summary="Add a milestone")
async def add_milestone(project_id: UUID, body: MilestoneCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    p = await _project(db, ctx, project_id)
    if not await _can_manage_project(db, ctx, p):
        raise err(403, "PROJECT_FORBIDDEN", "You cannot change this project.")
    row = await q1(db, "INSERT INTO project_milestones (organization_id, project_id, title, due_date) VALUES (:o, :p, :t, :d) RETURNING id", o=ctx.org_id, p=project_id, t=body.title, d=body.due_date)
    await db.commit()
    return {"id": row["id"]}


@router.patch("/milestones/{milestone_id}", summary="Update a milestone")
async def update_milestone(milestone_id: UUID, body: MilestoneUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    m = await q1(db, "SELECT project_id FROM project_milestones WHERE id = :id AND organization_id = :o", id=milestone_id, o=ctx.org_id)
    if m is None:
        raise err(404, "MILESTONE_NOT_FOUND", "Milestone not found.")
    p = await _project(db, ctx, m["project_id"])
    if not await _can_manage_project(db, ctx, p):
        raise err(403, "PROJECT_FORBIDDEN", "You cannot change this project.")
    sets, params = set_clause(body.model_dump(exclude_unset=True), {"title", "due_date", "done"})
    if sets:
        await x(db, f"UPDATE project_milestones SET {sets} WHERE id = :id", id=milestone_id, **params)  # noqa: S608
    await db.commit()
    return {"ok": True}


@router.delete("/milestones/{milestone_id}", summary="Delete a milestone")
async def delete_milestone(milestone_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    m = await q1(db, "SELECT project_id FROM project_milestones WHERE id = :id AND organization_id = :o", id=milestone_id, o=ctx.org_id)
    if m is None:
        raise err(404, "MILESTONE_NOT_FOUND", "Milestone not found.")
    p = await _project(db, ctx, m["project_id"])
    if not await _can_manage_project(db, ctx, p):
        raise err(403, "PROJECT_FORBIDDEN", "You cannot change this project.")
    await x(db, "DELETE FROM project_milestones WHERE id = :id", id=milestone_id)
    await db.commit()
    return {"ok": True}


# ----------------------------------------------------------------------- tasks

TASK_SELECT = """SELECT t.id, t.title, t.description, t.status, t.priority, t.due_date, t.position, t.created_at, t.completed_at,
       t.assignee_id, u.display_name AS assignee_name, t.role_id, r.name AS role_name,
       t.project_id, p.name AS project_name, COALESCE(t.circle_id, p.circle_id) AS circle_id, c.name AS circle_name,
       t.tension_id, t.meeting_id, (t.due_date < CURRENT_DATE AND t.status <> 'done') AS is_overdue
       FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id LEFT JOIN roles r ON r.id = t.role_id
       LEFT JOIN projects p ON p.id = t.project_id LEFT JOIN circles c ON c.id = COALESCE(t.circle_id, p.circle_id)"""


@router.get("/tasks", summary="List tasks with filters")
async def list_tasks(
    ctx: CtxDep,
    db: DbDep,
    scope: Literal["mine", "all"] = "all",
    circle_id: UUID | None = None,
    project_id: UUID | None = None,
    role_id: UUID | None = None,
    assignee_id: UUID | None = None,
    status: TaskStatus | None = None,
    overdue: bool = False,
    search: str | None = Query(default=None, max_length=100),
    sort: Literal["due", "priority", "created"] = "due",
) -> list[dict]:
    where = ["t.organization_id = :o", "t.deleted_at IS NULL"]
    params: dict[str, Any] = {"o": ctx.org_id}
    if scope == "mine":
        where.append("t.assignee_id = :u")
        params["u"] = ctx.user_id
    if circle_id:
        where.append("COALESCE(t.circle_id, p.circle_id) = :c")
        params["c"] = circle_id
    if project_id:
        where.append("t.project_id = :p")
        params["p"] = project_id
    if role_id:
        where.append("t.role_id = :r")
        params["r"] = role_id
    if assignee_id:
        where.append("t.assignee_id = :a")
        params["a"] = assignee_id
    if status:
        where.append("t.status = :s")
        params["s"] = status
    if overdue:
        where.append("t.due_date < CURRENT_DATE AND t.status <> 'done'")
    if search:
        where.append("(t.title ILIKE :q OR t.description ILIKE :q)")
        params["q"] = f"%{search}%"
    order = {
        "due": "t.due_date NULLS LAST, t.created_at DESC",
        "priority": "CASE t.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, t.due_date NULLS LAST",
        "created": "t.created_at DESC",
    }[sort]
    return await q(db, f"{TASK_SELECT} WHERE {' AND '.join(where)} ORDER BY {order} LIMIT 500", **params)  # noqa: S608 - constants only


async def _task(db, ctx, task_id: UUID) -> dict:
    t = await q1(db, "SELECT * FROM tasks WHERE id = :id AND organization_id = :o AND deleted_at IS NULL", id=task_id, o=ctx.org_id)
    if t is None:
        raise err(404, "TASK_NOT_FOUND", TASK_NOT_FOUND)
    return t


async def _can_edit_task(db, ctx, t: dict) -> bool:
    if ctx.level == "observer":
        return False
    if ctx.level == "org_admin" or ctx.user_id in (t["assignee_id"], t["created_by"]) or await _holds_role(db, ctx, t["role_id"]):
        return True
    if t["project_id"]:
        p = await q1(db, "SELECT * FROM projects WHERE id = :p", p=t["project_id"])
        if p and await _can_manage_project(db, ctx, p):
            return True
    return bool(t["circle_id"]) and await can_govern(db, ctx, t["circle_id"])


@router.post("/tasks", summary="Create a task")
async def create_task(body: TaskCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    circle_id = body.circle_id
    if body.project_id:
        p = await _project(db, ctx, body.project_id)
        circle_id = circle_id or p["circle_id"]
    if circle_id:
        await require_circle(db, ctx, circle_id)
    await _check_role_in_org(db, ctx, body.role_id)
    await _check_person(db, ctx, body.assignee_id)
    row = await q1(
        db,
        """INSERT INTO tasks (organization_id, project_id, circle_id, role_id, assignee_id, meeting_id, title, description, status, priority, due_date,
                              completed_at, created_by, updated_by)
           VALUES (:o, :p, :c, :r, :a, :m, :t, :d, :s, :pr, :due, CASE WHEN CAST(:s AS varchar) = 'done' THEN NOW() ELSE NULL END, :u, :u) RETURNING id""",
        o=ctx.org_id, p=body.project_id, c=circle_id, r=body.role_id, a=body.assignee_id, m=body.meeting_id, t=body.title, d=body.description,
        s=body.status, pr=body.priority, due=body.due_date, u=ctx.user_id,
    )
    await x(db, "INSERT INTO task_activity (organization_id, task_id, actor_id, action, detail) VALUES (:o, :t, :u, 'created', :d)", o=ctx.org_id, t=row["id"], u=ctx.user_id, d=body.title)
    if body.assignee_id:
        await notify(db, ctx.org_id, [body.assignee_id], "task", f"New task: {body.title}", "", f"/work?task={row['id']}", exclude=ctx.user_id)
    await db.commit()
    return {"id": row["id"]}


@router.get("/tasks/{task_id}", summary="Task detail with comments and activity", responses={404: {"description": TASK_NOT_FOUND}})
async def task_detail(task_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    t = await _task(db, ctx, task_id)
    row = await q1(db, f"{TASK_SELECT} WHERE t.id = :id", id=task_id)  # noqa: S608
    comments = await q(db, "SELECT tc.id, tc.body, tc.created_at, u.display_name AS author_name, tc.author_id FROM task_comments tc JOIN users u ON u.id = tc.author_id WHERE tc.task_id = :t ORDER BY tc.created_at", t=task_id)
    activity = await q(db, "SELECT ta.id, ta.action, ta.detail, ta.created_at, u.display_name AS actor_name FROM task_activity ta LEFT JOIN users u ON u.id = ta.actor_id WHERE ta.task_id = :t ORDER BY ta.created_at DESC LIMIT 50", t=task_id)
    docs = await q(db, "SELECT id, name, url FROM attachments WHERE entity_type = 'task' AND entity_id = :t AND deleted_at IS NULL", t=task_id)
    return {**(row or {}), "comments": comments, "activity": activity, "attachments": docs, "can_edit": await _can_edit_task(db, ctx, t)}


@router.patch("/tasks/{task_id}", summary="Update a task (including drag-and-drop status changes)", responses={403: {"description": "Not allowed to edit this task"}})
async def update_task(task_id: UUID, body: TaskUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    t = await _task(db, ctx, task_id)
    if not await _can_edit_task(db, ctx, t):
        raise err(403, "TASK_FORBIDDEN", "Only the assignee, the accountable role, the project team or governance roles can change this task.")
    data = body.model_dump(exclude_unset=True)
    if "role_id" in data:
        await _check_role_in_org(db, ctx, data["role_id"])
    if "assignee_id" in data:
        await _check_person(db, ctx, data["assignee_id"])
    if "project_id" in data and data["project_id"]:
        await _project(db, ctx, data["project_id"])
    sets, params = set_clause(data, {"title", "description", "assignee_id", "role_id", "project_id", "circle_id", "due_date", "priority", "status"})
    if sets:
        extra = ""
        if "status" in data:
            extra = ", completed_at = NOW()" if data["status"] == "done" else ", completed_at = NULL"
        await x(db, f"UPDATE tasks SET {sets}{extra}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=task_id, u=ctx.user_id, **params)  # noqa: S608
        for k, v in params.items():
            if t[k] != v:
                await x(db, "INSERT INTO task_activity (organization_id, task_id, actor_id, action, detail) VALUES (:o, :t, :u, :a, :d)", o=ctx.org_id, t=task_id, u=ctx.user_id, a=f"{k}_changed", d=f"{t[k]} → {v}"[:300])
        if data.get("assignee_id") and data["assignee_id"] != t["assignee_id"]:
            await notify(db, ctx.org_id, [data["assignee_id"]], "task", f"Task assigned: {t['title']}", "", f"/work?task={task_id}", exclude=ctx.user_id)
    await db.commit()
    return {"ok": True}


@router.delete("/tasks/{task_id}", summary="Delete a task (soft)")
async def delete_task(task_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    t = await _task(db, ctx, task_id)
    if not await _can_edit_task(db, ctx, t):
        raise err(403, "TASK_FORBIDDEN", "You cannot delete this task.")
    await x(db, "UPDATE tasks SET deleted_at = NOW(), updated_by = :u WHERE id = :id", id=task_id, u=ctx.user_id)
    await db.commit()
    return {"ok": True}


@router.post("/tasks/{task_id}/comments", summary="Comment on a task")
async def comment_task(task_id: UUID, body: CommentBody, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    t = await _task(db, ctx, task_id)
    row = await q1(db, "INSERT INTO task_comments (organization_id, task_id, author_id, body) VALUES (:o, :t, :u, :b) RETURNING id", o=ctx.org_id, t=task_id, u=ctx.user_id, b=body.body.strip())
    await x(db, "INSERT INTO task_activity (organization_id, task_id, actor_id, action, detail) VALUES (:o, :t, :u, 'commented', :d)", o=ctx.org_id, t=task_id, u=ctx.user_id, d=body.body[:200])
    await notify(db, ctx.org_id, [uid for uid in (t["assignee_id"], t["created_by"]) if uid], "task", f"New comment on {t['title']}", body.body[:200], f"/work?task={task_id}", exclude=ctx.user_id)
    await db.commit()
    return {"id": row["id"]}
