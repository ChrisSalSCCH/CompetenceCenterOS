"""Turn a won opportunity into a customer project - or enrich an existing project - without losing links.

The preview shows exactly what would happen. The conversion runs in one transaction on a locked
opportunity row, and a unique index on projects.source_opportunity_id makes a second project impossible.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from routes.portfolio import _can_edit as _can_edit_project
from routes.work import _project
from services.commercial import CONVERT_FIELDS, conversion_plan
from services.commercial_db import check_member, get_opp, require_edit_opp
from services.ctx import CtxDep, require_circle
from services.dbx import DbDep, err, q, q1, x
from services.events import audit, notify

router = APIRouter(prefix="/api/commercial", tags=["conversion"])

NOT_WON = "Only a won opportunity can be turned into a project."


class ConvertBody(BaseModel):
    project_id: UUID | None = None
    circle_id: UUID | None = None
    manager_id: UUID | None = None
    name: str | None = Field(default=None, min_length=3, max_length=200)
    overwrite_fields: list[str] = Field(default_factory=list, max_length=len(CONVERT_FIELDS))


async def _source_version(db, opp_id: UUID) -> dict | None:
    return await q1(
        db,
        """SELECT v.*, p.number AS proposal_number, p.status AS proposal_status FROM proposals p JOIN proposal_versions v ON v.proposal_id = p.id
           WHERE p.opportunity_id = :o AND p.deleted_at IS NULL AND v.status IN ('approved','submitted')
           ORDER BY (p.status = 'accepted') DESC, v.submitted_at DESC NULLS LAST, v.created_at DESC LIMIT 1""",
        o=opp_id,
    )


async def _packages(db, version_id: UUID | None) -> list[dict]:
    if version_id is None:
        return []
    return await q(
        db,
        """SELECT code, title, description, effort_days, start_date, end_date, milestone_title, milestone_due, position
           FROM proposal_work_packages WHERE version_id = :v ORDER BY position, code""",
        v=version_id,
    )


def _earliest(values: list[date | None]) -> date | None:
    real = [v for v in values if v]
    return min(real) if real else None


def _latest(values: list[date | None]) -> date | None:
    real = [v for v in values if v]
    return max(real) if real else None


async def _source_fields(db, opp: dict, version: dict | None, packages: list[dict]) -> dict[str, Any]:
    effort = version["effort_days"] if version and version["effort_days"] else opp["effort_days"]
    budget = version["price_total"] if version and version["price_total"] else opp["value_amount"]
    return {
        "name": opp["title"],
        "description": opp["description"],
        "category": opp["category"],
        "start_date": opp["expected_start"] or _earliest([p["start_date"] for p in packages]),
        "due_date": opp["expected_end"] or _latest([p["end_date"] for p in packages]),
        "effort_days": effort,
        "budget_total": budget,
        "classification": "customer",
    }


async def _existing_fields(db, project: dict) -> dict[str, Any]:
    fin = await q1(db, "SELECT budget_total FROM project_finance WHERE project_id = :p", p=project["id"])
    return {**{k: project.get(k) for k in CONVERT_FIELDS if k != "budget_total"}, "budget_total": fin["budget_total"] if fin else None}


async def _counts(db, opp: dict, packages: list[dict]) -> dict[str, int]:
    async def count(sql: str) -> int:
        row = await q1(db, sql, i=opp["id"])
        return int(row["n"]) if row else 0

    return {
        "work_packages": len(packages),
        "milestones": sum(1 for p in packages if p["milestone_title"]),
        "catalog_entries": await count("SELECT COUNT(*) AS n FROM opportunity_catalog_links WHERE opportunity_id = :i"),
        "contacts": await count("SELECT COUNT(*) AS n FROM opportunity_contacts WHERE opportunity_id = :i"),
        "team": await count("SELECT COUNT(*) AS n FROM opportunity_team WHERE opportunity_id = :i"),
        "contracts": await count("SELECT COUNT(*) AS n FROM contracts WHERE opportunity_id = :i AND deleted_at IS NULL"),
        "role_scopes": await count("SELECT COUNT(*) AS n FROM crm_role_scopes WHERE opportunity_id = :i"),
    }


@router.get("/opportunities/{opp_id}/convert-preview", summary="Preview what a conversion into a (new or existing) project would do", responses={404: {"description": "Opportunity or project not found"}})
async def convert_preview(opp_id: UUID, ctx: CtxDep, db: DbDep, project_id: UUID | None = Query(default=None)) -> dict:
    opp = await get_opp(db, ctx, opp_id)
    version = await _source_version(db, opp_id)
    packages = await _packages(db, version["id"] if version else None)
    source = await _source_fields(db, opp, version, packages)
    existing = None
    existing_fields = None
    if project_id:
        existing = await _project(db, ctx, project_id)
        existing_fields = await _existing_fields(db, existing)
    warnings: list[str] = []
    if version is None:
        warnings.append("no_approved_proposal")
    if not opp["circle_id"] and existing is None:
        warnings.append("circle_required")
    if existing and existing["source_opportunity_id"] not in (None, opp_id):
        warnings.append("project_has_other_source")
    blocked = None
    if opp["project_id"]:
        blocked = "ALREADY_CONVERTED"
    elif opp["stage"] != "won":
        blocked = "OPPORTUNITY_NOT_WON"
    return {
        "opportunity": {"id": opp["id"], "number": opp["number"], "title": opp["title"], "stage": opp["stage"], "circle_id": opp["circle_id"], "project_id": opp["project_id"]},
        "source_proposal": {"number": version["proposal_number"], "version_no": version["version_no"], "currency": version["currency"], "status": version["proposal_status"]} if version else None,
        "mode": "existing" if existing else "new",
        "existing_project": {"id": existing["id"], "name": existing["name"]} if existing else None,
        "fields": conversion_plan(source, existing_fields),
        "will_link": await _counts(db, opp, packages),
        "warnings": warnings,
        "blocked_reason": blocked,
        "can_convert": blocked is None,
    }


async def _copy_links(db, ctx, opp: dict, pid: UUID, version: dict | None, packages: list[dict], has_packages: bool) -> dict[str, int]:
    """Hand over everything that is not a plain field. Existing links are never duplicated."""
    done = {"work_packages": 0, "milestones": 0}
    if not has_packages:
        for pos, wp in enumerate(packages, start=1):
            await x(
                db,
                """INSERT INTO project_work_packages (organization_id, project_id, code, title, description, status, start_date, end_date, position, created_by, updated_by)
                   VALUES (:o, :p, :c, :t, :d, 'planned', :sd, :ed, :pos, :u, :u)""",
                o=ctx.org_id, p=pid, c=wp["code"], t=wp["title"], d=wp["description"], sd=wp["start_date"], ed=wp["end_date"], pos=pos, u=ctx.user_id,
            )
            done["work_packages"] += 1
            if wp["milestone_title"]:
                await x(db, "INSERT INTO project_milestones (organization_id, project_id, title, due_date) VALUES (:o, :p, :t, :d)", o=ctx.org_id, p=pid, t=wp["milestone_title"], d=wp["milestone_due"])
                done["milestones"] += 1
    params = {"o": ctx.org_id, "p": pid, "i": opp["id"]}
    await x(db, "INSERT INTO project_orgs (organization_id, project_id, crm_org_id, relation) VALUES (:o, :p, :c, 'customer') ON CONFLICT DO NOTHING", c=opp["crm_org_id"], o=ctx.org_id, p=pid)
    await x(db, "INSERT INTO project_catalog_links (organization_id, project_id, entry_id) SELECT CAST(:o AS uuid), CAST(:p AS uuid), entry_id FROM opportunity_catalog_links WHERE opportunity_id = :i ON CONFLICT DO NOTHING", **params)
    await x(db, "INSERT INTO project_contacts (organization_id, project_id, contact_id, contact_role) SELECT CAST(:o AS uuid), CAST(:p AS uuid), contact_id, contact_role FROM opportunity_contacts WHERE opportunity_id = :i ON CONFLICT DO NOTHING", **params)
    await x(db, "INSERT INTO project_people (organization_id, project_id, user_id) SELECT CAST(:o AS uuid), CAST(:p AS uuid), user_id FROM opportunity_team WHERE opportunity_id = :i ON CONFLICT DO NOTHING", **params)
    await x(db, "INSERT INTO contract_projects (organization_id, contract_id, project_id) SELECT CAST(:o AS uuid), id, CAST(:p AS uuid) FROM contracts WHERE opportunity_id = :i AND deleted_at IS NULL ON CONFLICT DO NOTHING", **params)
    await x(
        db,
        """INSERT INTO crm_role_scopes (organization_id, role_assignment_id, scope_type, project_id, created_by)
           SELECT CAST(:o AS uuid), role_assignment_id, 'project', CAST(:p AS uuid), CAST(:u AS uuid) FROM crm_role_scopes WHERE opportunity_id = :i ON CONFLICT DO NOTHING""",
        u=ctx.user_id, **params,
    )
    return done


async def _write_budget(db, ctx, pid: UUID, version: dict | None, budget: Any, currency: str) -> None:
    if budget is None:
        return
    await x(
        db,
        """INSERT INTO project_finance (organization_id, project_id, budget_total, revenue_expected, currency, created_by, updated_by)
           VALUES (:o, :p, :b, :b, :c, :u, :u)
           ON CONFLICT (project_id) DO UPDATE SET budget_total = EXCLUDED.budget_total, updated_at = NOW(), updated_by = EXCLUDED.updated_by""",
        o=ctx.org_id, p=pid, b=Decimal(str(budget)), c=currency, u=ctx.user_id,
    )


@router.post("/opportunities/{opp_id}/convert", summary="Create a customer project from a won opportunity, or fill an existing project", responses={409: {"description": "Already converted or not won"}, 422: {"description": "Circle or unknown field"}, 403: {"description": "Not allowed"}})
async def convert(opp_id: UUID, body: ConvertBody, ctx: CtxDep, db: DbDep) -> dict:
    await require_edit_opp(db, ctx, opp_id)
    unknown = set(body.overwrite_fields) - set(CONVERT_FIELDS)
    if unknown:
        raise err(422, "UNKNOWN_FIELD", f"Unknown field to overwrite: {sorted(unknown)[0]}.", "overwrite_fields")
    # Lock the row: a concurrent second conversion waits here and then sees project_id.
    locked = await q1(db, "SELECT * FROM opportunities WHERE id = :i AND organization_id = :o AND deleted_at IS NULL FOR UPDATE", i=opp_id, o=ctx.org_id)
    if locked is None:
        raise err(404, "OPPORTUNITY_NOT_FOUND", "Opportunity not found.")
    opp = locked
    if opp["project_id"]:
        raise err(409, "ALREADY_CONVERTED", "This opportunity was already turned into a project.")
    if opp["stage"] != "won":
        raise err(409, "OPPORTUNITY_NOT_WON", NOT_WON)
    version = await _source_version(db, opp_id)
    packages = await _packages(db, version["id"] if version else None)
    source = await _source_fields(db, opp, version, packages)
    currency = version["currency"] if version else opp["currency"]
    created = body.project_id is None
    if created:
        circle_id = opp["circle_id"] or body.circle_id
        if circle_id is None:
            raise err(422, "CIRCLE_REQUIRED", "Choose the circle that will own the project.", "circle_id")
        await require_circle(db, ctx, circle_id)
        manager = body.manager_id or opp["owner_user_id"]
        await check_member(db, ctx, manager, "manager_id")
        row = await q1(
            db,
            """INSERT INTO projects (organization_id, circle_id, name, description, status, priority, start_date, due_date, classification, category, phase, manager_id,
                                    effort_days, source_opportunity_id, created_by, updated_by)
               VALUES (:o, :c, :n, :d, 'planned', 'medium', :sd, :dd, 'customer', :ca, 'running', :m, :ef, :op, :u, :u) RETURNING id""",
            o=ctx.org_id, c=circle_id, n=(body.name or source["name"]).strip(), d=source["description"], sd=source["start_date"], dd=source["due_date"], ca=source["category"],
            m=manager, ef=source["effort_days"], op=opp_id, u=ctx.user_id,
        )
        pid = row["id"]
        project_name = (body.name or source["name"]).strip()
        applied = [r["field"] for r in conversion_plan(source, None)]
        await _write_budget(db, ctx, pid, version, source["budget_total"], currency)
        has_packages = False
    else:
        project = await _project(db, ctx, body.project_id)
        if not await _can_edit_project(db, ctx, project):
            raise err(403, "PROJECT_FORBIDDEN", "Only administrators, the project manager or the project team can change this project.")
        if project["source_opportunity_id"] not in (None, opp_id):
            raise err(409, "PROJECT_HAS_OTHER_SOURCE", "This project already originates from another opportunity.")
        pid, project_name = project["id"], project["name"]
        plan = conversion_plan(source, await _existing_fields(db, project))
        applied = [r["field"] for r in plan if r["action"] in ("fill", "set") or (r["action"] == "conflict" and r["field"] in body.overwrite_fields)]
        columns = [f for f in applied if f != "budget_total"]
        if columns:
            sets = ", ".join(f"{c} = :{c}" for c in columns)
            await x(db, f"UPDATE projects SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=pid, u=ctx.user_id, **{c: source[c] for c in columns})  # noqa: S608 - columns come from CONVERT_FIELDS
        if "budget_total" in applied:
            await _write_budget(db, ctx, pid, version, source["budget_total"], currency)
        await x(db, "UPDATE projects SET source_opportunity_id = :op WHERE id = :id AND source_opportunity_id IS NULL", op=opp_id, id=pid)
        has_packages = bool(await q1(db, "SELECT 1 AS ok FROM project_work_packages WHERE project_id = :p AND deleted_at IS NULL LIMIT 1", p=pid))
    handed = await _copy_links(db, ctx, opp, pid, version, packages, has_packages)
    await x(db, "UPDATE opportunities SET project_id = :p, converted_at = NOW(), updated_at = NOW(), updated_by = :u WHERE id = :i", p=pid, u=ctx.user_id, i=opp_id)
    await audit(db, ctx, "opportunity.converted", "opportunity", opp_id, f"{opp['number']} -> project {project_name}", {"project_id": str(pid), "created": created, "fields": applied, **handed})
    await audit(db, ctx, "project.created_from_opportunity" if created else "project.enriched_from_opportunity", "project", pid, f"{project_name} <- {opp['number']}", {"opportunity_id": str(opp_id), "fields": applied})
    if opp["owner_user_id"]:
        await notify(db, ctx.org_id, [opp["owner_user_id"]], "task", f"{opp['number']} is now project {project_name}", opp["title"], f"/projects/{pid}", exclude=ctx.user_id)
    await db.commit()
    return {"ok": True, "project_id": pid, "created": created, "applied_fields": applied, "skipped_work_packages": bool(has_packages and packages), **handed}
