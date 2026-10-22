"""Governance engine.

Structural changes (circles/roles and their accountabilities, domains, policies and
decision authorities) are expressed as *change operations*. The same operations are
used for direct authorized changes and for accepted proposals; each applied operation
writes a versioned before/after snapshot to `governance_changes`. Applying a proposal
happens inside the caller's single database transaction: nothing is committed unless
every operation succeeds.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, Field
from services.ctx import (
    GOVERNANCE_MODES,
    Ctx,
    can_govern,
    effective_mode,
    would_create_cycle,
)
from services.dbx import err, jb, q, q1, x
from services.events import audit, notify

ITEM_KEYS = {
    "accountabilities": "accountability",
    "domains": "domain",
    "policies": "policy",
    "authorities": "decision_authority",
}
AUTHORITY_LEVELS = ("decides", "consents", "consulted", "informed")

WORKFLOW_STAGES: dict[str, list[str]] = {
    "approval": ["submitted"],
    "consent": ["submitted", "objections"],
    "holacracy": ["submitted", "clarifying", "reactions", "objections", "integration"],
}
FINAL_STATUSES = ("accepted", "rejected", "withdrawn")


class ChangeOp(BaseModel):
    op: Literal[
        "create_circle",
        "update_circle",
        "delete_circle",
        "create_role",
        "update_role",
        "delete_role",
    ]
    id: UUID | None = None
    data: dict[str, Any] = Field(default_factory=dict)


# ----------------------------- pure workflow rules -----------------------------


def next_status(workflow: str, status: str) -> str | None:
    stages = WORKFLOW_STAGES.get(workflow, [])
    if status not in stages:
        return None
    i = stages.index(status)
    return stages[i + 1] if i + 1 < len(stages) else None


def acceptance_blocker(workflow: str, status: str, open_objections: int) -> str | None:
    """Return a human-readable reason why a proposal cannot be accepted yet, else None."""
    if status in FINAL_STATUSES:
        return "The proposal is already closed."
    if status == "draft":
        return "The proposal has not been submitted yet."
    if workflow == "approval":
        return None
    if open_objections > 0:
        return f"{open_objections} objection(s) are still open and must be integrated or withdrawn."
    if workflow == "consent":
        return None
    if workflow == "holacracy" and status in ("objections", "integration"):
        return None
    return "The structured process has not reached the objection/integration stage yet."


# ----------------------------------- snapshots ----------------------------------


def _norm_items(raw: Any, key: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for it in raw or []:
        if isinstance(it, str):
            it = {"text": it}
        text = str(it.get("text", "")).strip()
        if not text:
            continue
        if len(text) > 600:
            raise err(422, "ITEM_TOO_LONG", f"{key}: entries are limited to 600 characters.", key)
        level = it.get("level")
        if key == "authorities":
            level = level if level in AUTHORITY_LEVELS else "decides"
        else:
            level = None
        detail = (str(it.get("detail")).strip() or None) if it.get("detail") else None
        out.append({"text": text, "detail": detail, "level": level})
    return out


async def _items(db, *, role_id: UUID | None = None, circle_id: UUID | None = None) -> dict[str, list]:
    if role_id is not None:
        rows = await q(
            db,
            """SELECT kind, text, detail, authority_level FROM governance_items
               WHERE role_id = :o AND deleted_at IS NULL ORDER BY position, created_at""",
            o=role_id,
        )
    else:
        rows = await q(
            db,
            """SELECT kind, text, detail, authority_level FROM governance_items
               WHERE circle_id = :o AND deleted_at IS NULL ORDER BY position, created_at""",
            o=circle_id,
        )
    out: dict[str, list] = {k: [] for k in ITEM_KEYS}
    inv = {v: k for k, v in ITEM_KEYS.items()}
    for r in rows:
        out[inv[r["kind"]]].append(
            {"text": r["text"], "detail": r["detail"], "level": r["authority_level"]}
        )
    return out


async def circle_snapshot(db, org_id: UUID, circle_id: UUID, include_deleted: bool = False) -> dict | None:
    sql = "SELECT * FROM circles WHERE id = :id AND organization_id = :org"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    c = await q1(db, sql, id=circle_id, org=org_id)
    if c is None:
        return None
    items = await _items(db, circle_id=circle_id)
    return {
        "id": str(c["id"]),
        "name": c["name"],
        "purpose": c["purpose"],
        "description": c["description"],
        "parent_id": str(c["parent_id"]) if c["parent_id"] else None,
        "governance_mode": c["governance_mode"],
        "accountabilities": items["accountabilities"],
        "domains": items["domains"],
        "policies": items["policies"],
    }


async def role_snapshot(db, org_id: UUID, role_id: UUID, include_deleted: bool = False) -> dict | None:
    sql = "SELECT * FROM roles WHERE id = :id AND organization_id = :org"
    if not include_deleted:
        sql += " AND deleted_at IS NULL"
    r = await q1(db, sql, id=role_id, org=org_id)
    if r is None:
        return None
    items = await _items(db, role_id=role_id)
    return {
        "id": str(r["id"]),
        "name": r["name"],
        "purpose": r["purpose"],
        "description": r["description"],
        "circle_id": str(r["circle_id"]),
        "allow_multiple": r["allow_multiple"],
        "can_govern": r["can_govern"],
        "accountabilities": items["accountabilities"],
        "domains": items["domains"],
        "policies": items["policies"],
        "authorities": items["authorities"],
    }


async def record_change(
    db,
    ctx: Ctx,
    *,
    proposal_id: UUID | None,
    circle_id: UUID | None,
    entity_type: str,
    entity_id: UUID,
    op: str,
    before: dict | None,
    after: dict | None,
    source: str,
    summary: str,
    reason: str | None = None,
    at: datetime | None = None,
) -> None:
    await x(
        db,
        """INSERT INTO governance_changes
             (organization_id, proposal_id, circle_id, entity_type, entity_id, op, source,
              before_state, after_state, summary, actor_id, reason, created_at)
           VALUES (:org, :pid, :cid, :et, :eid, :op, :src, CAST(:b AS jsonb), CAST(:a AS jsonb),
                   :sum, :actor, :reason, COALESCE(:at, clock_timestamp()))""",
        org=ctx.org_id,
        pid=proposal_id,
        cid=circle_id,
        et=entity_type,
        eid=entity_id,
        op=op,
        src=source,
        b=jb(before) if before is not None else None,
        a=jb(after) if after is not None else None,
        sum=summary[:300],
        actor=ctx.user_id,
        reason=reason,
        at=at,
    )


async def _replace_items(
    db, ctx: Ctx, key: str, raw: Any, *, role_id: UUID | None = None, circle_id: UUID | None = None
) -> None:
    kind = ITEM_KEYS[key]
    owner_sql = "role_id = :o" if role_id else "circle_id = :o"
    owner = role_id or circle_id
    await x(
        db,
        f"UPDATE governance_items SET deleted_at = NOW() WHERE deleted_at IS NULL AND kind = :k AND {owner_sql}",
        k=kind,
        o=owner,
    )
    for pos, it in enumerate(_norm_items(raw, key)):
        await x(
            db,
            """INSERT INTO governance_items
                 (organization_id, circle_id, role_id, kind, text, detail, authority_level, position, created_by)
               VALUES (:org, :cid, :rid, :k, :t, :d, :lvl, :pos, :actor)""",
            org=ctx.org_id,
            cid=circle_id,
            rid=role_id,
            k=kind,
            t=it["text"],
            d=it["detail"],
            lvl=it["level"],
            pos=pos,
            actor=ctx.user_id,
        )


def _clean_name(data: dict[str, Any], required: bool) -> str | None:
    if "name" not in data and not required:
        return None
    name = str(data.get("name", "")).strip()
    if not name:
        raise err(422, "NAME_REQUIRED", "A name is required.", "name")
    if len(name) > 120:
        raise err(422, "NAME_TOO_LONG", "Names are limited to 120 characters.", "name")
    return name


async def _parent_map(db, org_id: UUID) -> dict[str, str | None]:
    rows = await q(db, "SELECT id, parent_id FROM circles WHERE organization_id = :o AND deleted_at IS NULL", o=org_id)
    return {str(r["id"]): (str(r["parent_id"]) if r["parent_id"] else None) for r in rows}


async def _ensure_circle(db, org_id: UUID, circle_id: Any) -> UUID:
    try:
        cid = UUID(str(circle_id))
    except (ValueError, TypeError):
        raise err(422, "CIRCLE_INVALID", "A valid circle id is required.", "circle_id") from None
    row = await q1(db, "SELECT id FROM circles WHERE id = :id AND organization_id = :o AND deleted_at IS NULL", id=cid, o=org_id)
    if row is None:
        raise err(404, "CIRCLE_NOT_FOUND", "Circle not found in this organization.")
    return cid


def _check_mode(mode: Any) -> str | None:
    if mode in (None, "", "inherit"):
        return None
    if mode not in GOVERNANCE_MODES:
        raise err(422, "MODE_INVALID", "Unknown governance mode.", "governance_mode")
    return str(mode)


# ------------------------------- operation executor -------------------------------


async def apply_op(
    db,
    ctx: Ctx,
    op: ChangeOp,
    *,
    proposal_id: UUID | None,
    source: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Apply a single operation inside the caller's transaction. Returns a change summary."""
    d = op.data
    org = ctx.org_id
    handler = _HANDLERS[op.op]
    return await handler(db, ctx, op, d, org, proposal_id, source, reason)


