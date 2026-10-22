"""Session bootstrap (who am I, which org, what may I govern) and demo login."""

from __future__ import annotations

import os
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Request
from limiter import limiter
from pydantic import BaseModel, EmailStr, Field
from services.auth import issue_access_token, issue_refresh_token, public_endpoint
from services.ctx import CtxDep
from services.dbx import DbDep, err, q, q1, x

router = APIRouter(prefix="/api", tags=["session"])

DEMO_DOMAIN = "@demo.circleos.app"


class DemoLoginRequest(BaseModel):
    email: EmailStr


class ProfileUpdate(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=120)
    job_title: str | None = Field(default=None, max_length=120)
    skills: list[Annotated[str, Field(max_length=40)]] | None = Field(default=None, max_length=30)
    availability: str | None = Field(default=None, max_length=120)
    notification_prefs: dict[str, bool] | None = None


def _demo_enabled() -> bool:
    return os.getenv("DEMO_LOGIN_ENABLED", "true").lower() == "true"


@router.get(
    "/auth/demo-users",
    summary="List demo personas available for one-click login",
    **public_endpoint("Lists demo personas of the clearly labelled demonstration organization"),
)
async def demo_users(db: DbDep) -> dict:
    if not _demo_enabled():
        return {"enabled": False, "users": []}
    rows = await q(
        db,
        """SELECT u.email, u.display_name, m.job_title, m.access_level, m.avatar_color
           FROM memberships m JOIN users u ON u.id = m.user_id
           JOIN organizations o ON o.id = m.organization_id AND o.is_demo AND o.deleted_at IS NULL
           WHERE m.active AND u.email LIKE :pat ORDER BY m.access_level, u.display_name""",
        pat=f"%{DEMO_DOMAIN}",
    )
    return {"enabled": True, "users": rows}


@router.post(
    "/auth/demo-login",
    summary="Sign in as a demo persona",
    responses={403: {"description": "Demo login disabled or not a demo account"}},
    **public_endpoint("One-click access to the demonstration organization only"),
)
@limiter.limit("30/minute")
async def demo_login(request: Request, body: DemoLoginRequest, db: DbDep) -> dict:
    if not _demo_enabled():
        raise err(403, "DEMO_DISABLED", "Demo login is disabled.")
    row = await q1(
        db,
        """SELECT u.id FROM users u
           JOIN memberships m ON m.user_id = u.id AND m.active
           JOIN organizations o ON o.id = m.organization_id AND o.is_demo AND o.deleted_at IS NULL
           WHERE lower(u.email) = lower(:e) AND u.email LIKE :pat""",
        e=str(body.email),
        pat=f"%{DEMO_DOMAIN}",
    )
    if row is None:
        raise err(403, "NOT_A_DEMO_ACCOUNT", "This account is not part of the demonstration data.")
    sub = str(row["id"])
    return {
        "access_token": issue_access_token(sub),
        "refresh_token": issue_refresh_token(sub),
        "token_type": "bearer",  # noqa: S105
    }


