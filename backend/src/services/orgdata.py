"""Read models for the organization structure."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from services.dbx import q


async def load_structure(db, org_id: UUID) -> dict[str, list[dict[str, Any]]]:
    """All live circles and roles of an organization with items and role holders."""
    circles = await q(
        db,
        """SELECT id, parent_id, name, purpose, description, governance_mode, position
           FROM circles WHERE organization_id = :o AND deleted_at IS NULL ORDER BY position, name""",
        o=org_id,
    )
    roles = await q(
        db,
        """SELECT id, circle_id, name, purpose, description, allow_multiple, can_govern, lead_user_id
           FROM roles WHERE organization_id = :o AND deleted_at IS NULL ORDER BY name""",
        o=org_id,
    )
    items = await q(
        db,
        """SELECT circle_id, role_id, kind, text, detail, authority_level
           FROM governance_items WHERE organization_id = :o AND deleted_at IS NULL ORDER BY position, created_at""",
        o=org_id,
    )
    holders = await q(
        db,
        """SELECT ra.id AS assignment_id, ra.role_id, ra.user_id, ra.focus,
                  u.display_name AS name, m.avatar_color
           FROM role_assignments ra
           JOIN users u ON u.id = ra.user_id
           JOIN memberships m ON m.user_id = ra.user_id AND m.organization_id = ra.organization_id
           WHERE ra.organization_id = :o AND ra.deleted_at IS NULL ORDER BY u.display_name""",
        o=org_id,
    )
    key_of = {
        "accountability": "accountabilities",
        "domain": "domains",
        "policy": "policies",
        "decision_authority": "authorities",
    }
    for c in circles:
        c.update(accountabilities=[], domains=[], policies=[])
    for r in roles:
        r.update(accountabilities=[], domains=[], policies=[], authorities=[], holders=[])
    cmap = {c["id"]: c for c in circles}
    rmap = {r["id"]: r for r in roles}
    for it in items:
        entry = {"text": it["text"], "detail": it["detail"], "level": it["authority_level"]}
        owner = rmap.get(it["role_id"]) if it["role_id"] else cmap.get(it["circle_id"])
        if owner is not None:
            owner[key_of[it["kind"]]].append(entry)
    for h in holders:
        if h["role_id"] in rmap:
            rmap[h["role_id"]]["holders"].append(h)
    return {"circles": circles, "roles": roles}


async def load_structure_as_of(db, org_id: UUID, as_of: datetime) -> dict[str, list[dict[str, Any]]]:
    """Reconstruct circles and roles as they were at a point in time from versioned snapshots."""
    rows = await q(
        db,
        """SELECT DISTINCT ON (entity_type, entity_id) entity_type, entity_id, op, after_state
           FROM governance_changes WHERE organization_id = :o AND created_at <= :t
           ORDER BY entity_type, entity_id, created_at DESC""",
        o=org_id,
        t=as_of,
    )
    circles: list[dict[str, Any]] = []
    roles: list[dict[str, Any]] = []
    for r in rows:
        if r["op"] == "delete" or not r["after_state"]:
            continue
        snap = dict(r["after_state"])
        snap["holders"] = []
        snap["lead_user_id"] = None
        snap.setdefault("authorities", [])
        (circles if r["entity_type"] == "circle" else roles).append(snap)
    return {"circles": circles, "roles": roles}


async def history_rows(db, org_id: UUID, where: str, limit: int = 60, **params: Any) -> list[dict[str, Any]]:
    """Governance change history with actor and proposal titles. `where` is a trusted fragment."""
    return await q(
        db,
        f"""SELECT gc.id, gc.proposal_id, gc.circle_id, gc.entity_type, gc.entity_id, gc.op, gc.source,
                   gc.before_state, gc.after_state, gc.summary, gc.reason, gc.created_at,
                   u.display_name AS actor_name, gp.title AS proposal_title,
                   du.display_name AS decided_by_name
            FROM governance_changes gc
            LEFT JOIN users u ON u.id = gc.actor_id
            LEFT JOIN governance_proposals gp ON gp.id = gc.proposal_id
            LEFT JOIN users du ON du.id = gp.decided_by
            WHERE gc.organization_id = :o AND ({where})
            ORDER BY gc.created_at DESC LIMIT {int(limit)}""",  # noqa: S608 - trusted fragments only
        o=org_id,
        **params,
    )
