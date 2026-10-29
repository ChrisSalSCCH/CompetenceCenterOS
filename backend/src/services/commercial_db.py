"""Database helpers shared by the commercial routers: numbering, access checks, decision rules."""

from __future__ import annotations

from datetime import date
from typing import Any
from uuid import UUID

from services.commercial import format_number, resolve_authority
from services.ctx import Ctx
from services.dbx import err, q, q1

OPP_NOT_FOUND = "Opportunity not found."
MONEY_FIELDS = ("value_amount", "weighted_value", "price_total", "cost_total", "margin", "margin_pct", "amount")


async def next_number(db, org_id: UUID, kind: str) -> str:
    """Next number of the year for OPP / ANG / NDA / CON; one atomic upsert, so concurrent requests never collide."""
    year = date.today().year
    row = await q1(
        db,
        """INSERT INTO commercial_counters (organization_id, kind, year, last_value) VALUES (:o, :k, :y, 1)
           ON CONFLICT (organization_id, kind, year) DO UPDATE SET last_value = commercial_counters.last_value + 1 RETURNING last_value""",
        o=org_id, k=kind, y=year,
    )
    return format_number(kind, year, int(row["last_value"])) if row else format_number(kind, year, 1)


def money_hidden(ctx: Ctx) -> bool:
    """Observers never see monetary values of the commercial process."""
    return ctx.level == "observer"


def strip_money(row: dict[str, Any], ctx: Ctx) -> dict[str, Any]:
    if money_hidden(ctx):
        for key in MONEY_FIELDS:
            if key in row:
                row[key] = None
    return row


async def held_role_ids(db, ctx: Ctx) -> set[UUID]:
    rows = await q(
        db,
        "SELECT role_id FROM role_assignments WHERE user_id = :u AND organization_id = :o AND deleted_at IS NULL",
        u=ctx.user_id, o=ctx.org_id,
    )
    return {r["role_id"] for r in rows}


async def load_rules(db, ctx: Ctx, decision_type: str) -> list[dict]:
    return await q(
        db,
        """SELECT dr.*, r.name AS role_name, c.name AS circle_name,
                  (SELECT COUNT(*) FROM role_assignments ra WHERE ra.role_id = dr.role_id AND ra.deleted_at IS NULL) AS holders
           FROM decision_rules dr JOIN roles r ON r.id = dr.role_id AND r.deleted_at IS NULL LEFT JOIN circles c ON c.id = dr.circle_id
           WHERE dr.organization_id = :o AND dr.decision_type = :t AND dr.deleted_at IS NULL AND dr.active
           ORDER BY dr.step_order, dr.label""",
        o=ctx.org_id, t=decision_type,
    )


async def get_opp(db, ctx: Ctx, opp_id: UUID) -> dict:
    row = await q1(db, "SELECT * FROM opportunities WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=opp_id, o=ctx.org_id)
    if row is None:
        raise err(404, "OPPORTUNITY_NOT_FOUND", OPP_NOT_FOUND)
    return row


async def on_opp_team(db, ctx: Ctx, opp: dict) -> bool:
    """Owner, creator, team member, or a role holder scoped to the opportunity or its customer."""
    if ctx.user_id in (opp.get("owner_user_id"), opp.get("created_by")):
        return True
    row = await q1(
        db,
        """SELECT 1 AS ok FROM opportunity_team WHERE opportunity_id = :i AND user_id = :u
           UNION ALL
           SELECT 1 FROM crm_role_scopes s JOIN role_assignments ra ON ra.id = s.role_assignment_id AND ra.deleted_at IS NULL
            WHERE ra.user_id = :u AND (s.opportunity_id = :i OR s.crm_org_id = :c) LIMIT 1""",
        i=opp["id"], u=ctx.user_id, c=opp["crm_org_id"],
    )
    return row is not None


async def can_edit_opp(db, ctx: Ctx, opp: dict) -> bool:
    if ctx.level == "observer":
        return False
    return ctx.level == "org_admin" or await on_opp_team(db, ctx, opp)


async def require_edit_opp(db, ctx: Ctx, opp_id: UUID) -> dict:
    if ctx.level == "observer":
        raise err(403, "READ_ONLY", "Observers have read-only access.")
    opp = await get_opp(db, ctx, opp_id)
    if not await can_edit_opp(db, ctx, opp):
        raise err(403, "OPPORTUNITY_FORBIDDEN", "Only administrators, the owner or the opportunity team can change this opportunity.")
    return opp


async def can_see_cost(db, ctx: Ctx, opp: dict) -> bool:
    """Cost and margin are visible to administrators, the opportunity team and holders of decision roles."""
    if ctx.level == "observer":
        return False
    if ctx.level == "org_admin" or await on_opp_team(db, ctx, opp):
        return True
    held = await held_role_ids(db, ctx)
    if not held:
        return False
    row = await q1(
        db,
        "SELECT 1 AS ok FROM decision_rules WHERE organization_id = :o AND deleted_at IS NULL AND active AND role_id = ANY(:ids) LIMIT 1",
        o=ctx.org_id, ids=list(held),
    )
    return row is not None


async def check_authority(
    db, ctx: Ctx, decision_type: str, *, value: Any, category: str | None, risk: str | None, circle_id: Any, override_note: str | None
) -> dict[str, Any]:
    """Who may decide: a holder of a matching rule's role; otherwise an administrator with a recorded note."""
    rules = await load_rules(db, ctx, decision_type)
    auth = resolve_authority(rules, await held_role_ids(db, ctx), value=value, category=category, risk=risk, circle_id=circle_id)
    override = False
    if not auth["authorized"]:
        if ctx.level != "org_admin":
            raise err(403, "AUTHORITY_REQUIRED", "Only the holder of a decision role (or an administrator with a note) can do this.")
        if not (override_note or "").strip():
            raise err(422, "OVERRIDE_NOTE_REQUIRED", "Without a matching decision role, an administrator must record why this is done.", "override_note")
        override = True
    rule_id = auth["matching"][0]["id"] if auth["matching"] and auth["authorized"] else None
    return {"override": override, "unclear": auth["unclear"], "rule_id": rule_id}


async def has_cost_access(db, ctx: Ctx) -> bool:
    """Cost and margin in aggregated reports: administrators and holders of any decision role."""
    if ctx.level == "observer":
        return False
    if ctx.level == "org_admin":
        return True
    held = await held_role_ids(db, ctx)
    if not held:
        return False
    row = await q1(
        db,
        "SELECT 1 AS ok FROM decision_rules WHERE organization_id = :o AND deleted_at IS NULL AND active AND role_id = ANY(:ids) LIMIT 1",
        o=ctx.org_id, ids=list(held),
    )
    return row is not None


async def check_member(db, ctx: Ctx, user_id: UUID | None, field: str) -> None:
    if user_id is None:
        return
    row = await q1(db, "SELECT 1 AS ok FROM memberships WHERE user_id = :u AND organization_id = :o AND active", u=user_id, o=ctx.org_id)
    if row is None:
        raise err(404, "PERSON_NOT_FOUND", "Person is not a member of this organization.", field)


async def check_crm_org(db, ctx: Ctx, org_id: UUID, field: str = "crm_org_id") -> dict:
    row = await q1(db, "SELECT id, name FROM crm_organizations WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=org_id, o=ctx.org_id)
    if row is None:
        raise err(404, "CRM_ORG_NOT_FOUND", "Organization not found.", field)
    return row
