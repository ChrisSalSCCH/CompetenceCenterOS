"""Capacity planning: explicit weekly capacity per person and planned allocations to projects or opportunities.

An allocation to an opportunity is hypothetical and is reported separately; it is never counted as certain.
A person without a capacity entry has no utilization figure - no capacity is ever assumed.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from routes.portfolio import _can_edit as _can_edit_project
from routes.work import _project
from services.commercial_db import can_edit_opp, check_member, get_opp
from services.ctx import CtxDep, require_write
from services.dbx import DbDep, err, q, q1, x
from services.events import audit
from services.management import capacity_for, utilization, weekly_load, weeks_ahead

router = APIRouter(prefix="/api/management", tags=["capacity"])

OVERLOAD_PCT = 100.0


class CapacityBody(BaseModel):
    user_id: UUID
    weekly_hours: Decimal = Field(ge=0, le=80)
    valid_from: date | None = None
    note: str | None = Field(default=None, max_length=300)


class AllocationBody(BaseModel):
    user_id: UUID
    project_id: UUID | None = None
    opportunity_id: UUID | None = None
    start_date: date
    end_date: date
    hours_per_week: Decimal = Field(gt=0, le=80)
    note: str | None = Field(default=None, max_length=300)


async def capacity_overview(db, ctx, weeks: int, start: date | None = None) -> dict[str, Any]:
    first = start or date.today()
    week_list = weeks_ahead(first, weeks)
    last_day = week_list[-1] + timedelta(days=6)
    people = await q(
        db,
        """SELECT u.id AS user_id, u.display_name AS name, m.job_title FROM memberships m JOIN users u ON u.id = m.user_id
           WHERE m.organization_id = :o AND m.active ORDER BY u.display_name""",
        o=ctx.org_id,
    )
    caps = await q(db, "SELECT user_id, weekly_hours, valid_from, valid_to FROM person_capacity WHERE organization_id = :o", o=ctx.org_id)
    allocs = await q(
        db,
        """SELECT a.id, a.user_id, a.project_id, a.opportunity_id, a.start_date, a.end_date, a.hours_per_week, a.note, p.name AS project_name, o.title AS opportunity_title
           FROM project_allocations a LEFT JOIN projects p ON p.id = a.project_id AND p.deleted_at IS NULL LEFT JOIN opportunities o ON o.id = a.opportunity_id AND o.deleted_at IS NULL
           WHERE a.organization_id = :o AND a.deleted_at IS NULL AND a.start_date <= :hi AND a.end_date >= :lo""",
        o=ctx.org_id, lo=week_list[0], hi=last_day,
    )
    rows = []
    overloaded = 0
    utils: list[float] = []
    for person in people:
        mine = [c for c in caps if c["user_id"] == person["user_id"]]
        planned = [a for a in allocs if a["user_id"] == person["user_id"] and a["project_id"] is not None]
        hypo = [a for a in allocs if a["user_id"] == person["user_id"] and a["opportunity_id"] is not None]
        cells = []
        for w in week_list:
            cap = capacity_for(mine, w)
            load = weekly_load(planned, w)
            maybe = weekly_load(hypo, w)
            pct = utilization(load, cap)
            with_hypo = utilization(load + maybe, cap)
            cells.append({"week": w, "capacity": cap, "planned": load, "hypothetical": maybe, "utilization": pct, "utilization_with_hypothetical": with_hypo, "overloaded": pct is not None and pct > OVERLOAD_PCT})
            if pct is not None:
                utils.append(pct)
        if any(c["overloaded"] for c in cells):
            overloaded += 1
        rows.append({**person, "has_capacity": bool(mine), "weeks": cells, "allocations": [a for a in allocs if a["user_id"] == person["user_id"]]})
    return {
        "weeks": week_list, "people": rows, "overloaded_people": overloaded, "people_without_capacity": sum(1 for p in rows if not p["has_capacity"]),
        "average_utilization": round(sum(utils) / len(utils), 1) if utils else None,
        "notes": ["Utilization is only shown for people with an explicit capacity entry.", "Allocations to opportunities are hypothetical and reported separately.", "A part-week counts pro rata by working days (Monday to Friday)."],
    }


@router.get("/capacity", summary="Capacity and planned load per person and week")
async def capacity(ctx: CtxDep, db: DbDep, weeks: int = Query(default=12, ge=1, le=52)) -> dict:
    return await capacity_overview(db, ctx, weeks)


@router.post("/capacity", summary="Set the weekly capacity of a person from a date on", responses={403: {"description": "Only administrators or the person herself"}})
async def set_capacity(body: CapacityBody, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    if ctx.level != "org_admin" and body.user_id != ctx.user_id:
        raise err(403, "CAPACITY_FORBIDDEN", "Only administrators or the person herself can set the capacity.")
    await check_member(db, ctx, body.user_id, "user_id")
    start = body.valid_from or date.today()
    # The previous entry ends the day before the new one starts, so entries never overlap.
    await x(
        db,
        "UPDATE person_capacity SET valid_to = :d, updated_at = NOW(), updated_by = :u WHERE organization_id = :o AND user_id = :p AND valid_to IS NULL AND valid_from < :s",
        d=start - timedelta(days=1), u=ctx.user_id, o=ctx.org_id, p=body.user_id, s=start,
    )
    same_day = await q(
        db,
        "UPDATE person_capacity SET weekly_hours = :h, note = :n, valid_to = NULL, updated_at = NOW(), updated_by = :u WHERE organization_id = :o AND user_id = :p AND valid_from = :s RETURNING id",
        o=ctx.org_id, p=body.user_id, h=body.weekly_hours, s=start, n=body.note, u=ctx.user_id,
    )
    if not same_day:
        await x(
            db,
            "INSERT INTO person_capacity (organization_id, user_id, weekly_hours, valid_from, note, created_by, updated_by) VALUES (:o, :p, :h, :s, :n, :u, :u)",
            o=ctx.org_id, p=body.user_id, h=body.weekly_hours, s=start, n=body.note, u=ctx.user_id,
        )
    await audit(db, ctx, "capacity.set", "person", body.user_id, f"{body.weekly_hours} h/week from {start}")
    await db.commit()
    return {"ok": True}


async def _check_target(db, ctx, body: AllocationBody) -> None:
    if (body.project_id is None) == (body.opportunity_id is None):
        raise err(422, "ALLOCATION_TARGET", "Choose either a project or an opportunity.", "project_id")
    if body.end_date < body.start_date:
        raise err(422, "INVALID_DATES", "The end date cannot be before the start date.", "end_date")
    if body.project_id:
        project = await _project(db, ctx, body.project_id)
        if not await _can_edit_project(db, ctx, project):
            raise err(403, "PROJECT_FORBIDDEN", "Only administrators, the project manager or the project team can plan capacity for this project.")
    elif body.opportunity_id:
        opp = await get_opp(db, ctx, body.opportunity_id)
        if not await can_edit_opp(db, ctx, opp):
            raise err(403, "OPPORTUNITY_FORBIDDEN", "Only administrators, the owner or the opportunity team can plan capacity for this opportunity.")


@router.post("/allocations", summary="Plan a person on a project (planned) or an opportunity (hypothetical)", responses={403: {"description": "Not allowed"}, 422: {"description": "Invalid target or dates"}})
async def create_allocation(body: AllocationBody, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    await _check_target(db, ctx, body)
    await check_member(db, ctx, body.user_id, "user_id")
    row = await q1(
        db,
        """INSERT INTO project_allocations (organization_id, user_id, project_id, opportunity_id, start_date, end_date, hours_per_week, note, created_by, updated_by)
           VALUES (:o, :us, :p, :op, :s, :e, :h, :n, :u, :u) RETURNING id""",
        o=ctx.org_id, us=body.user_id, p=body.project_id, op=body.opportunity_id, s=body.start_date, e=body.end_date, h=body.hours_per_week, n=body.note, u=ctx.user_id,
    )
    await audit(db, ctx, "allocation.created", "project" if body.project_id else "opportunity", body.project_id or body.opportunity_id, f"{body.hours_per_week} h/week")
    await db.commit()
    return {"id": row["id"]}


@router.delete("/allocations/{allocation_id}", summary="Remove a planned allocation (soft)", responses={404: {"description": "Allocation not found"}})
async def delete_allocation(allocation_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    a = await q1(db, "SELECT * FROM project_allocations WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=allocation_id, o=ctx.org_id)
    if a is None:
        raise err(404, "ALLOCATION_NOT_FOUND", "Allocation not found.")
    body = AllocationBody(user_id=a["user_id"], project_id=a["project_id"], opportunity_id=a["opportunity_id"], start_date=a["start_date"], end_date=a["end_date"], hours_per_week=a["hours_per_week"])
    await _check_target(db, ctx, body)
    await x(db, "UPDATE project_allocations SET deleted_at = NOW(), updated_by = :u WHERE id = :i", i=allocation_id, u=ctx.user_id)
    await db.commit()
    return {"ok": True}
