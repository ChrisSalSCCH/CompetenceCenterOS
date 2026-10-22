"""Governance: proposals, workflow stages, comments/objections, decisions, history, tensions."""

from __future__ import annotations

from datetime import date
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from services.ctx import (
    CtxDep,
    can_govern,
    effective_mode,
    require_circle,
    require_govern,
    require_write,
)
from services.dbx import DbDep, err, jb, q, q1, set_clause, x
from services.events import audit, notify
from services.governance import (
    FINAL_STATUSES,
    WORKFLOW_STAGES,
    ChangeOp,
    accept_proposal,
    acceptance_blocker,
    next_status,
    notify_governors,
)
from services.orgdata import history_rows

router = APIRouter(prefix="/api", tags=["governance"])

ProposalType = Literal[
    "create_role", "modify_role", "remove_role", "create_circle", "restructure_circle",
    "change_accountabilities", "change_domains", "update_policies", "change_authorities",
]
Workflow = Literal["direct", "approval", "consent", "holacracy"]
Priority = Literal["low", "medium", "high"]
PROPOSAL_NOT_FOUND = "Proposal not found."


class ProposalCreate(BaseModel):
    circle_id: UUID
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=10000)
    reason: str = Field(default="", max_length=5000)
    expected_impact: str = Field(default="", max_length=5000)
    proposal_type: ProposalType = "modify_role"
    workflow: Workflow | None = None
    changes: list[ChangeOp] = Field(default_factory=list, max_length=20)
    source_tension_id: UUID | None = None
    meeting_id: UUID | None = None
    ai_generated: bool = False
    submit: bool = False


class ProposalUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=10000)
    reason: str | None = Field(default=None, max_length=5000)
    expected_impact: str | None = Field(default=None, max_length=5000)
    proposal_type: ProposalType | None = None
    changes: list[ChangeOp] | None = Field(default=None, max_length=20)


class CommentCreate(BaseModel):
    kind: Literal["question", "answer", "reaction", "objection", "comment", "integration"]
    body: str = Field(min_length=1, max_length=4000)


class CommentUpdate(BaseModel):
    status: Literal["resolved", "withdrawn"]
    resolution_note: str | None = Field(default=None, max_length=2000)


class DecisionBody(BaseModel):
    outcome: Literal["accepted", "rejected"]
    rationale: str = Field(default="", max_length=4000)


class TensionCreate(BaseModel):
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(default="", max_length=5000)
    context_type: Literal["circle", "role", "project", "responsibility", "process"] = "circle"
    circle_id: UUID | None = None
    role_id: UUID | None = None
    project_id: UUID | None = None
    context_label: str | None = Field(default=None, max_length=300)
    priority: Priority = "medium"


class TensionUpdate(BaseModel):
    title: str | None = Field(default=None, min_length=3, max_length=200)
    description: str | None = Field(default=None, max_length=5000)
    priority: Priority | None = None
    status: Literal["open", "processing", "resolved", "dropped"] | None = None
    circle_id: UUID | None = None
    role_id: UUID | None = None
    context_label: str | None = Field(default=None, max_length=300)


class TensionConvert(BaseModel):
    to: Literal["task", "project", "proposal", "decision", "resolution"]
    title: str | None = Field(default=None, max_length=200)
    note: str | None = Field(default=None, max_length=4000)
    assignee_id: UUID | None = None
    role_id: UUID | None = None
    circle_id: UUID | None = None
    due_date: date | None = None
    meeting_id: UUID | None = None
    proposal_type: ProposalType = "modify_role"


# ------------------------------------------------------------------ proposals


async def _proposal(db, ctx, proposal_id: UUID) -> dict:
    row = await q1(
        db,
        "SELECT * FROM governance_proposals WHERE id = :id AND organization_id = :o AND deleted_at IS NULL",
        id=proposal_id, o=ctx.org_id,
    )
    if row is None:
        raise err(404, "PROPOSAL_NOT_FOUND", PROPOSAL_NOT_FOUND)
    return row


async def _open_objections(db, proposal_id: UUID) -> int:
    row = await q1(db, "SELECT COUNT(*) AS n FROM proposal_comments WHERE proposal_id = :p AND kind = 'objection' AND status = 'open'", p=proposal_id)
    return int(row["n"]) if row else 0