async def _create_circle(db, ctx, op, d, org, pid, source, reason):
    name = _clean_name(d, True)
    parent_id = await _ensure_circle(db, org, d.get("parent_id"))
    row = await q1(
        db,
        """INSERT INTO circles (organization_id, parent_id, name, purpose, description, governance_mode, created_by, updated_by)
           VALUES (:org, :p, :n, :pu, :de, :gm, :a, :a) RETURNING id""",
        org=org, p=parent_id, n=name, pu=str(d.get("purpose", "")), de=str(d.get("description", "")),
        gm=_check_mode(d.get("governance_mode")), a=ctx.user_id,
    )
    cid = row["id"]
    for key in ("accountabilities", "domains", "policies"):
        await _replace_items(db, ctx, key, d.get(key), circle_id=cid)
    after = await circle_snapshot(db, org, cid)
    summary = f"Created circle “{name}”"
    await record_change(db, ctx, proposal_id=pid, circle_id=cid, entity_type="circle", entity_id=cid, op="create",
                        before=None, after=after, source=source, summary=summary, reason=reason)
    return {"entity_type": "circle", "entity_id": cid, "op": "create", "summary": summary}


async def _update_circle(db, ctx, op, d, org, pid, source, reason):
    cid = await _ensure_circle(db, org, op.id)
    before = await circle_snapshot(db, org, cid)
    sets: dict[str, Any] = {}
    if "name" in d:
        sets["name"] = _clean_name(d, True)
    for k in ("purpose", "description"):
        if k in d:
            sets[k] = str(d[k])
    if "governance_mode" in d:
        sets["governance_mode"] = _check_mode(d["governance_mode"])
    if "parent_id" in d:
        if before["parent_id"] is None:
            raise err(409, "ROOT_CIRCLE_FIXED", "The root circle cannot be moved below another circle.")
        new_parent = await _ensure_circle(db, org, d["parent_id"])
        if would_create_cycle(await _parent_map(db, org), str(cid), str(new_parent)):
            raise err(409, "CIRCLE_CYCLE", "A circle cannot be moved below itself or one of its subcircles.", "parent_id")
        sets["parent_id"] = new_parent
    if sets:
        cols = ", ".join(f"{k} = :{k}" for k in sets)
        await x(db, f"UPDATE circles SET {cols}, updated_at = NOW(), updated_by = :actor WHERE id = :id",
                id=cid, actor=ctx.user_id, **sets)
    for key in ("accountabilities", "domains", "policies"):
        if key in d:
            await _replace_items(db, ctx, key, d[key], circle_id=cid)
    after = await circle_snapshot(db, org, cid)
    summary = f"Updated circle “{after['name']}”"
    await record_change(db, ctx, proposal_id=pid, circle_id=cid, entity_type="circle", entity_id=cid, op="update",
                        before=before, after=after, source=source, summary=summary, reason=reason)
    return {"entity_type": "circle", "entity_id": cid, "op": "update", "summary": summary}