@router.get("/session", summary="Current user, organization, roles and permissions")
async def session(ctx: CtxDep, db: DbDep) -> dict:
    org = await q1(db, "SELECT id, name, slug, is_demo, default_governance_mode FROM organizations WHERE id = :o", o=ctx.org_id)
    me = await q1(
        db,
        """SELECT m.job_title, m.skills, m.availability, m.avatar_color, m.notification_prefs
           FROM memberships m WHERE m.user_id = :u AND m.organization_id = :o""",
        u=ctx.user_id, o=ctx.org_id,
    )
    roles = await q(
        db,
        """SELECT r.id AS role_id, r.name AS role_name, c.id AS circle_id, c.name AS circle_name, r.can_govern, ra.focus
           FROM role_assignments ra JOIN roles r ON r.id = ra.role_id AND r.deleted_at IS NULL
           JOIN circles c ON c.id = r.circle_id AND c.deleted_at IS NULL
           WHERE ra.user_id = :u AND ra.organization_id = :o AND ra.deleted_at IS NULL ORDER BY c.name, r.name""",
        u=ctx.user_id, o=ctx.org_id,
    )
    if ctx.level == "org_admin":
        gov = await q(db, "SELECT id FROM circles WHERE organization_id = :o AND deleted_at IS NULL", o=ctx.org_id)
    elif ctx.level == "observer":
        gov = []
    else:
        gov = await q(
            db,
            """WITH RECURSIVE g AS (
                   SELECT DISTINCT r.circle_id AS id FROM role_assignments ra
                   JOIN roles r ON r.id = ra.role_id AND r.deleted_at IS NULL AND r.can_govern
                   WHERE ra.user_id = :u AND ra.organization_id = :o AND ra.deleted_at IS NULL
                 UNION
                   SELECT c.id FROM circles c JOIN g ON c.parent_id = g.id WHERE c.deleted_at IS NULL
               ) SELECT id FROM g""",
            u=ctx.user_id, o=ctx.org_id,
        )
    unread = await q1(db, "SELECT COUNT(*) AS n FROM notifications WHERE user_id = :u AND organization_id = :o AND read_at IS NULL", u=ctx.user_id, o=ctx.org_id)
    ai = await q1(db, "SELECT enabled, base_url, model FROM ai_provider_configs WHERE organization_id = :o", o=ctx.org_id)
    return {
        "user": {"id": ctx.user_id, "name": ctx.name, "email": ctx.email, **(me or {})},
        "organization": org,
        "access_level": ctx.level,
        "roles": roles,
        "governable_circle_ids": [g["id"] for g in gov],
        "unread_notifications": unread["n"] if unread else 0,
        "ai_enabled": bool(ai and ai["enabled"] and ai["base_url"] and ai["model"]),
    }


@router.patch("/me/profile", summary="Update own profile and notification preferences")
async def update_profile(body: ProfileUpdate, ctx: CtxDep, db: DbDep) -> dict:
    data = body.model_dump(exclude_unset=True)
    if "display_name" in data and data["display_name"]:
        await x(db, "UPDATE users SET display_name = :n, updated_at = NOW() WHERE id = :u", n=data["display_name"], u=ctx.user_id)
    for col in ("job_title", "skills", "availability"):
        if col in data:
            await x(db, f"UPDATE memberships SET {col} = :v, updated_at = NOW() WHERE user_id = :u AND organization_id = :o", v=data[col] if col != "skills" else (data[col] or []), u=ctx.user_id, o=ctx.org_id)
    if "notification_prefs" in data and data["notification_prefs"] is not None:
        import json

        await x(
            db,
            "UPDATE memberships SET notification_prefs = CAST(:v AS jsonb), updated_at = NOW() WHERE user_id = :u AND organization_id = :o",
            v=json.dumps(data["notification_prefs"]), u=ctx.user_id, o=ctx.org_id,
        )
    await db.commit()
    return {"ok": True}


@router.get("/notifications", summary="List own notifications")
async def list_notifications(ctx: CtxDep, db: DbDep) -> list[dict]:
    return await q(
        db,
        """SELECT id, kind, title, body, link, read_at, created_at FROM notifications
           WHERE user_id = :u AND organization_id = :o ORDER BY created_at DESC LIMIT 60""",
        u=ctx.user_id, o=ctx.org_id,
    )


@router.post("/notifications/read-all", summary="Mark all own notifications as read")
async def read_all(ctx: CtxDep, db: DbDep) -> dict:
    await x(db, "UPDATE notifications SET read_at = NOW() WHERE user_id = :u AND organization_id = :o AND read_at IS NULL", u=ctx.user_id, o=ctx.org_id)
    await db.commit()
    return {"ok": True}


@router.post("/notifications/{notification_id}/read", summary="Mark one notification as read")
async def read_one(notification_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    await x(db, "UPDATE notifications SET read_at = NOW() WHERE id = :id AND user_id = :u AND organization_id = :o", id=notification_id, u=ctx.user_id, o=ctx.org_id)
    await db.commit()
    return {"ok": True}
