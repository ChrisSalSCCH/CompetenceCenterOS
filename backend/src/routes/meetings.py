"""Meetings: scheduling, agenda, guided facilitation, decisions."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field
from services.ctx import CtxDep, can_govern, require_circle, require_write
from services.dbx import DbDep, err, q, q1, set_clause, x
from services.events import audit, notify

router = APIRouter(prefix="/api", tags=["meetings"])

MeetingType = Literal["tactical", "governance", "general", "custom"]
MEETING_NOT_FOUND = "Meeting not found."

TEMPLATES: dict[str, list[tuple[str, str]]] = {
    "tactical": [
        ("checkin", "Check-in round"),
        ("checklist", "Checklist review"),
        ("metrics", "Metrics review"),
        ("projects", "Project updates"),
        ("tension", "Tension processing"),
        ("closing", "Closing round"),
    ],
    "governance": [("checkin", "Check-in round"), ("custom", "Proposals"), ("closing", "Closing round")],
    "general": [("checkin", "Check-in round"), ("custom", "Topics"), ("closing", "Closing round")],
    "custom": [],
}


class MeetingCreate(BaseModel):
    circle_id: UUID
    title: str = Field(min_length=3, max_length=200)
    meeting_type: MeetingType = "tactical"
    scheduled_at: datetime
    duration_min: int = Field(default=60, ge=5, le=600)
    facilitator_id: UUID | None = None
    participant_ids: list[UUID] | None = Field(default=None, max_length=100)
    tension_ids: list[UUID] = Field(default_factory=list, max_length=50)


class MeetingUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    scheduled_at: datetime | None = None
    duration_min: int | None = Field(default=None, ge=5, le=600)
    facilitator_id: UUID | None = None
    notes: str | None = Field(default=None, max_length=20000)
    checkin_notes: str | None = Field(default=None, max_length=20000)
    status: Literal["scheduled", "cancelled"] | None = None


class StepBody(BaseModel):
    step: int = Field(ge=0, le=200)


class ParticipantsBody(BaseModel):
    user_ids: list[UUID] = Field(max_length=100)


class AttendanceBody(BaseModel):
    user_id: UUID
    attended: bool


class AgendaCreate(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    kind: Literal["checklist", "metrics", "projects", "tension", "custom"] = "custom"
    tension_id: UUID | None = None
    project_id: UUID | None = None


class AgendaUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    notes: str | None = Field(default=None, max_length=10000)
    outcome: str | None = Field(default=None, max_length=10000)
    status: Literal["pending", "done"] | None = None


class DecisionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    rationale: str = Field(default="", max_length=4000)


async def _meeting(db, ctx, meeting_id: UUID) -> dict:
    m = await q1(db, "SELECT * FROM meetings WHERE id = :id AND organization_id = :o AND deleted_at IS NULL", id=meeting_id, o=ctx.org_id)
    if m is None:
        raise err(404, "MEETING_NOT_FOUND", MEETING_NOT_FOUND)
    return m


async def _can_run(db, ctx, m: dict) -> bool:
    return m["facilitator_id"] == ctx.user_id or ctx.level == "org_admin" or await can_govern(db, ctx, m["circle_id"])


async def _renumber(db, meeting_id: UUID) -> None:
    rows = await q(db, "SELECT id FROM agenda_items WHERE meeting_id = :m ORDER BY position, created_at", m=meeting_id)
    for i, r in enumerate(rows):
        await x(db, "UPDATE agenda_items SET position = :p WHERE id = :id", p=i, id=r["id"])


@router.get("/meetings", summary="List meetings")
async def list_meetings(ctx: CtxDep, db: DbDep, circle_id: UUID | None = None, scope: Literal["all", "upcoming", "past", "mine"] = "all") -> list[dict]:
    where = ["m.organization_id = :o", "m.deleted_at IS NULL"]
    params: dict[str, Any] = {"o": ctx.org_id}
    if circle_id:
        where.append("m.circle_id = :c")
        params["c"] = circle_id
    if scope == "upcoming":
        where.append("m.status IN ('scheduled','in_progress')")
    elif scope == "past":
        where.append("m.status IN ('completed','cancelled')")
    elif scope == "mine":
        where.append("m.id IN (SELECT meeting_id FROM meeting_participants WHERE user_id = :u)")
        params["u"] = ctx.user_id
    return await q(
        db,
        f"""SELECT m.id, m.title, m.meeting_type, m.scheduled_at, m.duration_min, m.status, m.circle_id, c.name AS circle_name,
                   m.facilitator_id, f.display_name AS facilitator_name,
                   (SELECT COUNT(*) FROM meeting_participants mp WHERE mp.meeting_id = m.id) AS participant_count
            FROM meetings m JOIN circles c ON c.id = m.circle_id LEFT JOIN users f ON f.id = m.facilitator_id
            WHERE {' AND '.join(where)} ORDER BY m.scheduled_at DESC LIMIT 200""",  # noqa: S608 - constants only
        **params,
    )


@router.post("/meetings", summary="Schedule a meeting from a template")
async def create_meeting(body: MeetingCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    await require_circle(db, ctx, body.circle_id)
    row = await q1(
        db,
        """INSERT INTO meetings (organization_id, circle_id, title, meeting_type, scheduled_at, duration_min, facilitator_id, created_by, updated_by)
           VALUES (:o, :c, :t, :mt, :s, :d, :f, :u, :u) RETURNING id""",
        o=ctx.org_id, c=body.circle_id, t=body.title, mt=body.meeting_type, s=body.scheduled_at, d=body.duration_min,
        f=body.facilitator_id or ctx.user_id, u=ctx.user_id,
    )
    mid = row["id"]
    participants = body.participant_ids
    if participants is None:
        holders = await q(
            db,
            """SELECT DISTINCT ra.user_id FROM role_assignments ra JOIN roles r ON r.id = ra.role_id AND r.deleted_at IS NULL
               WHERE r.circle_id = :c AND ra.organization_id = :o AND ra.deleted_at IS NULL""",
            c=body.circle_id, o=ctx.org_id,
        )
        participants = [h["user_id"] for h in holders]
    participants = list({*participants, ctx.user_id})
    for uid in participants:
        await x(db, "INSERT INTO meeting_participants (organization_id, meeting_id, user_id) VALUES (:o, :m, :u) ON CONFLICT DO NOTHING", o=ctx.org_id, m=mid, u=uid)
    pos = 0
    tension_inserted = False
    for kind, title in TEMPLATES[body.meeting_type]:
        if kind == "tension" and body.tension_ids:
            for tid in body.tension_ids:
                t = await q1(db, "SELECT title FROM tensions WHERE id = :t AND organization_id = :o AND deleted_at IS NULL", t=tid, o=ctx.org_id)
                if t:
                    await x(db, "INSERT INTO agenda_items (organization_id, meeting_id, position, title, kind, tension_id) VALUES (:o, :m, :p, :t, 'tension', :tid)", o=ctx.org_id, m=mid, p=pos, t=t["title"], tid=tid)
                    pos += 1
            tension_inserted = True
            continue
        await x(db, "INSERT INTO agenda_items (organization_id, meeting_id, position, title, kind) VALUES (:o, :m, :p, :t, :k)", o=ctx.org_id, m=mid, p=pos, t=title, k=kind)
        pos += 1
    if body.tension_ids and not tension_inserted:
        for tid in body.tension_ids:
            t = await q1(db, "SELECT title FROM tensions WHERE id = :t AND organization_id = :o AND deleted_at IS NULL", t=tid, o=ctx.org_id)
            if t:
                await x(db, "INSERT INTO agenda_items (organization_id, meeting_id, position, title, kind, tension_id) VALUES (:o, :m, :p, :t, 'tension', :tid)", o=ctx.org_id, m=mid, p=pos, t=t["title"], tid=tid)
                pos += 1
    await notify(db, ctx.org_id, participants, "meeting", f"Invitation: {body.title}", body.scheduled_at.isoformat(), f"/meetings/{mid}", exclude=ctx.user_id)
    await audit(db, ctx, "meeting.created", "meeting", mid, body.title)
    await db.commit()
    return {"id": mid}


@router.get("/meetings/{meeting_id}", summary="Meeting detail with agenda, decisions and prepared context", responses={404: {"description": MEETING_NOT_FOUND}})
async def meeting_detail(meeting_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    m = await _meeting(db, ctx, meeting_id)
    circle = await q1(db, "SELECT id, name FROM circles WHERE id = :c", c=m["circle_id"])
    fac = await q1(db, "SELECT display_name FROM users WHERE id = :u", u=m["facilitator_id"]) if m["facilitator_id"] else None
    participants = await q(
        db,
        """SELECT mp.user_id, mp.attended, u.display_name AS name, ms.avatar_color FROM meeting_participants mp
           JOIN users u ON u.id = mp.user_id LEFT JOIN memberships ms ON ms.user_id = mp.user_id AND ms.organization_id = mp.organization_id
           WHERE mp.meeting_id = :m ORDER BY u.display_name""",
        m=meeting_id,
    )
    agenda = await q(
        db,
        """SELECT ai.id, ai.position, ai.title, ai.kind, ai.notes, ai.outcome, ai.status, ai.tension_id, ai.project_id,
                  t.title AS tension_title, t.description AS tension_description, t.status AS tension_status, t.priority AS tension_priority,
                  tu.display_name AS tension_creator, p.name AS project_name
           FROM agenda_items ai LEFT JOIN tensions t ON t.id = ai.tension_id LEFT JOIN users tu ON tu.id = t.creator_id
           LEFT JOIN projects p ON p.id = ai.project_id WHERE ai.meeting_id = :m ORDER BY ai.position""",
        m=meeting_id,
    )
    decisions = await q(
        db,
        """SELECT gd.id, gd.title, gd.rationale, gd.outcome, gd.created_at, u.display_name AS decided_by_name
           FROM governance_decisions gd LEFT JOIN users u ON u.id = gd.decided_by WHERE gd.meeting_id = :m ORDER BY gd.created_at""",
        m=meeting_id,
    )
    tasks = await q(
        db,
        """SELECT t.id, t.title, t.status, t.due_date, u.display_name AS assignee_name FROM tasks t LEFT JOIN users u ON u.id = t.assignee_id
           WHERE t.meeting_id = :m AND t.deleted_at IS NULL ORDER BY t.created_at""",
        m=meeting_id,
    )
    proposals = await q(db, "SELECT id, title, status FROM governance_proposals WHERE meeting_id = :m AND deleted_at IS NULL", m=meeting_id)
    metrics = await q(db, "SELECT id, name, unit, target_value, current_value, direction FROM metrics WHERE circle_id = :c AND organization_id = :o AND deleted_at IS NULL ORDER BY name", c=m["circle_id"], o=ctx.org_id)
    projects = await q(db, "SELECT id, name, status, due_date FROM projects WHERE circle_id = :c AND organization_id = :o AND deleted_at IS NULL AND status IN ('planned','active','on_hold') ORDER BY name", c=m["circle_id"], o=ctx.org_id)
    open_tensions = await q(
        db,
        """SELECT t.id, t.title, t.priority FROM tensions t WHERE t.circle_id = :c AND t.organization_id = :o AND t.deleted_at IS NULL
             AND t.status IN ('open','processing') AND t.id NOT IN (SELECT tension_id FROM agenda_items WHERE meeting_id = :m AND tension_id IS NOT NULL)
           ORDER BY t.created_at""",
        c=m["circle_id"], o=ctx.org_id, m=meeting_id,
    )
    return {
        **m,
        "circle_name": circle["name"] if circle else None,
        "facilitator_name": fac["display_name"] if fac else None,
        "participants": participants,
        "agenda": agenda,
        "decisions": decisions,
        "tasks": tasks,
        "proposals": proposals,
        "metrics": metrics,
        "projects": projects,
        "open_tensions": open_tensions,
        "can_run": await _can_run(db, ctx, m) and ctx.level != "observer",
    }


@router.patch("/meetings/{meeting_id}", summary="Edit meeting details or notes")
async def update_meeting(meeting_id: UUID, body: MeetingUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    m = await _meeting(db, ctx, meeting_id)
    if not await _can_run(db, ctx, m) and set(body.model_fields_set) - {"notes", "checkin_notes"}:
        raise err(403, "MEETING_FORBIDDEN", "Only the facilitator or a governance role can change the meeting setup.")
    sets, params = set_clause(body.model_dump(exclude_unset=True), {"title", "scheduled_at", "duration_min", "facilitator_id", "notes", "checkin_notes", "status"})
    if sets:
        await x(db, f"UPDATE meetings SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=meeting_id, u=ctx.user_id, **params)  # noqa: S608
    await db.commit()
    return {"ok": True}


@router.delete("/meetings/{meeting_id}", summary="Delete a meeting")
async def delete_meeting(meeting_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    m = await _meeting(db, ctx, meeting_id)
    if not await _can_run(db, ctx, m):
        raise err(403, "MEETING_FORBIDDEN", "Only the facilitator or a governance role can delete the meeting.")
    await x(db, "UPDATE meetings SET deleted_at = NOW() WHERE id = :id", id=meeting_id)
    await db.commit()
    return {"ok": True}


@router.post("/meetings/{meeting_id}/start", summary="Start the guided meeting")
async def start_meeting(meeting_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    m = await _meeting(db, ctx, meeting_id)
    if not await _can_run(db, ctx, m):
        raise err(403, "MEETING_FORBIDDEN", "Only the facilitator can run the meeting.")
    if m["status"] not in ("scheduled", "in_progress"):
        raise err(409, "MEETING_CLOSED", "This meeting can no longer be started.")
    await x(db, "UPDATE meetings SET status = 'in_progress', updated_at = NOW() WHERE id = :id", id=meeting_id)
    await db.commit()
    return {"ok": True}


@router.post("/meetings/{meeting_id}/step", summary="Move to an agenda step")
async def set_step(meeting_id: UUID, body: StepBody, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    m = await _meeting(db, ctx, meeting_id)
    if not await _can_run(db, ctx, m):
        raise err(403, "MEETING_FORBIDDEN", "Only the facilitator can run the meeting.")
    await x(db, "UPDATE meetings SET current_step = :s, updated_at = NOW() WHERE id = :id", s=body.step, id=meeting_id)
    await db.commit()
    return {"ok": True}


@router.post("/meetings/{meeting_id}/finish", summary="Close the meeting")
async def finish_meeting(meeting_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    m = await _meeting(db, ctx, meeting_id)
    if not await _can_run(db, ctx, m):
        raise err(403, "MEETING_FORBIDDEN", "Only the facilitator can run the meeting.")
    await x(db, "UPDATE meetings SET status = 'completed', updated_at = NOW() WHERE id = :id", id=meeting_id)
    parts = await q(db, "SELECT user_id FROM meeting_participants WHERE meeting_id = :m", m=meeting_id)
    open_tasks = await q1(db, "SELECT COUNT(*) AS n FROM tasks WHERE meeting_id = :m AND deleted_at IS NULL AND status <> 'done'", m=meeting_id)
    await notify(db, ctx.org_id, [p["user_id"] for p in parts], "meeting", f"Meeting completed: {m['title']}", f"{open_tasks['n']} follow-up action(s) open", f"/meetings/{meeting_id}", exclude=ctx.user_id)
    await audit(db, ctx, "meeting.completed", "meeting", meeting_id, m["title"])
    await db.commit()
    return {"ok": True}


@router.put("/meetings/{meeting_id}/participants", summary="Replace participants")
async def set_participants(meeting_id: UUID, body: ParticipantsBody, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    m = await _meeting(db, ctx, meeting_id)
    if not await _can_run(db, ctx, m):
        raise err(403, "MEETING_FORBIDDEN", "Only the facilitator can change participants.")
    await x(db, "DELETE FROM meeting_participants WHERE meeting_id = :m AND user_id <> ALL(:ids)", m=meeting_id, ids=body.user_ids or [ctx.user_id])
    for uid in body.user_ids:
        await x(db, "INSERT INTO meeting_participants (organization_id, meeting_id, user_id) VALUES (:o, :m, :u) ON CONFLICT DO NOTHING", o=ctx.org_id, m=meeting_id, u=uid)
    await notify(db, ctx.org_id, body.user_ids, "meeting", f"Invitation: {m['title']}", "", f"/meetings/{meeting_id}", exclude=ctx.user_id)
    await db.commit()
    return {"ok": True}


@router.post("/meetings/{meeting_id}/attendance", summary="Record attendance")
async def attendance(meeting_id: UUID, body: AttendanceBody, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    m = await _meeting(db, ctx, meeting_id)
    if not await _can_run(db, ctx, m):
        raise err(403, "MEETING_FORBIDDEN", "Only the facilitator can record attendance.")
    await x(db, "UPDATE meeting_participants SET attended = :a WHERE meeting_id = :m AND user_id = :u", a=body.attended, m=meeting_id, u=body.user_id)
    await db.commit()
    return {"ok": True}


@router.post("/meetings/{meeting_id}/agenda", summary="Add an agenda item (before the closing round)")
async def add_agenda(meeting_id: UUID, body: AgendaCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    await _meeting(db, ctx, meeting_id)
    title = body.title
    if body.tension_id:
        t = await q1(db, "SELECT title FROM tensions WHERE id = :t AND organization_id = :o AND deleted_at IS NULL", t=body.tension_id, o=ctx.org_id)
        if t is None:
            raise err(404, "TENSION_NOT_FOUND", "Tension not found.")
        title = t["title"]
    closing = await q1(db, "SELECT position FROM agenda_items WHERE meeting_id = :m AND kind = 'closing' ORDER BY position LIMIT 1", m=meeting_id)
    last = await q1(db, "SELECT COALESCE(MAX(position), -1) AS p FROM agenda_items WHERE meeting_id = :m", m=meeting_id)
    if closing:
        await x(db, "UPDATE agenda_items SET position = position + 1 WHERE meeting_id = :m AND position >= :p", m=meeting_id, p=closing["position"])
        pos = closing["position"]
    else:
        pos = last["p"] + 1
    row = await q1(
        db,
        """INSERT INTO agenda_items (organization_id, meeting_id, position, title, kind, tension_id, project_id)
           VALUES (:o, :m, :p, :t, :k, :tid, :pid) RETURNING id""",
        o=ctx.org_id, m=meeting_id, p=pos, t=title, k="tension" if body.tension_id else body.kind, tid=body.tension_id, pid=body.project_id,
    )
    await db.commit()
    return {"id": row["id"]}


@router.patch("/agenda/{item_id}", summary="Update agenda item notes/outcome/status")
async def update_agenda(item_id: UUID, body: AgendaUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    sets, params = set_clause(body.model_dump(exclude_unset=True), {"title", "notes", "outcome", "status"})
    if sets:
        await x(db, f"UPDATE agenda_items SET {sets}, updated_at = NOW() WHERE id = :id AND organization_id = :o", id=item_id, o=ctx.org_id, **params)  # noqa: S608
    await db.commit()
    return {"ok": True}


@router.delete("/agenda/{item_id}", summary="Remove an agenda item")
async def delete_agenda(item_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    item = await q1(db, "SELECT meeting_id FROM agenda_items WHERE id = :id AND organization_id = :o", id=item_id, o=ctx.org_id)
    if item is None:
        raise err(404, "AGENDA_NOT_FOUND", "Agenda item not found.")
    await x(db, "DELETE FROM agenda_items WHERE id = :id", id=item_id)
    await _renumber(db, item["meeting_id"])
    await db.commit()
    return {"ok": True}


@router.post("/meetings/{meeting_id}/decisions", summary="Record a decision made in the meeting")
async def add_decision(meeting_id: UUID, body: DecisionCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    m = await _meeting(db, ctx, meeting_id)
    row = await q1(
        db,
        """INSERT INTO governance_decisions (organization_id, circle_id, meeting_id, title, outcome, rationale, decided_by)
           VALUES (:o, :c, :m, :t, 'recorded', :r, :u) RETURNING id""",
        o=ctx.org_id, c=m["circle_id"], m=meeting_id, t=body.title, r=body.rationale, u=ctx.user_id,
    )
    await audit(db, ctx, "decision.recorded", "meeting", meeting_id, body.title)
    await db.commit()
    return {"id": row["id"]}