async def _delete_circle(db, ctx, op, d, org, pid, source, reason):
    cid = await _ensure_circle(db, org, op.id)
    before = await circle_snapshot(db, org, cid)
    if before["parent_id"] is None:
        raise err(409, "ROOT_CIRCLE_FIXED", "The root circle cannot be removed.")
    kids = await q1(db, "SELECT COUNT(*) AS n FROM circles WHERE parent_id = :id AND deleted_at IS NULL", id=cid)
    roles = await q1(db, "SELECT COUNT(*) AS n FROM roles WHERE circle_id = :id AND deleted_at IS NULL", id=cid)
    if kids["n"] or roles["n"]:
        raise err(409, "CIRCLE_NOT_EMPTY", "Remove or move the roles and subcircles first.")
    await x(db, "UPDATE circles SET deleted_at = NOW(), updated_at = NOW(), updated_by = :a WHERE id = :id", id=cid, a=ctx.user_id)
    summary = f"Removed circle “{before['name']}”"
    await record_change(db, ctx, proposal_id=pid, circle_id=cid, entity_type="circle", entity_id=cid, op="delete",
                        before=before, after=None, source=source, summary=summary, reason=reason)
    return {"entity_type": "circle", "entity_id": cid, "op": "delete", "summary": summary}


async def _create_role(db, ctx, op, d, org, pid, source, reason):
    name = _clean_name(d, True)
    cid = await _ensure_circle(db, org, d.get("circle_id"))
    row = await q1(
        db,
        """INSERT INTO roles (organization_id, circle_id, name, purpose, description, allow_multiple, can_govern, template_key, created_by, updated_by)
           VALUES (:org, :c, :n, :pu, :de, :am, :cg, :tk, :a, :a) RETURNING id""",
        org=org, c=cid, n=name, pu=str(d.get("purpose", "")), de=str(d.get("description", "")),
        am=bool(d.get("allow_multiple", False)), cg=bool(d.get("can_govern", False)),
        tk=d.get("template_key"), a=ctx.user_id,
    )
    rid = row["id"]
    for key in ITEM_KEYS:
        await _replace_items(db, ctx, key, d.get(key), role_id=rid)
    after = await role_snapshot(db, org, rid)
    summary = f"Created role “{name}”"
    await record_change(db, ctx, proposal_id=pid, circle_id=cid, entity_type="role", entity_id=rid, op="create",
                        before=None, after=after, source=source, summary=summary, reason=reason)
    return {"entity_type": "role", "entity_id": rid, "op": "create", "summary": summary}


