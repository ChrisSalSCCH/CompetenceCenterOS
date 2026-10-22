"""Administration: users, organization settings, audit log, export, demo reset."""

from __future__ import annotations

import re
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, EmailStr, Field
from services.auth import hash_password
from services.ctx import CtxDep, require_admin
from services.dbx import DbDep, err, q, q1, set_clause, x
from services.events import audit
from services.seed import reset_demo

router = APIRouter(prefix="/api/admin", tags=["admin"])

AccessLevel = Literal["org_admin", "member", "observer"]
PASSWORD_RULE = re.compile(r"^(?=.*[A-Za-z])(?=.*\d).{10,128}$")


class UserCreate(BaseModel):
    email: EmailStr
    display_name: str = Field(min_length=2, max_length=120)
    password: str = Field(min_length=10, max_length=128)
    access_level: AccessLevel = "member"
    job_title: str | None = Field(default=None, max_length=120)


class UserUpdate(BaseModel):
    access_level: AccessLevel | None = None
    job_title: str | None = Field(default=None, max_length=120)
    active: bool | None = None
    display_name: str | None = Field(default=None, min_length=2, max_length=120)


class PasswordReset(BaseModel):
    password: str = Field(min_length=10, max_length=128)


class OrgUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=120)
    default_governance_mode: Literal["direct", "approval", "consent", "holacracy"] | None = None


AVATAR_COLORS = ["#C2512D", "#1F5C4A", "#8A5A00", "#2F4B7C", "#7A3E65", "#3E6B5C", "#9C4A1A", "#4A4E8A"]


@router.get("/users", summary="All memberships of the organization")
async def list_users(ctx: CtxDep, db: DbDep) -> list[dict]:
    require_admin(ctx)
    return await q(
        db,
        """SELECT u.id, u.email, u.display_name AS name, m.access_level, m.job_title, m.active, m.created_at
           FROM memberships m JOIN users u ON u.id = m.user_id WHERE m.organization_id = :o ORDER BY u.display_name""",
        o=ctx.org_id,
    )