@router.get("/proposals", summary="List governance proposals")
async def list_proposals(
    ctx: CtxDep,
    db: DbDep,
    status: str | None = Query(default=None, max_length=20),
    circle_id: UUID | None = None,
    mine: bool = False,
) -> list[dict]:
    where = ["gp.organization_id = :o", "gp.deleted_at IS NULL"]
    params: dict[str, Any] = {"o": ctx.org_id}
    if status == "open":
        where.append("gp.status NOT IN ('accepted','rejected','withdrawn')")
    elif status:
        where.append("gp.status = :st")
        params["st"] = status
    if circle_id:
        where.append("gp.circle_id = :c")
        params["c"] = circle_id
    if mine:
        where.append("gp.initiator_id = :u")
        params["u"] = ctx.user_id
    return await q(
        db,
        f"""SELECT gp.id, gp.title, gp.status, gp.workflow, gp.proposal_type, gp.circle_id, c.name AS circle_name,
                   gp.initiator_id, u.display_name AS initiator_name, gp.ai_generated, gp.created_at, gp.decided_at,
                   (SELECT COUNT(*) FROM proposal_comments pc WHERE pc.proposal_id = gp.id AND pc.kind = 'objection' AND pc.status = 'open') AS open_objections
            FROM governance_proposals gp JOIN circles c ON c.id = gp.circle_id JOIN users u ON u.id = gp.initiator_id
            WHERE {' AND '.join(where)} ORDER BY gp.created_at DESC LIMIT 200""",  # noqa: S608 - fragments are constants
        **params,
    )