async def _ensure_role(db, org_id: UUID, role_id: Any) -> UUID:
    try:
        rid = UUID(str(role_id))
    except (ValueError, TypeError):
        raise err(422, "ROLE_INVALID", "A valid role id is required.") from None
    row = await q1(db, "SELECT id FROM roles WHERE id = :id AND organization_id = :o AND deleted_at IS NULL", id=rid, o=org_id)
    if row is None:
        raise err(404, "ROLE_NOT_FOUND", "Role not found in this organization.")
    return rid


async def _update_role(db, ctx, op, d, org, pid, source, reason):
    rid = await _ensure_role(db, org, op.id)
    before = await role_snapshot(db, org, rid)
    sets: dict[str, Any] = {}
    if "name" in d:
        sets["name"] = _clean_name(d, True)
    for k in ("purpose", "description"):
        if k in d:
            sets[k] = str(d[k])
    for k in ("allow_multiple", "can_govern"):
        if k in d:
            sets[k] = bool(d[k])
    if "circle_id" in d:
        sets["circle_id"] = await _ensure_circle(db, org, d["circle_id"])
    if sets.get("allow_multiple") is False:
        holders = await q1(db, "SELECT COUNT(*) AS n FROM role_assignments WHERE role_id = :r AND deleted_at IS NULL", r=rid)
        if holders["n"] > 1:
            raise err(409, "ROLE_HAS_MULTIPLE_HOLDERS", "Unassign extra role holders before disallowing multiple holders.")
    if sets:
        cols = ", ".join(f"{k} = :{k}" for k in sets)
        await x(db, f"UPDATE roles SET {cols}, updated_at = NOW(), updated_by = :actor WHERE id = :id",
                id=rid, actor=ctx.user_id, **sets)
    for key in ITEM_KEYS:
        if key in d:
            await _replace_items(db, ctx, key, d[key], role_id=rid)
    after = await role_snapshot(db, org, rid)
    summary = f"Updated role “{after['name']}”"
    await record_change(db, ctx, proposal_id=pid, circle_id=UUID(after["circle_id"]), entity_type="role", entity_id=rid,
                        op="update", before=before, after=after, source=source, summary=summary, reason=reason)
    return {"entity_type": "role", "entity_id": rid, "op": "update", "summary": summary}


async def _delete_role(db, ctx, op, d, org, pid, source, reason):
    rid = await _ensure_role(db, org, op.id)
    before = await role_snapshot(db, org, rid)
    await x(db, "UPDATE role_assignments SET deleted_at = NOW() WHERE role_id = :r AND deleted_at IS NULL", r=rid)
    await x(db, "UPDATE roles SET deleted_at = NOW(), updated_at = NOW(), updated_by = :a WHERE id = :r", r=rid, a=ctx.user_id)
    summary = f"Removed role “{before['name']}”"
    await record_change(db, ctx, proposal_id=pid, circle_id=UUID(before["circle_id"]), entity_type="role", entity_id=rid,
                        op="delete", before=before, after=None, source=source, summary=summary, reason=reason)
    return {"entity_type": "role", "entity_id": rid, "op": "delete", "summary": summary}


