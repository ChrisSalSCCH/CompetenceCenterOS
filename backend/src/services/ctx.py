"""Request context (who is calling, for which organization) and permission rules.

Permission model
----------------
* org_admin  - manages users, settings and may govern every circle.
* member     - may work (tasks, tensions, proposals ...), read everything in the org.
* observer   - read only.
* Governance authority is NOT implied by holding an arbitrary role: only holders of
  roles flagged `can_govern` (in the circle or one of its ancestors) may change the
  structure of that circle directly or decide proposals.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends
from services.auth import get_current_user_id
from services.dbx import DbDep, err, q, q1

GOVERNANCE_MODES = ("direct", "approval", "consent", "holacracy")


@dataclass(frozen=True)
class Ctx:
    user_id: UUID
    org_id: UUID
    level: str
    name: str
    email: str


async def get_ctx(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: DbDep,
) -> Ctx:
    row = await q1(
        db,
        """SELECT m.organization_id, m.access_level, u.display_name, u.email
           FROM memberships m
           JOIN users u ON u.id = m.user_id
           JOIN organizations o ON o.id = m.organization_id AND o.deleted_at IS NULL
           WHERE m.user_id = :uid AND m.active
           ORDER BY m.created_at LIMIT 1""",
        uid=user_id,
    )
    if row is None:
        raise err(403, "NO_ORGANIZATION", "This account is not a member of any organization.")
    return Ctx(
        user_id=user_id,
        org_id=row["organization_id"],
        level=row["access_level"],
        name=row["display_name"] or row["email"],
        email=row["email"],
    )


CtxDep = Annotated[Ctx, Depends(get_ctx)]


def require_write(ctx: Ctx) -> None:
    if ctx.level == "observer":
        raise err(403, "READ_ONLY", "Observers have read-only access.")


def require_admin(ctx: Ctx) -> None:
    if ctx.level != "org_admin":
        raise err(403, "ADMIN_REQUIRED", "Organization administrator permission required.")


def would_create_cycle(parents: dict[str, str | None], node: str, new_parent: str | None) -> bool:
    """True when making `new_parent` the parent of `node` would create a loop."""
    cur = new_parent
    seen: set[str] = set()
    while cur is not None:
        if cur == node:
            return True
        if cur in seen:  # pre-existing corrupt data; refuse to extend it
            return True
        seen.add(cur)
        cur = parents.get(cur)
    return False


async def circle_ancestors(db, org_id: UUID, circle_id: UUID) -> list[dict]:
    """The circle itself followed by its ancestors up to the root (depth ascending)."""
    return await q(
        db,
        """WITH RECURSIVE anc AS (
               SELECT id, parent_id, governance_mode, name, 0 AS depth FROM circles
               WHERE id = :cid AND organization_id = :org AND deleted_at IS NULL
             UNION ALL
               SELECT c.id, c.parent_id, c.governance_mode, c.name, a.depth + 1 FROM circles c
               JOIN anc a ON c.id = a.parent_id
               WHERE c.deleted_at IS NULL AND a.depth < 50
           )
           SELECT * FROM anc ORDER BY depth""",
        cid=circle_id,
        org=org_id,
    )


async def require_circle(db, ctx: Ctx, circle_id: UUID) -> dict:
    row = await q1(
        db,
        "SELECT * FROM circles WHERE id = :id AND organization_id = :org AND deleted_at IS NULL",
        id=circle_id,
        org=ctx.org_id,
    )
    if row is None:
        raise err(404, "CIRCLE_NOT_FOUND", "Circle not found.")
    return row


async def require_role(db, ctx: Ctx, role_id: UUID) -> dict:
    row = await q1(
        db,
        "SELECT * FROM roles WHERE id = :id AND organization_id = :org AND deleted_at IS NULL",
        id=role_id,
        org=ctx.org_id,
    )
    if row is None:
        raise err(404, "ROLE_NOT_FOUND", "Role not found.")
    return row


async def effective_mode(db, ctx: Ctx, circle_id: UUID) -> str:
    """Governance workflow in force for a circle: nearest explicit setting, else org default."""
    for c in await circle_ancestors(db, ctx.org_id, circle_id):
        if c["governance_mode"]:
            return c["governance_mode"]
    org = await q1(db, "SELECT default_governance_mode FROM organizations WHERE id = :o", o=ctx.org_id)
    return org["default_governance_mode"] if org else "consent"


async def can_govern(db, ctx: Ctx, circle_id: UUID) -> bool:
    if ctx.level == "org_admin":
        return True
    if ctx.level == "observer":
        return False
    ids = [c["id"] for c in await circle_ancestors(db, ctx.org_id, circle_id)]
    if not ids:
        return False
    row = await q1(
        db,
        """SELECT 1 AS ok FROM role_assignments ra
           JOIN roles r ON r.id = ra.role_id AND r.deleted_at IS NULL AND r.can_govern
           WHERE ra.user_id = :uid AND ra.organization_id = :org AND ra.deleted_at IS NULL
             AND r.circle_id = ANY(:ids) LIMIT 1""",
        uid=ctx.user_id,
        org=ctx.org_id,
        ids=ids,
    )
    return row is not None


async def require_govern(db, ctx: Ctx, circle_id: UUID) -> None:
    if not await can_govern(db, ctx, circle_id):
        raise err(
            403,
            "GOVERNANCE_FORBIDDEN",
            "You do not hold a governance role for this circle.",
        )