@router.post("/proposals", summary="Create a governance proposal")
async def create_proposal(body: ProposalCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    await require_circle(db, ctx, body.circle_id)
    mode = await effective_mode(db, ctx, body.circle_id)
    workflow = body.workflow or ("approval" if mode == "direct" else mode)
    if body.submit and not body.changes:
        raise err(422, "CHANGES_REQUIRED", "A proposal needs at least one proposed modification before it can be submitted.", "changes")
    status = "submitted" if body.submit else "draft"
    row = await q1(
        db,
        """INSERT INTO governance_proposals
             (organization_id, circle_id, title, description, reason, expected_impact, proposal_type, workflow, status,
              changes, initiator_id, source_tension_id, meeting_id, ai_generated, created_by, updated_by)
           VALUES (:o, :c, :t, :d, :r, :i, :pt, :wf, :st, CAST(:ch AS jsonb), :u, :tn, :m, :ai, :u, :u) RETURNING id""",
        o=ctx.org_id, c=body.circle_id, t=body.title, d=body.description, r=body.reason, i=body.expected_impact,
        pt=body.proposal_type, wf=workflow, st=status, ch=jb([c.model_dump(mode="json") for c in body.changes]),
        u=ctx.user_id, tn=body.source_tension_id, m=body.meeting_id, ai=body.ai_generated,
    )
    if body.source_tension_id:
        await x(db, "UPDATE tensions SET status = 'processing', outcome_type = 'proposal', outcome_ref_id = :p, updated_at = NOW() WHERE id = :t AND organization_id = :o", p=row["id"], t=body.source_tension_id, o=ctx.org_id)
    await audit(db, ctx, "proposal.created", "proposal", row["id"], body.title, {"ai_generated": body.ai_generated})
    if body.submit:
        await notify_governors(db, ctx, body.circle_id, f"New governance proposal: {body.title}", f"/governance/proposals/{row['id']}")
    await db.commit()
    return {"id": row["id"], "status": status}


async def _preview(db, ctx, changes: list[dict]) -> list[dict]:
    out = []
    for ch in changes:
        op = ch.get("op", "")
        data = ch.get("data") or {}
        name = data.get("name")
        target = ch.get("id")
        if target and not name:
            table = "circles" if "circle" in op else "roles"
            row = await q1(db, f"SELECT name FROM {table} WHERE id = :i AND organization_id = :o", i=target, o=ctx.org_id)  # noqa: S608
            name = row["name"] if row else "(unknown)"
        out.append({"op": op, "id": target, "name": name, "data": data})
    return out


@router.get("/proposals/{proposal_id}", summary="Proposal detail with comments and workflow state", responses={404: {"description": PROPOSAL_NOT_FOUND}})
async def proposal_detail(proposal_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    p = await _proposal(db, ctx, proposal_id)
    circle = await q1(db, "SELECT id, name FROM circles WHERE id = :c", c=p["circle_id"])
    names = await q(db, "SELECT id, display_name FROM users WHERE id = ANY(:ids)", ids=[i for i in (p["initiator_id"], p["decided_by"]) if i])
    nm = {n["id"]: n["display_name"] for n in names}
    comments = await q(
        db,
        """SELECT pc.id, pc.kind, pc.body, pc.status, pc.resolution_note, pc.created_at, pc.author_id, u.display_name AS author_name
           FROM proposal_comments pc JOIN users u ON u.id = pc.author_id WHERE pc.proposal_id = :p ORDER BY pc.created_at""",
        p=proposal_id,
    )
    governor = await can_govern(db, ctx, p["circle_id"])
    open_obj = await _open_objections(db, proposal_id)
    final = p["status"] in FINAL_STATUSES
    tension = None
    if p["source_tension_id"]:
        tension = await q1(db, "SELECT id, title FROM tensions WHERE id = :t", t=p["source_tension_id"])
    changes_made = await history_rows(db, ctx.org_id, "gc.proposal_id = :p", 50, p=proposal_id)
    return {
        **p,
        "circle_name": circle["name"] if circle else None,
        "initiator_name": nm.get(p["initiator_id"]),
        "decided_by_name": nm.get(p["decided_by"]) if p["decided_by"] else None,
        "comments": comments,
        "stages": WORKFLOW_STAGES.get(p["workflow"], []),
        "open_objections": open_obj,
        "next_status": next_status(p["workflow"], p["status"]),
        "acceptance_blocker": acceptance_blocker(p["workflow"], p["status"], open_obj),
        "preview": await _preview(db, ctx, p["changes"]),
        "applied_changes": changes_made,
        "source_tension": tension,
        "can_decide": governor and not final and p["status"] != "draft",
        "can_advance": governor and not final and p["status"] != "draft",
        "can_edit": (p["initiator_id"] == ctx.user_id or governor) and p["status"] == "draft",
        "can_withdraw": p["initiator_id"] == ctx.user_id and not final,
    }


@router.patch("/proposals/{proposal_id}", summary="Edit a draft proposal", responses={409: {"description": "Not a draft"}})
async def update_proposal(proposal_id: UUID, body: ProposalUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    p = await _proposal(db, ctx, proposal_id)
    if p["status"] != "draft":
        raise err(409, "NOT_A_DRAFT", "Only draft proposals can be edited.")
    if p["initiator_id"] != ctx.user_id:
        await require_govern(db, ctx, p["circle_id"])
    data = body.model_dump(exclude_unset=True, mode="json")
    if "changes" in data:
        data["changes"] = jb(data["changes"])
    allowed = {"title", "description", "reason", "expected_impact", "proposal_type", "changes"}
    sets, params = set_clause(data, allowed)
    if sets:
        sets = sets.replace("changes = :changes", "changes = CAST(:changes AS jsonb)")
        await x(db, f"UPDATE governance_proposals SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=proposal_id, u=ctx.user_id, **params)  # noqa: S608
    await db.commit()
    return {"ok": True}


@router.post("/proposals/{proposal_id}/submit", summary="Submit a draft into its workflow", responses={409: {"description": "Not a draft"}, 422: {"description": "No modifications"}})
async def submit_proposal(proposal_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    p = await _proposal(db, ctx, proposal_id)
    if p["status"] != "draft":
        raise err(409, "NOT_A_DRAFT", "Only draft proposals can be submitted.")
    if p["initiator_id"] != ctx.user_id:
        await require_govern(db, ctx, p["circle_id"])
    if not p["changes"]:
        raise err(422, "CHANGES_REQUIRED", "Add at least one proposed modification first.")
    for ch in p["changes"]:
        if ch.get("id"):
            table = "circles" if "circle" in ch["op"] else "roles"
            row = await q1(db, f"SELECT id FROM {table} WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=ch["id"], o=ctx.org_id)  # noqa: S608
            if row is None:
                raise err(422, "TARGET_MISSING", "A modification refers to a circle or role that no longer exists.")
    await x(db, "UPDATE governance_proposals SET status = 'submitted', updated_at = NOW(), updated_by = :u WHERE id = :id", id=proposal_id, u=ctx.user_id)
    await audit(db, ctx, "proposal.submitted", "proposal", proposal_id, p["title"])
    await notify_governors(db, ctx, p["circle_id"], f"Proposal submitted: {p['title']}", f"/governance/proposals/{proposal_id}")
    await db.commit()
    return {"ok": True}


def _comment_allowed(workflow: str, status: str, kind: str) -> bool:
    if status in FINAL_STATUSES or status == "draft":
        return kind == "comment" and status == "draft"
    if kind == "comment":
        return True
    if workflow == "approval":
        return kind in ("question", "answer")
    if workflow == "consent":
        return kind != "integration" or status == "objections"
    allowed = {
        "question": ("submitted", "clarifying"),
        "answer": ("submitted", "clarifying"),
        "reaction": ("submitted", "clarifying", "reactions"),
        "objection": ("objections", "integration"),
        "integration": ("objections", "integration"),
    }
    return status in allowed.get(kind, ())


@router.post("/proposals/{proposal_id}/comments", summary="Add a question, reaction, objection or comment", responses={409: {"description": "Not allowed in this stage"}})
async def add_comment(proposal_id: UUID, body: CommentCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    p = await _proposal(db, ctx, proposal_id)
    if not _comment_allowed(p["workflow"], p["status"], body.kind):
        raise err(409, "STAGE_MISMATCH", f"A {body.kind} is not possible while the proposal is '{p['status']}' in the {p['workflow']} workflow.")
    if body.kind == "objection" and len(body.body.strip()) < 10:
        raise err(422, "OBJECTION_TOO_SHORT", "Please explain the objection (what harm or limitation does it cause?).", "body")
    row = await q1(
        db,
        "INSERT INTO proposal_comments (organization_id, proposal_id, author_id, kind, body) VALUES (:o, :p, :u, :k, :b) RETURNING id",
        o=ctx.org_id, p=proposal_id, u=ctx.user_id, k=body.kind, b=body.body.strip(),
    )
    await notify(db, ctx.org_id, [p["initiator_id"]], "governance", f"{ctx.name}: {body.kind} on “{p['title']}”", body.body[:200], f"/governance/proposals/{proposal_id}", exclude=ctx.user_id)
    await audit(db, ctx, f"proposal.{body.kind}", "proposal", proposal_id, p["title"])
    await db.commit()
    return {"id": row["id"]}


@router.patch("/proposal-comments/{comment_id}", summary="Resolve (integrate) or withdraw an objection")
async def update_comment(comment_id: UUID, body: CommentUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    c = await q1(
        db,
        """SELECT pc.*, gp.circle_id, gp.status AS pstatus FROM proposal_comments pc
           JOIN governance_proposals gp ON gp.id = pc.proposal_id WHERE pc.id = :id AND pc.organization_id = :o""",
        id=comment_id, o=ctx.org_id,
    )
    if c is None:
        raise err(404, "COMMENT_NOT_FOUND", "Comment not found.")
    if c["pstatus"] in FINAL_STATUSES:
        raise err(409, "PROPOSAL_CLOSED", "The proposal is already closed.")
    if body.status == "withdrawn" and c["author_id"] != ctx.user_id:
        await require_govern(db, ctx, c["circle_id"])
    if body.status == "resolved":
        await require_govern(db, ctx, c["circle_id"])
    await x(db, "UPDATE proposal_comments SET status = :s, resolution_note = :n, updated_at = NOW() WHERE id = :id", s=body.status, n=body.resolution_note, id=comment_id)
    await db.commit()
    return {"ok": True}


@router.post("/proposals/{proposal_id}/advance", summary="Move the proposal to the next workflow stage", responses={409: {"description": "No further stage"}})
async def advance(proposal_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    p = await _proposal(db, ctx, proposal_id)
    await require_govern(db, ctx, p["circle_id"])
    nxt = next_status(p["workflow"], p["status"])
    if nxt is None:
        raise err(409, "NO_NEXT_STAGE", "There is no further stage. Record the decision instead.")
    await x(db, "UPDATE governance_proposals SET status = :s, updated_at = NOW(), updated_by = :u WHERE id = :id", s=nxt, u=ctx.user_id, id=proposal_id)
    await audit(db, ctx, "proposal.advanced", "proposal", proposal_id, f"{p['title']} → {nxt}")
    await notify(db, ctx.org_id, [p["initiator_id"]], "governance", f"“{p['title']}” moved to {nxt}", "", f"/governance/proposals/{proposal_id}", exclude=ctx.user_id)
    await db.commit()
    return {"status": nxt}


@router.post("/proposals/{proposal_id}/decide", summary="Accept (apply changes in one transaction) or reject a proposal", responses={403: {"description": "Not authorized"}, 409: {"description": "Blocked by workflow"}})
async def decide(proposal_id: UUID, body: DecisionBody, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    p = await _proposal(db, ctx, proposal_id)
    await require_govern(db, ctx, p["circle_id"])
    if p["status"] in FINAL_STATUSES or p["status"] == "draft":
        raise err(409, "NOT_DECIDABLE", "This proposal cannot be decided in its current state.")
    if body.outcome == "accepted":
        if p["workflow"] == "approval" and p["initiator_id"] == ctx.user_id and ctx.level != "org_admin":
            raise err(403, "SELF_APPROVAL", "Approval workflows require a second person to approve your proposal.")
        blocker = acceptance_blocker(p["workflow"], p["status"], await _open_objections(db, proposal_id))
        if blocker:
            raise err(409, "ACCEPTANCE_BLOCKED", blocker)
        changes = await accept_proposal(db, ctx, p, body.rationale)
        summary = f"Accepted: {p['title']}"
        result: dict[str, Any] = {"status": "accepted", "changes": changes}
    else:
        await x(
            db,
            """UPDATE governance_proposals SET status = 'rejected', decided_by = :u, decided_at = NOW(), decision_note = :n,
                 updated_at = NOW(), updated_by = :u WHERE id = :id""",
            u=ctx.user_id, n=body.rationale, id=proposal_id,
        )
        await x(
            db,
            """INSERT INTO governance_decisions (organization_id, circle_id, proposal_id, meeting_id, title, outcome, rationale, decided_by)
               VALUES (:o, :c, :p, :m, :t, 'rejected', :r, :u)""",
            o=ctx.org_id, c=p["circle_id"], p=proposal_id, m=p["meeting_id"], t=p["title"], r=body.rationale, u=ctx.user_id,
        )
        summary = f"Rejected: {p['title']}"
        result = {"status": "rejected", "changes": []}
    if p["source_tension_id"]:
        await x(db, "UPDATE tensions SET status = 'resolved', resolved_at = NOW(), updated_at = NOW() WHERE id = :t AND organization_id = :o", t=p["source_tension_id"], o=ctx.org_id)
    await audit(db, ctx, f"proposal.{body.outcome}", "proposal", proposal_id, summary, {"rationale": body.rationale})
    await notify(db, ctx.org_id, [p["initiator_id"]], "governance", summary, body.rationale[:200], f"/governance/proposals/{proposal_id}", exclude=ctx.user_id)
    await db.commit()
    return result


@router.post("/proposals/{proposal_id}/withdraw", summary="Withdraw an own proposal")
async def withdraw(proposal_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    p = await _proposal(db, ctx, proposal_id)
    if p["initiator_id"] != ctx.user_id:
        raise err(403, "NOT_INITIATOR", "Only the initiator can withdraw a proposal.")
    if p["status"] in FINAL_STATUSES:
        raise err(409, "PROPOSAL_CLOSED", "The proposal is already closed.")
    await x(db, "UPDATE governance_proposals SET status = 'withdrawn', decided_at = NOW(), updated_at = NOW() WHERE id = :id", id=proposal_id)
    await x(
        db,
        "INSERT INTO governance_decisions (organization_id, circle_id, proposal_id, title, outcome, rationale, decided_by) VALUES (:o, :c, :p, :t, 'withdrawn', '', :u)",
        o=ctx.org_id, c=p["circle_id"], p=proposal_id, t=p["title"], u=ctx.user_id,
    )
    await audit(db, ctx, "proposal.withdrawn", "proposal", proposal_id, p["title"])
    await db.commit()
    return {"ok": True}


@router.get("/governance/history", summary="Versioned log of structural changes")
async def governance_history(ctx: CtxDep, db: DbDep, circle_id: UUID | None = None, limit: int = Query(default=60, ge=1, le=200)) -> list[dict]:
    if circle_id:
        return await history_rows(db, ctx.org_id, "gc.circle_id = :c", limit, c=circle_id)
    return await history_rows(db, ctx.org_id, "gc.source <> 'seed'", limit)


@router.get("/governance/decisions", summary="Decision records")
async def decisions(ctx: CtxDep, db: DbDep, circle_id: UUID | None = None) -> list[dict]:
    where = "gd.organization_id = :o" + (" AND gd.circle_id = :c" if circle_id else "")
    params: dict[str, Any] = {"o": ctx.org_id}
    if circle_id:
        params["c"] = circle_id
    return await q(
        db,
        f"""SELECT gd.id, gd.title, gd.outcome, gd.rationale, gd.created_at, gd.proposal_id, gd.meeting_id, gd.circle_id,
                   c.name AS circle_name, u.display_name AS decided_by_name
            FROM governance_decisions gd LEFT JOIN circles c ON c.id = gd.circle_id LEFT JOIN users u ON u.id = gd.decided_by
            WHERE {where} ORDER BY gd.created_at DESC LIMIT 100""",  # noqa: S608 - constants only
        **params,
    )


# --------------------------------------------------------------------- tensions


@router.get("/tensions", summary="List tensions (own inbox or circle backlog)")
async def list_tensions(
    ctx: CtxDep,
    db: DbDep,
    scope: Literal["mine", "circle", "all"] = "mine",
    circle_id: UUID | None = None,
    status: str | None = Query(default=None, max_length=20),
) -> list[dict]:
    where = ["t.organization_id = :o", "t.deleted_at IS NULL"]
    params: dict[str, Any] = {"o": ctx.org_id}
    if scope == "mine":
        where.append("t.creator_id = :u")
        params["u"] = ctx.user_id
    if circle_id:
        where.append("t.circle_id = :c")
        params["c"] = circle_id
    if status == "open":
        where.append("t.status IN ('open','processing')")
    elif status:
        where.append("t.status = :st")
        params["st"] = status
    return await q(
        db,
        f"""SELECT t.id, t.title, t.description, t.context_type, t.context_label, t.priority, t.status, t.outcome_type,
                   t.outcome_ref_id, t.resolution_note, t.created_at, t.circle_id, c.name AS circle_name,
                   t.role_id, r.name AS role_name, t.creator_id, u.display_name AS creator_name
            FROM tensions t JOIN users u ON u.id = t.creator_id
            LEFT JOIN circles c ON c.id = t.circle_id LEFT JOIN roles r ON r.id = t.role_id
            WHERE {' AND '.join(where)}
            ORDER BY (t.status IN ('resolved','dropped')), CASE t.priority WHEN 'high' THEN 0 WHEN 'medium' THEN 1 ELSE 2 END, t.created_at DESC LIMIT 300""",  # noqa: S608 - constants only
        **params,
    )


@router.post("/tensions", summary="Capture a tension")
async def create_tension(body: TensionCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    circle_id = body.circle_id
    if body.role_id:
        role = await q1(db, "SELECT circle_id FROM roles WHERE id = :r AND organization_id = :o AND deleted_at IS NULL", r=body.role_id, o=ctx.org_id)
        if role is None:
            raise err(404, "ROLE_NOT_FOUND", "Role not found.", "role_id")
        circle_id = circle_id or role["circle_id"]
    if circle_id:
        await require_circle(db, ctx, circle_id)
    row = await q1(
        db,
        """INSERT INTO tensions (organization_id, title, description, creator_id, context_type, circle_id, role_id, project_id,
                                 context_label, priority, created_by, updated_by)
           VALUES (:o, :t, :d, :u, :ct, :c, :r, :p, :cl, :pr, :u, :u) RETURNING id""",
        o=ctx.org_id, t=body.title, d=body.description, u=ctx.user_id, ct=body.context_type, c=circle_id,
        r=body.role_id, p=body.project_id, cl=body.context_label, pr=body.priority,
    )
    await audit(db, ctx, "tension.created", "tension", row["id"], body.title)
    await db.commit()
    return {"id": row["id"]}


async def _tension(db, ctx, tension_id: UUID) -> dict:
    t = await q1(db, "SELECT * FROM tensions WHERE id = :id AND organization_id = :o AND deleted_at IS NULL", id=tension_id, o=ctx.org_id)
    if t is None:
        raise err(404, "TENSION_NOT_FOUND", "Tension not found.")
    return t


@router.patch("/tensions/{tension_id}", summary="Edit a tension")
async def update_tension(tension_id: UUID, body: TensionUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    t = await _tension(db, ctx, tension_id)
    if t["creator_id"] != ctx.user_id and t["circle_id"]:
        await require_govern(db, ctx, t["circle_id"])
    data = body.model_dump(exclude_unset=True)
    sets, params = set_clause(data, {"title", "description", "priority", "status", "circle_id", "role_id", "context_label"})
    if sets:
        extra = ", resolved_at = NOW()" if data.get("status") in ("resolved", "dropped") else ""
        await x(db, f"UPDATE tensions SET {sets}{extra}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=tension_id, u=ctx.user_id, **params)  # noqa: S608
    await db.commit()
    return {"ok": True}


@router.post("/tensions/{tension_id}/convert", summary="Turn a tension into a task, project, proposal, decision or documented resolution")
async def convert_tension(tension_id: UUID, body: TensionConvert, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    t = await _tension(db, ctx, tension_id)
    circle_id = body.circle_id or t["circle_id"]
    title = (body.title or t["title"])[:200]
    ref: UUID | None = None
    status = "resolved"
    if body.to == "task":
        row = await q1(
            db,
            """INSERT INTO tasks (organization_id, circle_id, role_id, assignee_id, tension_id, meeting_id, title, description, due_date, created_by, updated_by)
               VALUES (:o, :c, :r, :a, :t, :m, :ti, :d, :due, :u, :u) RETURNING id""",
            o=ctx.org_id, c=circle_id, r=body.role_id or t["role_id"], a=body.assignee_id or ctx.user_id, t=tension_id,
            m=body.meeting_id, ti=title, d=body.note or t["description"], due=body.due_date, u=ctx.user_id,
        )
        ref = row["id"]
    elif body.to == "project":
        if circle_id is None:
            raise err(422, "CIRCLE_REQUIRED", "Choose a circle for the new project.", "circle_id")
        row = await q1(
            db,
            """INSERT INTO projects (organization_id, circle_id, owning_role_id, name, description, status, created_by, updated_by)
               VALUES (:o, :c, :r, :n, :d, 'planned', :u, :u) RETURNING id""",
            o=ctx.org_id, c=circle_id, r=body.role_id or t["role_id"], n=title, d=body.note or t["description"], u=ctx.user_id,
        )
        ref = row["id"]
    elif body.to == "proposal":
        if circle_id is None:
            raise err(422, "CIRCLE_REQUIRED", "Choose a circle for the governance proposal.", "circle_id")
        mode = await effective_mode(db, ctx, circle_id)
        row = await q1(
            db,
            """INSERT INTO governance_proposals (organization_id, circle_id, title, description, reason, proposal_type, workflow, status,
                                                 changes, initiator_id, source_tension_id, meeting_id, created_by, updated_by)
               VALUES (:o, :c, :ti, :d, :re, :pt, :wf, 'draft', '[]', :u, :t, :m, :u, :u) RETURNING id""",
            o=ctx.org_id, c=circle_id, ti=title, d=body.note or "", re=t["description"], pt=body.proposal_type,
            wf="approval" if mode == "direct" else mode, u=ctx.user_id, t=tension_id, m=body.meeting_id,
        )
        ref = row["id"]
        status = "processing"
    elif body.to == "decision":
        row = await q1(
            db,
            """INSERT INTO governance_decisions (organization_id, circle_id, meeting_id, title, outcome, rationale, decided_by)
               VALUES (:o, :c, :m, :ti, 'recorded', :r, :u) RETURNING id""",
            o=ctx.org_id, c=circle_id, m=body.meeting_id, ti=title, r=body.note or "", u=ctx.user_id,
        )
        ref = row["id"]
    elif not (body.note and body.note.strip()):
        raise err(422, "NOTE_REQUIRED", "Describe how the tension was resolved.", "note")
    await x(
        db,
        """UPDATE tensions SET status = :s, outcome_type = :ot, outcome_ref_id = :ref, resolution_note = COALESCE(:n, resolution_note),
             resolved_at = CASE WHEN CAST(:s AS varchar) = 'resolved' THEN NOW() ELSE NULL END, updated_at = NOW(), updated_by = :u WHERE id = :id""",
        s=status, ot=body.to, ref=ref, n=body.note, u=ctx.user_id, id=tension_id,
    )
    await audit(db, ctx, f"tension.to_{body.to}", "tension", tension_id, title)
    await db.commit()
    return {"outcome_type": body.to, "outcome_ref_id": ref}