_HANDLERS = {
    "create_circle": _create_circle,
    "update_circle": _update_circle,
    "delete_circle": _delete_circle,
    "create_role": _create_role,
    "update_role": _update_role,
    "delete_role": _delete_role,
}

PROPOSAL_TYPE_BY_OP = {
    "create_circle": "create_circle",
    "update_circle": "restructure_circle",
    "delete_circle": "restructure_circle",
    "create_role": "create_role",
    "update_role": "modify_role",
    "delete_role": "remove_role",
}


# ------------------------------- policy-aware entry -------------------------------


async def submit_structural_change(
    db,
    ctx: Ctx,
    circle_id: UUID,
    ops: list[ChangeOp],
    *,
    title: str,
    reason: str = "",
    description: str = "",
) -> dict[str, Any]:
    """Apply directly when policy + authority allow it, otherwise open a proposal."""
    mode = await effective_mode(db, ctx, circle_id)
    if mode == "direct" and await can_govern(db, ctx, circle_id):
        changes = [await apply_op(db, ctx, op, proposal_id=None, source="direct", reason=reason or None) for op in ops]
        await audit(db, ctx, "governance.direct_change", "circle", circle_id, title, {"changes": [c["summary"] for c in changes]})
        return {"applied": True, "mode": mode, "changes": changes}
    workflow = "approval" if mode == "direct" else mode
    ptype = PROPOSAL_TYPE_BY_OP[ops[0].op] if ops else "modify_role"
    row = await q1(
        db,
        """INSERT INTO governance_proposals
             (organization_id, circle_id, title, description, reason, proposal_type, workflow, status, changes, initiator_id, created_by, updated_by)
           VALUES (:org, :cid, :t, :de, :re, :pt, :wf, 'submitted', CAST(:ch AS jsonb), :u, :u, :u) RETURNING id""",
        org=ctx.org_id, cid=circle_id, t=title[:200], de=description, re=reason, pt=ptype, wf=workflow,
        ch=jb([op.model_dump(mode="json") for op in ops]), u=ctx.user_id,
    )
    await audit(db, ctx, "governance.proposal_created", "proposal", row["id"], title, {"mode": mode})
    await notify_governors(db, ctx, circle_id, f"New governance proposal: {title}", f"/governance/proposals/{row['id']}")
    return {"applied": False, "mode": mode, "proposal_id": row["id"], "workflow": workflow}


async def notify_governors(db, ctx: Ctx, circle_id: UUID, title: str, link: str) -> None:
    from services.ctx import circle_ancestors

    ids = [c["id"] for c in await circle_ancestors(db, ctx.org_id, circle_id)]
    rows = await q(
        db,
        """SELECT DISTINCT ra.user_id FROM role_assignments ra
           JOIN roles r ON r.id = ra.role_id AND r.can_govern AND r.deleted_at IS NULL
           WHERE ra.deleted_at IS NULL AND ra.organization_id = :o AND r.circle_id = ANY(:ids)
           UNION SELECT user_id FROM memberships WHERE organization_id = :o AND access_level = 'org_admin' AND active""",
        o=ctx.org_id, ids=ids,
    )
    await notify(db, ctx.org_id, [r["user_id"] for r in rows], "governance", title, "", link, exclude=ctx.user_id)


async def accept_proposal(db, ctx: Ctx, proposal: dict[str, Any], rationale: str) -> list[dict[str, Any]]:
    """Apply every operation of the proposal (caller commits once) and record the decision."""
    ops = [ChangeOp.model_validate(o) for o in proposal["changes"]]
    changes = [
        await apply_op(db, ctx, op, proposal_id=proposal["id"], source="proposal", reason=proposal["reason"] or None)
        for op in ops
    ]
    await x(
        db,
        """UPDATE governance_proposals SET status = 'accepted', decided_by = :u, decided_at = NOW(),
             decision_note = :n, updated_at = NOW(), updated_by = :u WHERE id = :id""",
        u=ctx.user_id, n=rationale, id=proposal["id"],
    )
    await x(
        db,
        """INSERT INTO governance_decisions (organization_id, circle_id, proposal_id, meeting_id, title, outcome, rationale, decided_by)
           VALUES (:o, :c, :p, :m, :t, 'accepted', :r, :u)""",
        o=ctx.org_id, c=proposal["circle_id"], p=proposal["id"], m=proposal["meeting_id"], t=proposal["title"], r=rationale, u=ctx.user_id,
    )
    return changes
