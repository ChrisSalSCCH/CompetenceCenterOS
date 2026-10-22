"""Goals & metrics: objectives (with roll-up), key results, KPIs and readings."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Any, Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from services.ctx import CtxDep, can_govern, require_circle, require_write
from services.dbx import DbDep, err, q, q1, set_clause, x
from services.events import audit

router = APIRouter(prefix="/api", tags=["goals"])

Num = Annotated[Decimal, Field(ge=-1_000_000_000, le=1_000_000_000)]


class ObjectiveCreate(BaseModel):
    circle_id: UUID
    role_id: UUID | None = None
    parent_id: UUID | None = None
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=5000)
    period: str = Field(default="", max_length=30)


class ObjectiveUpdate(BaseModel):
    role_id: UUID | None = None
    parent_id: UUID | None = None
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    period: str | None = Field(default=None, max_length=30)


class KeyResultCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    unit: str = Field(default="", max_length=20)
    start_value: Num = Decimal(0)
    target_value: Num
    current_value: Num = Decimal(0)


class KeyResultUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    unit: str | None = Field(default=None, max_length=20)
    start_value: Num | None = None
    target_value: Num | None = None
    current_value: Num | None = None


class MetricCreate(BaseModel):
    circle_id: UUID
    role_id: UUID | None = None
    name: str = Field(min_length=2, max_length=160)
    unit: str = Field(default="", max_length=20)
    direction: Literal["up", "down"] = "up"
    target_value: Num
    current_value: Num = Decimal(0)
    period: Literal["weekly", "monthly", "quarterly", "yearly"] = "monthly"


class MetricUpdate(BaseModel):
    role_id: UUID | None = None
    name: str | None = Field(default=None, min_length=2, max_length=160)
    unit: str | None = Field(default=None, max_length=20)
    direction: Literal["up", "down"] | None = None
    target_value: Num | None = None
    period: Literal["weekly", "monthly", "quarterly", "yearly"] | None = None


class ReadingCreate(BaseModel):
    value: Num
    note: str | None = Field(default=None, max_length=300)


def kr_progress(start: Decimal, target: Decimal, current: Decimal) -> float:
    span = float(target - start)
    if span == 0:
        return 1.0 if current >= target else 0.0
    return max(0.0, min(1.0, float(current - start) / span))


def metric_progress(direction: str, target: Decimal, current: Decimal) -> float:
    if direction == "down":
        if current <= 0:
            return 1.0
        return max(0.0, min(1.0, float(target) / float(current))) if target > 0 else 0.0
    return max(0.0, min(1.0, float(current) / float(target))) if target > 0 else 0.0


def rollup(objectives: list[dict[str, Any]]) -> None:
    """Adds own_progress and progress (blending own key results with child objectives)."""
    by_id = {o["id"]: o for o in objectives}
    children: dict[Any, list[dict[str, Any]]] = {}
    for o in objectives:
        if o["parent_id"] in by_id:
            children.setdefault(o["parent_id"], []).append(o)

    def calc(o: dict[str, Any], depth: int = 0) -> float:
        if "progress" in o:
            return o["progress"]
        parts = [kr["progress"] for kr in o["key_results"]]
        own = sum(parts) / len(parts) if parts else None
        o["own_progress"] = own
        kids = [calc(c, depth + 1) for c in children.get(o["id"], []) if depth < 20]
        allparts = parts + kids
        o["progress"] = sum(allparts) / len(allparts) if allparts else 0.0
        return o["progress"]

    for o in objectives:
        calc(o)


@router.get("/goals", summary="Objectives with roll-up progress and KPIs")
async def goals(ctx: CtxDep, db: DbDep, circle_id: UUID | None = None) -> dict:
    extra = " AND o.circle_id = :c" if circle_id else ""
    params: dict[str, Any] = {"o": ctx.org_id}
    if circle_id:
        params["c"] = circle_id
    objectives = await q(
        db,
        f"""SELECT o.id, o.circle_id, c.name AS circle_name, o.role_id, r.name AS role_name, o.parent_id, o.title, o.description, o.period,
                   (SELECT COUNT(*) FROM projects p WHERE p.objective_id = o.id AND p.deleted_at IS NULL) AS project_count
            FROM objectives o JOIN circles c ON c.id = o.circle_id LEFT JOIN roles r ON r.id = o.role_id
            WHERE o.organization_id = :o AND o.deleted_at IS NULL{extra} ORDER BY c.name, o.created_at""",  # noqa: S608 - constants only
        **params,
    )
    if circle_id:
        # include ancestors (higher objectives) so contribution chains stay visible
        parents = await q(
            db,
            """WITH RECURSIVE up AS (
                   SELECT id, parent_id FROM objectives WHERE circle_id = :c AND organization_id = :o AND deleted_at IS NULL
                 UNION SELECT ob.id, ob.parent_id FROM objectives ob JOIN up ON ob.id = up.parent_id WHERE ob.deleted_at IS NULL
               ) SELECT ob.id, ob.circle_id, c.name AS circle_name, ob.role_id, NULL AS role_name, ob.parent_id, ob.title, ob.description, ob.period, 0 AS project_count
               FROM objectives ob JOIN circles c ON c.id = ob.circle_id WHERE ob.id IN (SELECT id FROM up)""",
            c=circle_id, o=ctx.org_id,
        )
        have = {o["id"] for o in objectives}
        objectives += [p for p in parents if p["id"] not in have]
    krs = await q(
        db,
        """SELECT id, objective_id, title, unit, start_value, target_value, current_value FROM key_results
           WHERE organization_id = :o AND deleted_at IS NULL ORDER BY created_at""",
        o=ctx.org_id,
    )
    for ob in objectives:
        ob["key_results"] = []
    omap = {o["id"]: o for o in objectives}
    for kr in krs:
        if kr["objective_id"] in omap:
            kr["progress"] = kr_progress(kr["start_value"], kr["target_value"], kr["current_value"])
            omap[kr["objective_id"]]["key_results"].append(kr)
    rollup(objectives)
    mextra = " AND m.circle_id = :c" if circle_id else ""
    metrics = await q(
        db,
        f"""SELECT m.id, m.circle_id, c.name AS circle_name, m.role_id, r.name AS role_name, m.name, m.unit, m.direction, m.target_value, m.current_value, m.period
            FROM metrics m JOIN circles c ON c.id = m.circle_id LEFT JOIN roles r ON r.id = m.role_id
            WHERE m.organization_id = :o AND m.deleted_at IS NULL{mextra} ORDER BY c.name, m.name""",  # noqa: S608 - constants only
        **params,
    )
    readings = await q(
        db,
        """SELECT metric_id, value, recorded_at FROM metric_readings WHERE organization_id = :o ORDER BY recorded_at""",
        o=ctx.org_id,
    )
    series: dict[Any, list[dict[str, Any]]] = {}
    for rd in readings:
        series.setdefault(rd["metric_id"], []).append({"value": rd["value"], "recorded_at": rd["recorded_at"]})
    for m in metrics:
        m["progress"] = metric_progress(m["direction"], m["target_value"], m["current_value"])
        m["readings"] = series.get(m["id"], [])[-24:]
    return {"objectives": objectives, "metrics": metrics}


async def _can_edit_goals(db, ctx, circle_id: UUID) -> bool:
    if ctx.level == "observer":
        return False
    if await can_govern(db, ctx, circle_id):
        return True
    row = await q1(
        db,
        """SELECT 1 AS ok FROM role_assignments ra JOIN roles r ON r.id = ra.role_id AND r.deleted_at IS NULL
           WHERE ra.user_id = :u AND ra.deleted_at IS NULL AND r.circle_id = :c LIMIT 1""",
        u=ctx.user_id, c=circle_id,
    )
    return row is not None


async def _require_goal_edit(db, ctx, circle_id: UUID) -> None:
    require_write(ctx)
    if not await _can_edit_goals(db, ctx, circle_id):
        raise err(403, "GOALS_FORBIDDEN", "Only members holding a role in this circle or governance roles can change its goals.")


@router.post("/objectives", summary="Create an objective for a circle or role")
async def create_objective(body: ObjectiveCreate, ctx: CtxDep, db: DbDep) -> dict:
    await require_circle(db, ctx, body.circle_id)
    await _require_goal_edit(db, ctx, body.circle_id)
    if body.parent_id:
        parent = await q1(db, "SELECT id FROM objectives WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=body.parent_id, o=ctx.org_id)
        if parent is None:
            raise err(404, "OBJECTIVE_NOT_FOUND", "Parent objective not found.", "parent_id")
    row = await q1(
        db,
        """INSERT INTO objectives (organization_id, circle_id, role_id, parent_id, title, description, period, created_by, updated_by)
           VALUES (:o, :c, :r, :p, :t, :d, :pe, :u, :u) RETURNING id""",
        o=ctx.org_id, c=body.circle_id, r=body.role_id, p=body.parent_id, t=body.title, d=body.description, pe=body.period, u=ctx.user_id,
    )
    await audit(db, ctx, "objective.created", "objective", row["id"], body.title)
    await db.commit()
    return {"id": row["id"]}


async def _objective(db, ctx, objective_id: UUID) -> dict:
    o = await q1(db, "SELECT * FROM objectives WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=objective_id, o=ctx.org_id)
    if o is None:
        raise err(404, "OBJECTIVE_NOT_FOUND", "Objective not found.")
    return o


@router.patch("/objectives/{objective_id}", summary="Update an objective", responses={409: {"description": "Cycle in objective hierarchy"}})
async def update_objective(objective_id: UUID, body: ObjectiveUpdate, ctx: CtxDep, db: DbDep) -> dict:
    o = await _objective(db, ctx, objective_id)
    await _require_goal_edit(db, ctx, o["circle_id"])
    data = body.model_dump(exclude_unset=True)
    if data.get("parent_id"):
        cur: UUID | None = data["parent_id"]
        for _ in range(50):
            if cur is None:
                break
            if cur == objective_id:
                raise err(409, "OBJECTIVE_CYCLE", "An objective cannot contribute to itself.", "parent_id")
            row = await q1(db, "SELECT parent_id FROM objectives WHERE id = :i AND organization_id = :o", i=cur, o=ctx.org_id)
            cur = row["parent_id"] if row else None
    sets, params = set_clause(data, {"role_id", "parent_id", "title", "description", "period"})
    if sets:
        await x(db, f"UPDATE objectives SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=objective_id, u=ctx.user_id, **params)  # noqa: S608
    await db.commit()
    return {"ok": True}


@router.delete("/objectives/{objective_id}", summary="Delete an objective (soft)")
async def delete_objective(objective_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    o = await _objective(db, ctx, objective_id)
    await _require_goal_edit(db, ctx, o["circle_id"])
    await x(db, "UPDATE objectives SET deleted_at = NOW(), updated_by = :u WHERE id = :id", id=objective_id, u=ctx.user_id)
    await x(db, "UPDATE objectives SET parent_id = NULL WHERE parent_id = :id", id=objective_id)
    await db.commit()
    return {"ok": True}


@router.post("/objectives/{objective_id}/key-results", summary="Add a key result")
async def create_kr(objective_id: UUID, body: KeyResultCreate, ctx: CtxDep, db: DbDep) -> dict:
    o = await _objective(db, ctx, objective_id)
    await _require_goal_edit(db, ctx, o["circle_id"])
    row = await q1(
        db,
        """INSERT INTO key_results (organization_id, objective_id, title, unit, start_value, target_value, current_value)
           VALUES (:o, :ob, :t, :un, :s, :tg, :c) RETURNING id""",
        o=ctx.org_id, ob=objective_id, t=body.title, un=body.unit, s=body.start_value, tg=body.target_value, c=body.current_value,
    )
    await db.commit()
    return {"id": row["id"]}


@router.patch("/key-results/{kr_id}", summary="Update a key result (e.g. check in a new value)")
async def update_kr(kr_id: UUID, body: KeyResultUpdate, ctx: CtxDep, db: DbDep) -> dict:
    kr = await q1(db, "SELECT k.id, o.circle_id FROM key_results k JOIN objectives o ON o.id = k.objective_id WHERE k.id = :i AND k.organization_id = :o AND k.deleted_at IS NULL", i=kr_id, o=ctx.org_id)
    if kr is None:
        raise err(404, "KEY_RESULT_NOT_FOUND", "Key result not found.")
    await _require_goal_edit(db, ctx, kr["circle_id"])
    sets, params = set_clause(body.model_dump(exclude_unset=True), {"title", "unit", "start_value", "target_value", "current_value"})
    if sets:
        await x(db, f"UPDATE key_results SET {sets}, updated_at = NOW() WHERE id = :id", id=kr_id, **params)  # noqa: S608
    await db.commit()
    return {"ok": True}


@router.delete("/key-results/{kr_id}", summary="Delete a key result")
async def delete_kr(kr_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    kr = await q1(db, "SELECT k.id, o.circle_id FROM key_results k JOIN objectives o ON o.id = k.objective_id WHERE k.id = :i AND k.organization_id = :o", i=kr_id, o=ctx.org_id)
    if kr is None:
        raise err(404, "KEY_RESULT_NOT_FOUND", "Key result not found.")
    await _require_goal_edit(db, ctx, kr["circle_id"])
    await x(db, "UPDATE key_results SET deleted_at = NOW() WHERE id = :id", id=kr_id)
    await db.commit()
    return {"ok": True}


@router.post("/metrics", summary="Create a KPI for a circle or role")
async def create_metric(body: MetricCreate, ctx: CtxDep, db: DbDep) -> dict:
    await require_circle(db, ctx, body.circle_id)
    await _require_goal_edit(db, ctx, body.circle_id)
    row = await q1(
        db,
        """INSERT INTO metrics (organization_id, circle_id, role_id, name, unit, direction, target_value, current_value, period, created_by, updated_by)
           VALUES (:o, :c, :r, :n, :un, :d, :t, :cv, :p, :u, :u) RETURNING id""",
        o=ctx.org_id, c=body.circle_id, r=body.role_id, n=body.name, un=body.unit, d=body.direction, t=body.target_value, cv=body.current_value, p=body.period, u=ctx.user_id,
    )
    await x(db, "INSERT INTO metric_readings (organization_id, metric_id, value, recorded_by) VALUES (:o, :m, :v, :u)", o=ctx.org_id, m=row["id"], v=body.current_value, u=ctx.user_id)
    await db.commit()
    return {"id": row["id"]}


async def _metric(db, ctx, metric_id: UUID) -> dict:
    m = await q1(db, "SELECT * FROM metrics WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=metric_id, o=ctx.org_id)
    if m is None:
        raise err(404, "METRIC_NOT_FOUND", "Metric not found.")
    return m


@router.patch("/metrics/{metric_id}", summary="Update a KPI definition")
async def update_metric(metric_id: UUID, body: MetricUpdate, ctx: CtxDep, db: DbDep) -> dict:
    m = await _metric(db, ctx, metric_id)
    await _require_goal_edit(db, ctx, m["circle_id"])
    sets, params = set_clause(body.model_dump(exclude_unset=True), {"role_id", "name", "unit", "direction", "target_value", "period"})
    if sets:
        await x(db, f"UPDATE metrics SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=metric_id, u=ctx.user_id, **params)  # noqa: S608
    await db.commit()
    return {"ok": True}


@router.delete("/metrics/{metric_id}", summary="Delete a KPI (soft)")
async def delete_metric(metric_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    m = await _metric(db, ctx, metric_id)
    await _require_goal_edit(db, ctx, m["circle_id"])
    await x(db, "UPDATE metrics SET deleted_at = NOW(), updated_by = :u WHERE id = :id", id=metric_id, u=ctx.user_id)
    await db.commit()
    return {"ok": True}


@router.post("/metrics/{metric_id}/readings", summary="Report a new KPI value")
async def add_reading(metric_id: UUID, body: ReadingCreate, ctx: CtxDep, db: DbDep) -> dict:
    m = await _metric(db, ctx, metric_id)
    await _require_goal_edit(db, ctx, m["circle_id"])
    await x(db, "INSERT INTO metric_readings (organization_id, metric_id, value, note, recorded_by) VALUES (:o, :m, :v, :n, :u)", o=ctx.org_id, m=metric_id, v=body.value, n=body.note, u=ctx.user_id)
    await x(db, "UPDATE metrics SET current_value = :v, updated_at = NOW(), updated_by = :u WHERE id = :id", v=body.value, u=ctx.user_id, id=metric_id)
    await db.commit()
    return {"ok": True}


@router.get("/circles/{circle_id}/dashboard", summary="Compact health dashboard of a circle")
async def circle_dashboard(circle_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    await require_circle(db, ctx, circle_id)
    stats = await q1(
        db,
        """SELECT
             (SELECT COUNT(*) FROM roles WHERE circle_id = :c AND deleted_at IS NULL) AS roles,
             (SELECT COUNT(*) FROM roles r WHERE r.circle_id = :c AND r.deleted_at IS NULL AND NOT EXISTS
                 (SELECT 1 FROM role_assignments ra WHERE ra.role_id = r.id AND ra.deleted_at IS NULL)) AS unfilled_roles,
             (SELECT COUNT(*) FROM tasks t LEFT JOIN projects p ON p.id = t.project_id WHERE t.deleted_at IS NULL AND t.status <> 'done'
                 AND COALESCE(t.circle_id, p.circle_id) = :c) AS open_tasks,
             (SELECT COUNT(*) FROM tasks t LEFT JOIN projects p ON p.id = t.project_id WHERE t.deleted_at IS NULL AND t.status <> 'done'
                 AND t.due_date < CURRENT_DATE AND COALESCE(t.circle_id, p.circle_id) = :c) AS overdue_tasks,
             (SELECT COUNT(*) FROM projects WHERE circle_id = :c AND deleted_at IS NULL AND status IN ('planned','active','on_hold')) AS active_projects,
             (SELECT COUNT(*) FROM tensions WHERE circle_id = :c AND deleted_at IS NULL AND status IN ('open','processing')) AS open_tensions,
             (SELECT COUNT(*) FROM governance_proposals WHERE circle_id = :c AND deleted_at IS NULL AND status NOT IN ('accepted','rejected','withdrawn')) AS open_proposals""",
        c=circle_id,
    )
    data = await goals(ctx, db, circle_id)
    return {"stats": stats, **data}
