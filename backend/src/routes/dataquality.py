"""Data quality checks with direct fixes, contact merging and CSV / XLSX exports.

Every export mirrors what the caller may see on screen: observers get no monetary columns, contract conditions
need signing rights, and cost or margin need cost access. Each export is written to the audit log.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Literal
from uuid import UUID

from fastapi import APIRouter, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field
from routes.agreements import _require_edit_contract, _signature_role
from routes.portfolio import _can_edit as _can_edit_project
from routes.work import _project
from services.commercial import contract_state, effective_probability, is_overdue, nda_coverage, weighted_value
from services.commercial_db import check_member, has_cost_access, require_edit_opp
from services.ctx import CtxDep, require_write
from services.dbx import DbDep, err, q, q1, x
from services.events import audit
from services.management import find_duplicate_contacts, make_csv, make_xlsx

router = APIRouter(prefix="/api/management", tags=["data-quality"])

PAST_DAYS = 14
EXPORTS = ("opportunities", "proposals", "contracts", "ndas", "customers", "projects", "data_quality")
XLSX_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


class FixBody(BaseModel):
    action: Literal["set_owner", "set_manager", "set_next_action", "set_close_date"]
    entity_id: UUID
    user_id: UUID | None = None
    text: str | None = Field(default=None, max_length=300)
    day: date | None = None


class MergeBody(BaseModel):
    keep_id: UUID
    merge_ids: list[UUID] = Field(min_length=1, max_length=10)


def _issue(kind: str, severity: str, entity_type: str, entity_id: Any, label: str, message: str, link: str, fix: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"id": f"{kind}:{entity_id}", "kind": kind, "severity": severity, "entity_type": entity_type, "entity_id": entity_id, "label": label, "message": message, "link": link, "fix": fix}


# ---------------------------------------------------------------- checks


async def collect_issues(db, ctx) -> list[dict[str, Any]]:  # noqa: PLR0915 - one block per check
    org = ctx.org_id
    today = date.today()
    out: list[dict[str, Any]] = []

    for r in await q(db, "SELECT id, name FROM crm_organizations WHERE organization_id = :o AND deleted_at IS NULL AND status = 'active' AND 'customer' = ANY(relation_types) AND owner_user_id IS NULL ORDER BY name", o=org):
        out.append(_issue("customer_without_owner", "warning", "crm_organization", r["id"], r["name"], "Customer has no relationship owner.", f"/crm/organizations/{r['id']}", {"action": "set_owner"}))

    contacts = await q(db, "SELECT c.id, c.first_name, c.last_name, c.email, c.phone, (SELECT COUNT(*) FROM crm_contact_orgs cc WHERE cc.contact_id = c.id) AS orgs FROM crm_contacts c WHERE c.organization_id = :o AND c.deleted_at IS NULL", o=org)
    for c in contacts:
        name = f"{c['first_name']} {c['last_name']}"
        if c["orgs"] == 0:
            out.append(_issue("contact_without_organization", "info", "crm_contact", c["id"], name, "Contact is not linked to any organization.", "/crm/contacts"))
        if not c["email"] and not c["phone"]:
            out.append(_issue("contact_without_channel", "info", "crm_contact", c["id"], name, "Contact has neither e-mail nor phone.", "/crm/contacts"))
    for group in find_duplicate_contacts(contacts):
        label = f"{group[0]['first_name']} {group[0]['last_name']}"
        out.append(_issue("duplicate_contact", "warning", "crm_contact", group[0]["id"], label, f"{len(group)} contacts share this name.", "/crm/contacts", {"action": "merge_contacts", "keep_id": group[0]["id"], "merge_ids": [g["id"] for g in group[1:]]}))

    opps = await q(
        db,
        """SELECT o.id, o.number, o.title, o.stage, o.owner_user_id, o.next_action, o.next_action_due, o.expected_close, o.value_amount, o.crm_org_id
           FROM opportunities o WHERE o.organization_id = :o AND o.deleted_at IS NULL AND o.stage IN ('lead','qualification','bid_decision','proposal','negotiation')""",
        o=org,
    )
    covered: set[UUID] = set()
    nda_rows = await q(db, "SELECT crm_org_id, status, valid_from, valid_to FROM ndas WHERE organization_id = :o AND deleted_at IS NULL", o=org)
    for n in nda_rows:
        if nda_coverage(n["status"], n["valid_from"], n["valid_to"], today) in ("active", "expiring"):
            covered.add(n["crm_org_id"])
    for o in opps:
        label, link = f"{o['number']} {o['title']}", f"/sales/opportunities/{o['id']}"
        if o["owner_user_id"] is None:
            out.append(_issue("opportunity_without_owner", "warning", "opportunity", o["id"], label, "Opportunity has no owner.", link, {"action": "set_owner"}))
        if not o["next_action"]:
            out.append(_issue("opportunity_without_next_action", "info", "opportunity", o["id"], label, "No next action is planned.", link, {"action": "set_next_action"}))
        if is_overdue(o["next_action_due"], o["stage"], today):
            out.append(_issue("opportunity_action_overdue", "warning", "opportunity", o["id"], label, "The next action is overdue.", link, {"action": "set_next_action"}))
        if is_overdue(o["expected_close"], o["stage"], today):
            out.append(_issue("opportunity_decision_overdue", "warning", "opportunity", o["id"], label, "The expected decision date has passed.", link, {"action": "set_close_date"}))
        if o["value_amount"] is None:
            out.append(_issue("opportunity_without_value", "info", "opportunity", o["id"], label, "No expected value entered.", link))
        if o["stage"] in ("proposal", "negotiation") and o["crm_org_id"] not in covered:
            out.append(_issue("opportunity_without_nda", "warning", "opportunity", o["id"], label, "No valid NDA covers this customer.", "/sales/ndas"))

    for p in await q(db, "SELECT id, name FROM projects WHERE organization_id = :o AND deleted_at IS NULL AND classification = 'customer' AND phase NOT IN ('completed','archived') AND manager_id IS NULL ORDER BY name", o=org):
        out.append(_issue("project_without_manager", "warning", "project", p["id"], p["name"], "Customer project has no project manager.", f"/projects/{p['id']}", {"action": "set_manager"}))
    for p in await q(db, "SELECT id, name FROM projects p WHERE organization_id = :o AND deleted_at IS NULL AND classification = 'customer' AND phase = 'running' AND NOT EXISTS (SELECT 1 FROM contract_projects cp WHERE cp.project_id = p.id) ORDER BY name", o=org):
        out.append(_issue("project_without_contract", "info", "project", p["id"], p["name"], "Running customer project has no contract.", f"/projects/{p['id']}"))
    for p in await q(db, "SELECT id, name FROM projects p WHERE organization_id = :o AND deleted_at IS NULL AND phase IN ('closing','completed') AND NOT EXISTS (SELECT 1 FROM project_knowledge k WHERE k.project_id = p.id AND k.content <> '') ORDER BY name", o=org):
        out.append(_issue("project_without_knowledge", "info", "project", p["id"], p["name"], "Finished project has no recorded knowledge.", f"/projects/{p['id']}?tab=knowledge"))

    for c in await q(db, "SELECT id, number, title, status, valid_from, valid_to, owner_user_id, (SELECT COUNT(*) FROM contract_projects cp WHERE cp.contract_id = c.id) AS projects FROM contracts c WHERE organization_id = :o AND deleted_at IS NULL", o=org):
        label, link = f"{c['number']} {c['title']}", f"/sales/contracts/{c['id']}"
        if c["owner_user_id"] is None:
            out.append(_issue("contract_without_owner", "warning", "contract", c["id"], label, "Contract has no owner.", link, {"action": "set_owner"}))
        state = contract_state(c["status"], c["valid_from"], c["valid_to"], today)
        if state == "expired":
            out.append(_issue("contract_expired", "warning", "contract", c["id"], label, "Contract has expired. Renew it by amendment or terminate it.", link))
        if c["status"] == "signed" and c["projects"] == 0:
            out.append(_issue("contract_without_project", "info", "contract", c["id"], label, "Signed contract is not linked to a project.", link))

    limit = datetime.now(timezone.utc) - timedelta(days=PAST_DAYS)
    for p in await q(db, "SELECT id, number, title FROM proposals WHERE organization_id = :o AND deleted_at IS NULL AND status = 'approved' AND updated_at < :l", o=org, l=limit):
        out.append(_issue("proposal_not_sent", "info", "proposal", p["id"], f"{p['number']} {p['title']}", f"Approved more than {PAST_DAYS} days ago but not marked as sent.", f"/sales/proposals/{p['id']}"))
    for r in await q(db, "SELECT dr.id, dr.label, r.name AS role_name FROM decision_rules dr JOIN roles r ON r.id = dr.role_id WHERE dr.organization_id = :o AND dr.deleted_at IS NULL AND dr.active AND NOT EXISTS (SELECT 1 FROM role_assignments ra WHERE ra.role_id = dr.role_id AND ra.deleted_at IS NULL)", o=org):
        out.append(_issue("decision_role_unfilled", "error", "decision_rule", r["id"], r["label"], f"The deciding role “{r['role_name']}” has no holder.", "/sales/settings"))
    return out


async def quality_counts(db, ctx) -> dict[str, Any]:
    issues = await collect_issues(db, ctx)
    by_kind: dict[str, int] = defaultdict(int)
    by_severity: dict[str, int] = defaultdict(int)
    for i in issues:
        by_kind[i["kind"]] += 1
        by_severity[i["severity"]] += 1
    return {"total": len(issues), "by_kind": dict(by_kind), "by_severity": dict(by_severity)}


@router.get("/data-quality", summary="Open data quality findings with the fix that applies")
async def data_quality(ctx: CtxDep, db: DbDep, kind: str | None = Query(default=None, max_length=60)) -> dict:
    issues = await collect_issues(db, ctx)
    counts: dict[str, int] = defaultdict(int)
    for i in issues:
        counts[i["kind"]] += 1
    shown = [i for i in issues if kind is None or i["kind"] == kind]
    return {"total": len(issues), "by_kind": dict(counts), "items": shown[:300], "truncated": len(shown) > 300}


# ------------------------------------------------------------------ fixes


@router.post("/data-quality/fix", summary="Correct a finding directly (owner, manager, next action, decision date)", responses={403: {"description": "Not allowed to change this record"}, 404: {"description": "Record not found"}, 422: {"description": "Missing value"}})
async def fix(body: FixBody, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    if body.action in ("set_owner", "set_manager"):
        if body.user_id is None:
            raise err(422, "USER_REQUIRED", "Choose a person.", "user_id")
        await check_member(db, ctx, body.user_id, "user_id")
    if body.action == "set_owner":
        await _set_owner(db, ctx, body)
    elif body.action == "set_manager":
        project = await _project(db, ctx, body.entity_id)
        if not await _can_edit_project(db, ctx, project):
            raise err(403, "PROJECT_FORBIDDEN", "Only administrators, the project manager or the project team can change this project.")
        await x(db, "UPDATE projects SET manager_id = :m, updated_at = NOW(), updated_by = :u WHERE id = :i", m=body.user_id, u=ctx.user_id, i=body.entity_id)
        await audit(db, ctx, "project.updated", "project", body.entity_id, f"{project['name']}: manager set", {"via": "data_quality"})
    elif body.action == "set_next_action":
        if not (body.text or "").strip():
            raise err(422, "TEXT_REQUIRED", "Describe the next action.", "text")
        opp = await require_edit_opp(db, ctx, body.entity_id)
        await x(db, "UPDATE opportunities SET next_action = :t, next_action_due = :d, updated_at = NOW(), updated_by = :u WHERE id = :i", t=body.text.strip(), d=body.day, u=ctx.user_id, i=body.entity_id)
        await audit(db, ctx, "opportunity.updated", "opportunity", body.entity_id, f"{opp['number']}: next action set", {"via": "data_quality"})
    else:
        if body.day is None:
            raise err(422, "DATE_REQUIRED", "Choose a date.", "day")
        opp = await require_edit_opp(db, ctx, body.entity_id)
        await x(db, "UPDATE opportunities SET expected_close = :d, updated_at = NOW(), updated_by = :u WHERE id = :i", d=body.day, u=ctx.user_id, i=body.entity_id)
        await audit(db, ctx, "opportunity.updated", "opportunity", body.entity_id, f"{opp['number']}: decision date set", {"via": "data_quality"})
    await db.commit()
    return {"ok": True}


async def _set_owner(db, ctx, body: FixBody) -> None:
    org = await q1(db, "SELECT name FROM crm_organizations WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=body.entity_id, o=ctx.org_id)
    if org is not None:
        await x(db, "UPDATE crm_organizations SET owner_user_id = :w, updated_at = NOW(), updated_by = :u WHERE id = :i", w=body.user_id, u=ctx.user_id, i=body.entity_id)
        await audit(db, ctx, "crm.organization_updated", "crm_organization", body.entity_id, f"{org['name']}: owner set", {"via": "data_quality"})
        return
    contract = await q1(db, "SELECT number FROM contracts WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=body.entity_id, o=ctx.org_id)
    if contract is not None:
        await _require_edit_contract(db, ctx, body.entity_id)
        await x(db, "UPDATE contracts SET owner_user_id = :w, updated_at = NOW(), updated_by = :u WHERE id = :i", w=body.user_id, u=ctx.user_id, i=body.entity_id)
        await audit(db, ctx, "contract.updated", "contract", body.entity_id, f"{contract['number']}: owner set", {"via": "data_quality"})
        return
    opp = await require_edit_opp(db, ctx, body.entity_id)
    await x(db, "UPDATE opportunities SET owner_user_id = :w, updated_at = NOW(), updated_by = :u WHERE id = :i", w=body.user_id, u=ctx.user_id, i=body.entity_id)
    await audit(db, ctx, "opportunity.updated", "opportunity", body.entity_id, f"{opp['number']}: owner set", {"via": "data_quality"})


@router.post("/contacts/merge", summary="Merge duplicate contacts into one; links, activities and gaps move to the kept contact", responses={404: {"description": "Contact not found"}, 422: {"description": "Invalid selection"}})
async def merge_contacts(body: MergeBody, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    if body.keep_id in body.merge_ids or len(set(body.merge_ids)) != len(body.merge_ids):
        raise err(422, "MERGE_INVALID", "Choose different contacts to merge.", "merge_ids")
    keep = await q1(db, "SELECT * FROM crm_contacts WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=body.keep_id, o=ctx.org_id)
    if keep is None:
        raise err(404, "CONTACT_NOT_FOUND", "Contact not found.", "keep_id")
    merged = []
    for mid in body.merge_ids:
        row = await q1(db, "SELECT * FROM crm_contacts WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=mid, o=ctx.org_id)
        if row is None:
            raise err(404, "CONTACT_NOT_FOUND", "Contact not found.", "merge_ids")
        merged.append(row)
    fill: dict[str, Any] = {}
    for row in merged:
        for col in ("email", "phone", "job_title"):
            if not keep[col] and row[col] and col not in fill:
                fill[col] = row[col]
        # Soft delete first: the unique e-mail index only covers live rows, so the address can move to the kept contact.
        await x(db, "UPDATE crm_contacts SET deleted_at = NOW(), notes = notes || :n, updated_by = :u WHERE id = :i", n=f"\nMerged into {keep['first_name']} {keep['last_name']}.", u=ctx.user_id, i=row["id"])
        await x(db, "INSERT INTO crm_contact_orgs (organization_id, contact_id, crm_org_id, contact_role, is_primary) SELECT organization_id, CAST(:k AS uuid), crm_org_id, contact_role, FALSE FROM crm_contact_orgs WHERE contact_id = :m ON CONFLICT DO NOTHING", k=body.keep_id, m=row["id"])
        await x(db, "DELETE FROM crm_contact_orgs WHERE contact_id = :m", m=row["id"])
        await x(db, "INSERT INTO project_contacts (organization_id, project_id, contact_id, contact_role) SELECT organization_id, project_id, CAST(:k AS uuid), contact_role FROM project_contacts WHERE contact_id = :m ON CONFLICT DO NOTHING", k=body.keep_id, m=row["id"])
        await x(db, "DELETE FROM project_contacts WHERE contact_id = :m", m=row["id"])
        await x(db, "INSERT INTO opportunity_contacts (organization_id, opportunity_id, contact_id, contact_role) SELECT organization_id, opportunity_id, CAST(:k AS uuid), contact_role FROM opportunity_contacts WHERE contact_id = :m ON CONFLICT DO NOTHING", k=body.keep_id, m=row["id"])
        await x(db, "DELETE FROM opportunity_contacts WHERE contact_id = :m", m=row["id"])
        await x(db, "UPDATE crm_activities SET contact_id = :k WHERE contact_id = :m", k=body.keep_id, m=row["id"])
    if fill:
        sets = ", ".join(f"{c} = :{c}" for c in fill)
        await x(db, f"UPDATE crm_contacts SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :i", u=ctx.user_id, i=body.keep_id, **fill)  # noqa: S608 - columns come from a fixed tuple
    await audit(db, ctx, "crm.contacts_merged", "crm_contact", body.keep_id, f"{len(merged)} contact(s) merged into {keep['first_name']} {keep['last_name']}", {"merged": [str(m['id']) for m in merged]})
    await db.commit()
    return {"ok": True, "merged": len(merged)}


# ----------------------------------------------------------------- export


async def _dataset(db, ctx, name: str) -> tuple[list[str], list[list[Any]]]:  # noqa: PLR0911 - one builder per dataset
    hide = ctx.level == "observer"
    today = date.today()
    if name == "opportunities":
        cfg_rows = await q(db, "SELECT stage, probability FROM pipeline_stage_config WHERE organization_id = :o", o=ctx.org_id)
        cfg = {r["stage"]: int(r["probability"]) for r in cfg_rows}
        rows = await q(
            db,
            """SELECT o.number, o.title, co.name AS customer, o.stage, o.category, o.risk, u.display_name AS owner, o.value_amount, o.currency, o.probability, o.probability_manual,
                      o.expected_close, o.next_action, o.next_action_due, (SELECT b.decision FROM bid_assessments b WHERE b.opportunity_id = o.id) AS bid
               FROM opportunities o JOIN crm_organizations co ON co.id = o.crm_org_id LEFT JOIN users u ON u.id = o.owner_user_id WHERE o.organization_id = :org AND o.deleted_at IS NULL ORDER BY o.number""",
            org=ctx.org_id,
        )
        headers = ["Number", "Title", "Customer", "Stage", "Category", "Risk", "Owner", "Bid decision", "Expected decision", "Next action", "Next action due"]
        if not hide:
            headers += ["Value", "Currency", "Probability %", "Weighted value"]
        out = []
        for r in rows:
            line: list[Any] = [r["number"], r["title"], r["customer"], r["stage"], r["category"], r["risk"], r["owner"], r["bid"], r["expected_close"], r["next_action"], r["next_action_due"]]
            if not hide:
                prob = effective_probability(r["stage"], r["probability"], r["probability_manual"], cfg)
                line += [r["value_amount"], r["currency"], prob, weighted_value(r["value_amount"], prob)]
            out.append(line)
        return headers, out
    if name == "proposals":
        cost = await has_cost_access(db, ctx)
        rows = await q(
            db,
            """SELECT p.number, p.title, o.number AS opp, co.name AS customer, p.status, v.version_no, v.price_total, v.cost_total, v.margin_pct, v.currency, p.valid_until
               FROM proposals p JOIN opportunities o ON o.id = p.opportunity_id AND o.deleted_at IS NULL JOIN crm_organizations co ON co.id = o.crm_org_id LEFT JOIN proposal_versions v ON v.id = p.current_version_id
               WHERE p.organization_id = :org AND p.deleted_at IS NULL ORDER BY p.number""",
            org=ctx.org_id,
        )
        headers = ["Number", "Title", "Opportunity", "Customer", "Status", "Version", "Valid until"]
        if not hide:
            headers += ["Total price", "Currency"]
        if cost:
            headers += ["Cost", "Margin %"]
        out = []
        for r in rows:
            line = [r["number"], r["title"], r["opp"], r["customer"], r["status"], r["version_no"], r["valid_until"]]
            if not hide:
                line += [r["price_total"], r["currency"]]
            if cost:
                line += [r["cost_total"], r["margin_pct"]]
            out.append(line)
        return headers, out
    if name == "contracts":
        terms_all = ctx.level == "org_admin" or await _signature_role(db, ctx)
        rows = await q(
            db,
            """SELECT c.number, c.title, co.name AS customer, c.contract_kind, c.status, c.valid_from, c.valid_to, c.value_amount, c.currency
               FROM contracts c JOIN crm_organizations co ON co.id = c.crm_org_id WHERE c.organization_id = :o AND c.deleted_at IS NULL ORDER BY c.number""",
            o=ctx.org_id,
        )
        headers = ["Number", "Title", "Customer", "Kind", "State", "Valid from", "Valid until"]
        if terms_all:
            headers += ["Value", "Currency"]
        out = []
        for r in rows:
            line = [r["number"], r["title"], r["customer"], r["contract_kind"], contract_state(r["status"], r["valid_from"], r["valid_to"], today), r["valid_from"], r["valid_to"]]
            if terms_all:
                line += [r["value_amount"], r["currency"]]
            out.append(line)
        return headers, out
    if name == "ndas":
        rows = await q(db, "SELECT n.number, n.title, co.name AS customer, n.nda_kind, n.status, n.valid_from, n.valid_to FROM ndas n JOIN crm_organizations co ON co.id = n.crm_org_id WHERE n.organization_id = :o AND n.deleted_at IS NULL ORDER BY n.number", o=ctx.org_id)
        return ["Number", "Title", "Customer", "Kind", "Status", "Coverage", "Valid from", "Valid until"], [
            [r["number"], r["title"], r["customer"], r["nda_kind"], r["status"], nda_coverage(r["status"], r["valid_from"], r["valid_to"], today), r["valid_from"], r["valid_to"]] for r in rows
        ]
    if name == "customers":
        rows = await q(
            db,
            """SELECT co.name, array_to_string(co.relation_types, ', ') AS relations, u.display_name AS owner, co.city, co.country, i.name AS industry,
                      (SELECT COUNT(*) FROM opportunities o WHERE o.crm_org_id = co.id AND o.deleted_at IS NULL AND o.stage IN ('lead','qualification','bid_decision','proposal','negotiation')) AS open_opps,
                      (SELECT COUNT(*) FROM project_orgs po JOIN projects p ON p.id = po.project_id AND p.deleted_at IS NULL WHERE po.crm_org_id = co.id) AS projects
               FROM crm_organizations co LEFT JOIN users u ON u.id = co.owner_user_id LEFT JOIN catalog_entries i ON i.id = co.industry_entry_id
               WHERE co.organization_id = :o AND co.deleted_at IS NULL ORDER BY co.name""",
            o=ctx.org_id,
        )
        return ["Name", "Relationships", "Owner", "City", "Country", "Industry", "Open opportunities", "Projects"], [
            [r["name"], r["relations"], r["owner"], r["city"], r["country"], r["industry"], r["open_opps"], r["projects"]] for r in rows
        ]
    if name == "projects":
        rows = await q(
            db,
            """SELECT p.name, p.project_no, p.classification, p.category, p.phase, p.status, u.display_name AS manager, p.start_date, p.due_date
               FROM projects p LEFT JOIN users u ON u.id = p.manager_id WHERE p.organization_id = :o AND p.deleted_at IS NULL ORDER BY p.name""",
            o=ctx.org_id,
        )
        return ["Name", "Project no.", "Classification", "Category", "Phase", "Status", "Manager", "Start", "Due"], [
            [r["name"], r["project_no"], r["classification"], r["category"], r["phase"], r["status"], r["manager"], r["start_date"], r["due_date"]] for r in rows
        ]
    issues = await collect_issues(db, ctx)
    return ["Kind", "Severity", "Record", "Message"], [[i["kind"], i["severity"], i["label"], i["message"]] for i in issues]


@router.get("/export/{dataset}", summary="Export a dataset as CSV or XLSX (columns follow the caller's permissions)", responses={404: {"description": "Unknown dataset"}})
async def export(dataset: str, ctx: CtxDep, db: DbDep, fmt: Literal["csv", "xlsx"] = Query(default="csv", alias="format")) -> Response:
    if dataset not in EXPORTS:
        raise err(404, "UNKNOWN_DATASET", "Unknown export.")
    headers, rows = await _dataset(db, ctx, dataset)
    await audit(db, ctx, "export.created", "export", None, f"{dataset} as {fmt}: {len(rows)} rows")
    await db.commit()
    filename = f"{dataset}-{date.today().isoformat()}.{fmt}"
    disposition = {"Content-Disposition": f'attachment; filename="{filename}"'}
    if fmt == "xlsx":
        return Response(make_xlsx(headers, rows, dataset), media_type=XLSX_TYPE, headers=disposition)
    return Response("\ufeff" + make_csv(headers, rows), media_type="text/csv; charset=utf-8", headers=disposition)