@router.post("/users", summary="Create a user account inside this organization", responses={409: {"description": "Email already registered"}})
async def create_user(body: UserCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    if not PASSWORD_RULE.match(body.password):
        raise err(422, "PASSWORD_WEAK", "Use at least 10 characters including a letter and a digit.", "password")
    existing = await q1(db, "SELECT id FROM users WHERE lower(email) = lower(:e)", e=str(body.email))
    if existing:
        raise err(409, "USER_EXISTS", "An account with this email already exists.", "email")
    row = await q1(
        db,
        "INSERT INTO users (email, password_hash, display_name) VALUES (lower(:e), :p, :n) RETURNING id",
        e=str(body.email), p=hash_password(body.password), n=body.display_name,
    )
    count = await q1(db, "SELECT COUNT(*) AS n FROM memberships WHERE organization_id = :o", o=ctx.org_id)
    await x(
        db,
        """INSERT INTO memberships (organization_id, user_id, access_level, job_title, avatar_color, created_by, updated_by)
           VALUES (:o, :u, :a, :j, :c, :by, :by)""",
        o=ctx.org_id, u=row["id"], a=body.access_level, j=body.job_title, c=AVATAR_COLORS[count["n"] % len(AVATAR_COLORS)], by=ctx.user_id,
    )
    await audit(db, ctx, "user.created", "user", row["id"], f"{body.display_name} ({body.access_level})")
    await db.commit()
    return {"id": row["id"]}


@router.patch("/users/{user_id}", summary="Change access level or status of a member", responses={409: {"description": "Last administrator"}})
async def update_user(user_id: UUID, body: UserUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    m = await q1(db, "SELECT access_level, active FROM memberships WHERE organization_id = :o AND user_id = :u", o=ctx.org_id, u=user_id)
    if m is None:
        raise err(404, "USER_NOT_FOUND", "Member not found.")
    data = body.model_dump(exclude_unset=True)
    losing_admin = (data.get("access_level") not in (None, "org_admin") and m["access_level"] == "org_admin") or (data.get("active") is False and m["access_level"] == "org_admin")
    if losing_admin:
        admins = await q1(db, "SELECT COUNT(*) AS n FROM memberships WHERE organization_id = :o AND access_level = 'org_admin' AND active", o=ctx.org_id)
        if admins["n"] <= 1:
            raise err(409, "LAST_ADMIN", "The organization needs at least one active administrator.")
    if "display_name" in data:
        await x(db, "UPDATE users SET display_name = :n, updated_at = NOW() WHERE id = :u", n=data.pop("display_name"), u=user_id)
    sets, params = set_clause(data, {"access_level", "job_title", "active"})
    if sets:
        await x(db, f"UPDATE memberships SET {sets}, updated_at = NOW(), updated_by = :by WHERE organization_id = :o AND user_id = :u", o=ctx.org_id, u=user_id, by=ctx.user_id, **params)  # noqa: S608
    await audit(db, ctx, "user.updated", "user", user_id, "Member updated", body.model_dump(exclude_unset=True, mode="json"))
    await db.commit()
    return {"ok": True}


@router.post("/users/{user_id}/password", summary="Set a new password for a member")
async def reset_password(user_id: UUID, body: PasswordReset, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    if not PASSWORD_RULE.match(body.password):
        raise err(422, "PASSWORD_WEAK", "Use at least 10 characters including a letter and a digit.", "password")
    m = await q1(db, "SELECT 1 AS ok FROM memberships WHERE organization_id = :o AND user_id = :u", o=ctx.org_id, u=user_id)
    if m is None:
        raise err(404, "USER_NOT_FOUND", "Member not found.")
    await x(db, "UPDATE users SET password_hash = :p, updated_at = NOW() WHERE id = :u", p=hash_password(body.password), u=user_id)
    await audit(db, ctx, "user.password_reset", "user", user_id, "Password reset by administrator")
    await db.commit()
    return {"ok": True}


@router.get("/org", summary="Organization settings")
async def get_org(ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    org = await q1(db, "SELECT id, name, slug, default_governance_mode, is_demo FROM organizations WHERE id = :o", o=ctx.org_id)
    return org or {}


@router.patch("/org", summary="Update organization settings (default governance workflow)")
async def update_org(body: OrgUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    sets, params = set_clause(body.model_dump(exclude_unset=True), {"name", "default_governance_mode"})
    if sets:
        await x(db, f"UPDATE organizations SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :o", o=ctx.org_id, u=ctx.user_id, **params)  # noqa: S608
        await audit(db, ctx, "org.updated", "organization", ctx.org_id, "Organization settings changed", body.model_dump(exclude_unset=True))
    await db.commit()
    return {"ok": True}


@router.get("/audit", summary="Audit log")
async def audit_log(ctx: CtxDep, db: DbDep, limit: int = Query(default=100, ge=1, le=500), action: str | None = Query(default=None, max_length=60)) -> list[dict]:
    require_admin(ctx)
    where = "a.organization_id = :o" + (" AND a.action LIKE :act" if action else "")
    params: dict[str, Any] = {"o": ctx.org_id}
    if action:
        params["act"] = f"{action}%"
    return await q(
        db,
        f"""SELECT a.id, a.action, a.entity_type, a.entity_id, a.summary, a.created_at, u.display_name AS actor_name
            FROM audit_events a LEFT JOIN users u ON u.id = a.actor_id WHERE {where} ORDER BY a.created_at DESC LIMIT {int(limit)}""",  # noqa: S608 - constants only
        **params,
    )


EXPORT_TABLES = [
    "circles", "roles", "role_assignments", "governance_items", "governance_proposals", "proposal_comments", "governance_decisions",
    "governance_changes", "tensions", "meetings", "meeting_participants", "agenda_items", "projects", "project_milestones", "tasks",
    "task_comments", "objectives", "key_results", "metrics", "metric_readings", "audit_events",
]


@router.get("/export", summary="Full JSON export of the organization's data")
async def export_org(ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    out: dict[str, Any] = {
        "organization": await q1(db, "SELECT id, name, slug, default_governance_mode, is_demo FROM organizations WHERE id = :o", o=ctx.org_id),
        "members": await q(db, "SELECT u.id, u.email, u.display_name, m.access_level, m.job_title, m.skills FROM memberships m JOIN users u ON u.id = m.user_id WHERE m.organization_id = :o", o=ctx.org_id),
    }
    for table in EXPORT_TABLES:
        out[table] = await q(db, f"SELECT * FROM {table} WHERE organization_id = :o", o=ctx.org_id)  # noqa: S608 - fixed table list
    await audit(db, ctx, "org.exported", "organization", ctx.org_id, "Full data export")
    await db.commit()
    return out


@router.post("/reset-demo", summary="Reset the demonstration organization to its original sample data", responses={409: {"description": "Not a demo organization"}})
async def reset_demo_data(ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    org = await q1(db, "SELECT is_demo FROM organizations WHERE id = :o", o=ctx.org_id)
    if not org or not org["is_demo"]:
        raise err(409, "NOT_DEMO", "Only the demonstration organization can be reset.")
    await reset_demo(db, ctx.org_id)
    await db.commit()
    return {"ok": True}
