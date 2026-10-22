"""Audit events and in-app notifications."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from services.ctx import Ctx
from services.dbx import jb, q1, x


async def audit(
    db,
    ctx: Ctx,
    action: str,
    entity_type: str,
    entity_id: UUID | str | None,
    summary: str,
    data: dict[str, Any] | None = None,
) -> None:
    await x(
        db,
        """INSERT INTO audit_events (organization_id, actor_id, action, entity_type, entity_id, summary, data)
           VALUES (:org, :actor, :action, :et, :eid, :summary, CAST(:data AS jsonb))""",
        org=ctx.org_id,
        actor=ctx.user_id,
        action=action,
        et=entity_type,
        eid=entity_id,
        summary=summary[:400],
        data=jb(data) if data is not None else None,
    )


async def notify(
    db,
    org_id: UUID,
    user_ids: list[UUID],
    kind: str,
    title: str,
    body: str = "",
    link: str | None = None,
    exclude: UUID | None = None,
) -> None:
    """Create a notification for each user (respecting the per-kind opt-out preference)."""
    pref_key = {
        "governance": "governance",
        "task": "tasks",
        "meeting": "meetings",
        "tension": "tensions",
    }.get(kind, "governance")
    for uid in {u for u in user_ids if u and u != exclude}:
        member = await q1(
            db,
            "SELECT notification_prefs FROM memberships WHERE organization_id = :org AND user_id = :uid AND active",
            org=org_id,
            uid=uid,
        )
        if member is None:
            continue
        prefs = member["notification_prefs"]
        if isinstance(prefs, str):
            prefs = json.loads(prefs)
        if (prefs or {}).get(pref_key) is False:
            continue
        await x(
            db,
            """INSERT INTO notifications (organization_id, user_id, kind, title, body, link)
               VALUES (:org, :uid, :kind, :title, :body, :link)""",
            org=org_id,
            uid=uid,
            kind=kind,
            title=title[:250],
            body=body,
            link=link,
        )
