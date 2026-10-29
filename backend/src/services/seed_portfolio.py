"""Demonstration data for the project portfolio and CRM modules.

All customers, contacts and figures are FICTIONAL and exist only in the demo organization. The seed is
guarded: it writes only while the organization has no catalog entries, so it never overwrites real data.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from database import async_session
from services.catalog import normalize
from services.ctx import Ctx
from services.dbx import q, q1, x
from services.governance import _replace_items, record_change, role_snapshot

logger = logging.getLogger(__name__)

DEMO_DOMAIN = "demo.circleos.app"

# kind, name, category, aliases
CATALOG: list[tuple[str, str, str | None, list[str]]] = [
    ("technology", "Angular", "Frontend", ["Angular 2+"]),
    ("technology", "React", "Frontend", ["React.js"]),
    ("technology", "TypeScript", "Language", ["TS"]),
    ("technology", "Python", "Language", ["py"]),
    ("technology", "FastAPI", "Backend", []),
    ("technology", "PostgreSQL", "Database", ["Postgres"]),
    ("technology", "Docker", "Infrastructure", []),
    ("technology", "Kubernetes", "Infrastructure", ["k8s"]),
    ("technology", "PyTorch", "Machine learning", []),
    ("technology", "scikit-learn", "Machine learning", ["sklearn"]),
    ("technology", "MQTT", "Industrial IoT", []),
    ("technology", "OPC UA", "Industrial IoT", ["OPC-UA"]),
    ("industry", "Healthcare", None, ["Health"]),
    ("industry", "Manufacturing", None, ["Industry 4.0"]),
    ("industry", "Energy & Utilities", None, ["Energy"]),
    ("industry", "Public Sector", None, []),
    ("research_area", "Machine Learning", None, ["ML"]),
    ("research_area", "Explainable AI", None, ["XAI"]),
    ("research_area", "Industrial AI", None, []),
    ("competency", "Software Architecture", None, []),
    ("competency", "UX Research", None, ["User research"]),
    ("method", "Agile Delivery", None, ["Scrum"]),
    ("application_domain", "Predictive Maintenance", None, ["PdM"]),
    ("application_domain", "Patient Portal", None, []),
    ("solution_type", "Web Platform", None, []),
    ("solution_type", "ML Pipeline", None, []),
    ("reusable_component", "Design System", None, []),
    ("reusable_component", "Anomaly Detection Toolkit", None, []),
]

# name, legal, vat, industry, city, country, relation types, owner, size, parent, notes
CUSTOMERS: list[dict[str, Any]] = [
    {"key": "nord", "name": "Nordklinik Health Group", "vat": "ATU00000001", "industry": "Healthcare", "city": "Linz", "rel": ["customer"], "owner": "markus", "size": "large", "since": -400},
    {"key": "alpen", "name": "Alpenwerk Maschinenbau GmbH", "vat": "ATU00000002", "industry": "Manufacturing", "city": "Steyr", "rel": ["customer"], "owner": "markus", "size": "medium", "since": -900},
    {"key": "alpen_service", "name": "Alpenwerk Service GmbH", "vat": None, "industry": "Manufacturing", "city": "Wels", "rel": ["customer"], "owner": None, "size": "small", "parent": "alpen", "since": None},
    {"key": "lindental", "name": "Stadtwerke Lindental", "vat": "ATU00000003", "industry": "Energy & Utilities", "city": "Lindental", "rel": ["customer", "partner"], "owner": "david", "size": "public", "since": -200},
    {"key": "tu", "name": "Technische Universität Demo", "vat": None, "industry": "Public Sector", "city": "Hagenberg", "rel": ["research_partner"], "owner": "jonas", "size": "public", "since": None},
    {"key": "fund", "name": "Regional Research Funding Agency (demo)", "vat": None, "industry": "Public Sector", "city": "Vienna", "rel": ["funder"], "owner": None, "size": "public", "since": None},
    {"key": "prospect", "name": "Greenfield Logistics (prospect)", "vat": "ATU00000004", "industry": "Manufacturing", "city": "Salzburg", "rel": ["prospect"], "owner": "david", "size": "medium", "since": None},
]

# key, first, last, email, title, org, role, primary
CONTACTS: list[tuple[str, str, str, str, str, str, str, bool]] = [
    ("c1", "Greta", "Hollweg", "greta.hollweg@nordklinik.example", "Head of Digital Health", "nord", "Sponsor", True),
    ("c2", "Bernd", "Aichinger", "bernd.aichinger@nordklinik.example", "IT Procurement", "nord", "Procurement", False),
    ("c3", "Katharina", "Dorfer", "katharina.dorfer@alpenwerk.example", "Director Service", "alpen", "Sponsor", True),
    ("c4", "Matthias", "Pichler", "matthias.pichler@alpenwerk.example", "Product Owner Portal", "alpen", "Product owner", False),
    ("c5", "Sabine", "Leitner", "sabine.leitner@lindental.example", "Head of Asset Management", "lindental", "Sponsor", True),
    ("c6", "Prof. Anton", "Reiter", "anton.reiter@tu-demo.example", "Professor Data Science", "tu", "Scientific lead", True),
]

KNOWLEDGE: dict[str, dict[str, tuple[str, str]]] = {
    "portal": {
        "business_context": ("The customer's service organization handled most requests by phone. A self-service portal should cut handling time and give dealers a single entry point.", "approved"),
        "solution": ("Angular single-page application on a Python API with PostgreSQL. Components come from the shared design system; authentication uses the customer's identity provider.", "verified"),
        "challenges": ("The legacy identity provider blocked the first release; migration was done in two steps behind a feature flag.", "verified"),
        "results": ("First beta with 40 dealers; support calls for order status dropped noticeably (figures to be confirmed with the customer).", "unverified"),
        "reuse": ("Order-status widget and the dealer onboarding flow are reusable for other portal projects.", "ai_draft"),
    },
    "pm": {
        "business_context": ("A regional utility wants to reduce unplanned downtime of pumps and transformers. Condition data exists but is not used systematically.", "approved"),
        "solution": ("Streaming ingestion via MQTT and OPC UA, an anomaly detection pipeline in Python and a dashboard for asset managers.", "verified"),
        "challenges": ("Sensor data quality: gaps, drift and mislabeled maintenance events required an explicit data quality stage.", "verified"),
        "results": ("Two pilot sites live; anomaly recall below plan at the second site (see results table).", "verified"),
        "reuse": ("The data quality stage and the anomaly detection toolkit were extracted as reusable components.", "unverified"),
        "architecture": ("Ingestion -> validation -> feature store (PostgreSQL) -> model service (FastAPI) -> dashboard. Models are retrained monthly.", "verified"),
        "ai_usage": ("Unsupervised anomaly detection and gradient boosting for failure classification. No customer personal data is processed.", "verified"),
    },
    "tender": {
        "business_context": ("Public tender for a patient portal platform of a hospital group.", "unverified"),
    },
}


def _d(days: int) -> date:
    return (datetime.now(timezone.utc) + timedelta(days=days)).date()


def _t(days: float) -> datetime:
    return datetime.now(timezone.utc) + timedelta(days=days)


async def seed_portfolio_if_missing() -> None:
    """Add portfolio/CRM demo data to demo organizations that predate these modules."""
    async with async_session() as db:
        orgs = await q(db, "SELECT id FROM organizations WHERE is_demo AND deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM catalog_entries c WHERE c.organization_id = organizations.id)")
        for o in orgs:
            if await seed_portfolio(db, o["id"]):
                logger.info("Portfolio and CRM demonstration data created")
        await db.commit()


async def seed_portfolio(db, org: UUID) -> bool:  # noqa: PLR0915 - one linear data script
    existing = await q1(db, "SELECT COUNT(*) AS n FROM catalog_entries WHERE organization_id = :o", o=org)
    if existing and existing["n"] > 0:
        return False
    users = await q(db, "SELECT u.id, u.email FROM users u JOIN memberships m ON m.user_id = u.id WHERE m.organization_id = :o", o=org)
    uid: dict[str, UUID] = {}
    for u in users:
        local = u["email"].split("@")[0]
        if u["email"].endswith(DEMO_DOMAIN):
            uid[local.split(".")[0]] = u["id"]
    if "anna" not in uid:
        return False
    circles = {c["name"]: c["id"] for c in await q(db, "SELECT id, name FROM circles WHERE organization_id = :o AND deleted_at IS NULL", o=org)}
    roles = {r["name"]: r for r in await q(db, "SELECT id, name, circle_id FROM roles WHERE organization_id = :o AND deleted_at IS NULL", o=org)}
    projects = {p["name"]: p["id"] for p in await q(db, "SELECT id, name FROM projects WHERE organization_id = :o AND deleted_at IS NULL", o=org)}
    ctx = Ctx(user_id=uid["anna"], org_id=org, level="org_admin", name="Anna Berger", email=f"anna.berger@{DEMO_DOMAIN}")

    # ---- catalog
    entry: dict[str, UUID] = {}
    for kind, name, category, aliases in CATALOG:
        row = await q1(
            db,
            "INSERT INTO catalog_entries (organization_id, kind, name, norm_name, category, created_by, updated_by) VALUES (:o, :k, :n, :nn, :c, :u, :u) RETURNING id",
            o=org, k=kind, n=name, nn=normalize(name), c=category, u=uid["anna"],
        )
        entry[name] = row["id"]
        for alias in aliases:
            await x(db, "INSERT INTO catalog_aliases (organization_id, entry_id, kind, alias, norm_alias) VALUES (:o, :e, :k, :a, :n)", o=org, e=row["id"], k=kind, a=alias, n=normalize(alias))

    # ---- customers
    crm: dict[str, UUID] = {}
    for c in CUSTOMERS:
        row = await q1(
            db,
            """INSERT INTO crm_organizations (organization_id, name, norm_name, vat_id, industry_entry_id, city, country, size_class, parent_id, relation_types,
                                              owner_user_id, customer_since, notes, created_by, updated_by)
               VALUES (:o, :n, :nn, :v, :i, :ci, 'Austria', :sz, :pa, :rt, :ow, :cs, 'Fictional demonstration organization.', :u, :u) RETURNING id""",
            o=org, n=c["name"], nn=normalize(c["name"]), v=c["vat"], i=entry[c["industry"]], ci=c["city"], sz=c["size"], pa=crm.get(c.get("parent", "")),
            rt=c["rel"], ow=uid.get(c["owner"]) if c["owner"] else None, cs=_d(c["since"]) if c["since"] else None, u=uid["anna"],
        )
        crm[c["key"]] = row["id"]
    contact: dict[str, UUID] = {}
    for key, first, last, email, title, org_key, crole, primary in CONTACTS:
        row = await q1(
            db,
            "INSERT INTO crm_contacts (organization_id, first_name, last_name, email, job_title, notes, created_by, updated_by) VALUES (:o, :f, :l, :e, :t, 'Fictional demonstration contact.', :u, :u) RETURNING id",
            o=org, f=first, l=last, e=email, t=title, u=uid["anna"],
        )
        contact[key] = row["id"]
        await x(db, "INSERT INTO crm_contact_orgs (organization_id, contact_id, crm_org_id, contact_role, is_primary) VALUES (:o, :c, :g, :r, :p)", o=org, c=row["id"], g=crm[org_key], r=crole, p=primary)

    # ---- projects: classify the existing ones, add new ones
    async def classify(name: str, **cols: Any) -> UUID:
        sets = ", ".join(f"{k} = :{k}" for k in cols)
        await x(db, f"UPDATE projects SET {sets} WHERE organization_id = :o AND name = :n", o=org, n=name, **cols)  # noqa: S608 - constant column names
        return projects[name]

    async def new_project(name: str, circle: str, role: str, desc: str, status: str, sd: int, dd: int, **cols: Any) -> UUID:
        base = {"organization_id": org, "circle_id": circles[circle], "owning_role_id": roles[role]["id"], "name": name, "description": desc, "status": status, "start_date": _d(sd), "due_date": _d(dd), "created_by": uid["anna"], "updated_by": uid["anna"], **cols}
        row = await q1(db, f"INSERT INTO projects ({', '.join(base)}) VALUES ({', '.join(':' + k for k in base)}) RETURNING id", **base)  # noqa: S608 - constant column names
        projects[name] = row["id"]
        return row["id"]

    p_tender = await classify("Tender: Regional Hospital Platform", classification="customer", category="consulting", phase="proposal", short_name="HospTender", project_no="P-2025-004", org_unit="Customer Solutions", manager_id=uid["david"])
    p_portal = await classify("Customer Portal Relaunch", classification="customer", category="development", phase="running", short_name="Portal", project_no="P-2025-001", org_unit="Customer Solutions", manager_id=uid["tobias"])
    p_ai = await classify("AI Assistant Pilot", classification="internal", category="innovation", phase="running", short_name="AI Pilot", project_no="P-2025-003", org_unit="Venture & Product", manager_id=uid["ravi"], ai_relevant=True)
    await classify("Service Desk Automation", classification="internal", category="operations", phase="idea", short_name="Desk", project_no="P-2025-006", org_unit="Service Operations", manager_id=uid["mira"])
    await classify("Innovation Sprint Q3", classification="internal", category="innovation", phase="idea", short_name="Sprint Q3", org_unit="Services & Solutions", manager_id=uid["jonas"])
    p_pm = await new_project(
        "Predictive Maintenance for Stadtwerke Lindental", "Venture & Product", "AI Specialist",
        "Research and development project: anomaly detection on pump and transformer sensor data for a regional utility.", "active", -150, 120,
        classification="customer", category="research", phase="running", short_name="PrediMaint", project_no="P-2025-002", org_unit="Venture & Product",
        manager_id=uid["tobias"], is_research=True, funding_program="Regional Industrial Research Programme (demo)", funding_agency="Regional Research Funding Agency (demo)",
        funding_ref="DEMO-2025-0815", research_note="Industrial AI under real-world data quality conditions.", ai_relevant=True,
    )
    p_xai = await new_project(
        "Explainable AI Toolkit", "Venture & Product", "AI Specialist", "Internal toolkit that explains anomaly decisions to domain experts.", "active", -60, 90,
        classification="internal", category="research", phase="running", short_name="XAI Kit", project_no="P-2025-005", org_unit="Venture & Product", manager_id=uid["ravi"], is_research=True, ai_relevant=True,
    )
    p_ds = await new_project(
        "Shared Design System", "Customer Solutions", "UX Specialist", "Reusable UI components for all customer web projects.", "active", -200, 30,
        classification="internal", category="development", phase="closing", short_name="DS", project_no="P-2024-011", org_unit="Customer Solutions", manager_id=uid["clara"],
    )

    # ---- organizations and contacts per project
    for pid, org_key, rel in [(p_tender, "nord", "customer"), (p_portal, "alpen", "customer"), (p_pm, "lindental", "customer"), (p_pm, "fund", "funder"), (p_pm, "tu", "research_partner")]:
        await x(db, "INSERT INTO project_orgs (organization_id, project_id, crm_org_id, relation) VALUES (:o, :p, :c, :r)", o=org, p=pid, c=crm[org_key], r=rel)
    for pid, ckey, crole in [(p_tender, "c1", "Sponsor"), (p_tender, "c2", "Procurement"), (p_portal, "c3", "Sponsor"), (p_portal, "c4", "Product owner"), (p_pm, "c5", "Sponsor"), (p_pm, "c6", "Scientific lead")]:
        await x(db, "INSERT INTO project_contacts (organization_id, project_id, contact_id, contact_role) VALUES (:o, :p, :c, :r)", o=org, p=pid, c=contact[ckey], r=crole)
    for pid in (p_pm, p_xai):
        for person in ("ravi", "felix"):
            await x(db, "INSERT INTO project_people (organization_id, project_id, user_id) VALUES (:o, :p, :u) ON CONFLICT DO NOTHING", o=org, p=pid, u=uid[person])

    # ---- catalog links
    links = {
        p_portal: ["Angular", "TypeScript", "PostgreSQL", "Docker", "Python", "Design System", "Web Platform", "Manufacturing", "UX Research", "Agile Delivery"],
        p_tender: ["Healthcare", "Patient Portal", "Web Platform", "Angular", "Kubernetes"],
        p_pm: ["Python", "scikit-learn", "MQTT", "OPC UA", "PostgreSQL", "FastAPI", "Machine Learning", "Industrial AI", "Predictive Maintenance", "ML Pipeline", "Energy & Utilities", "Anomaly Detection Toolkit"],
        p_ai: ["Python", "FastAPI", "PyTorch", "Machine Learning", "React"],
        p_xai: ["Python", "PyTorch", "Explainable AI", "Machine Learning", "Anomaly Detection Toolkit"],
        p_ds: ["Angular", "React", "TypeScript", "Design System", "UX Research"],
    }
    for pid, names in links.items():
        for n in names:
            await x(db, "INSERT INTO project_catalog_links (organization_id, project_id, entry_id) VALUES (:o, :p, :e)", o=org, p=pid, e=entry[n])
    for role_name, names in {"Software Engineer": ["TypeScript", "Python", "Software Architecture"], "AI Specialist": ["Machine Learning", "Python", "PyTorch", "Explainable AI"], "UX Specialist": ["UX Research", "Design System"]}.items():
        for n in names:
            await x(db, "INSERT INTO role_catalog_links (organization_id, role_id, entry_id) VALUES (:o, :r, :e)", o=org, r=roles[role_name]["id"], e=entry[n])

    # ---- knowledge
    pids = {"portal": p_portal, "pm": p_pm, "tender": p_tender}
    for key, sections in KNOWLEDGE.items():
        for section, (content, verification) in sections.items():
            stamp = verification in ("verified", "approved")
            await x(
                db,
                """INSERT INTO project_knowledge (organization_id, project_id, section, content, verification, verified_by, verified_at, created_by, updated_by)
                   VALUES (:o, :p, :s, :c, :v, CASE WHEN :st THEN CAST(:u AS uuid) END, CASE WHEN :st THEN NOW() END, :u, :u)""",
                o=org, p=pids[key], s=section, c=content, v=verification, st=stamp, u=uid["anna"],
            )

    # ---- work packages and results (research project)
    wp: dict[str, UUID] = {}
    for pos, (code, title, status, sd, ed) in enumerate([("WP1", "Data acquisition and quality", "done", -150, -90), ("WP2", "Anomaly detection models", "active", -100, 20), ("WP3", "Pilot deployment and evaluation", "planned", 0, 110)]):
        row = await q1(
            db,
            """INSERT INTO project_work_packages (organization_id, project_id, code, title, status, start_date, end_date, lead_user_id, position, created_by, updated_by)
               VALUES (:o, :p, :c, :t, :s, :sd, :ed, :l, :pos, :u, :u) RETURNING id""",
            o=org, p=p_pm, c=code, t=title, s=status, sd=_d(sd), ed=_d(ed), l=uid["ravi"], pos=pos, u=uid["anna"],
        )
        wp[code] = row["id"]
    for title, kind, w, planned, shown, unit, status in [
        ("Data quality report for three sites", "deliverable", "WP1", "3", "3", "sites", "achieved"),
        ("Anomaly recall on labelled failures", "kpi", "WP2", "90", "87", "%", "partial"),
        ("Pilot sites live", "kpi", "WP3", "3", "2", "sites", "partial"),
        ("Conference paper on data quality effects", "publication", "WP2", "1", None, "paper", "planned"),
    ]:
        await x(
            db,
            """INSERT INTO project_results (organization_id, project_id, work_package_id, title, kind, planned_value, demonstrated_value, unit, status, created_by, updated_by)
               VALUES (:o, :p, :w, :t, :k, :pv, :dv, :un, :s, :u, :u)""",
            o=org, p=p_pm, w=wp[w], t=title, k=kind, pv=planned, dv=shown, un=unit, s=status, u=uid["anna"],
        )

    # ---- finance (visible to admins, project managers and explicit viewers only)
    for pid, total, funding, own, costs, revenue, cycle, due in [(p_pm, 480000, 240000, 240000, 310000, 240000, "quarterly", 12), (p_portal, 150000, 0, 150000, 82000, 150000, "monthly", -3)]:
        await x(
            db,
            """INSERT INTO project_finance (organization_id, project_id, budget_total, budget_funding, budget_own, costs_to_date, revenue_expected, reporting_cycle, next_report_due, created_by, updated_by)
               VALUES (:o, :p, :t, :f, :ow, :c, :r, :cy, :d, :u, :u)""",
            o=org, p=pid, t=total, f=funding, ow=own, c=costs, r=revenue, cy=cycle, d=_d(due), u=uid["anna"],
        )
    await x(db, "INSERT INTO project_finance_viewers (organization_id, project_id, user_id) VALUES (:o, :p, :u)", o=org, p=p_pm, u=uid["eva"])

    # ---- reference permissions and relations
    await x(db, "INSERT INTO project_communication (organization_id, project_id, reference_allowed, allow_name, allow_description, allow_results, approved_by_name, approved_at, notes) VALUES (:o, :p, TRUE, FALSE, TRUE, TRUE, 'Katharina Dorfer', :d, 'Name only anonymised; approved by e-mail (demo).')", o=org, p=p_portal, d=_d(-40))
    await x(db, "INSERT INTO project_communication (organization_id, project_id, reference_allowed, allow_name, allow_logo, allow_description, allow_results, approved_by_name, approved_at) VALUES (:o, :p, TRUE, TRUE, TRUE, TRUE, TRUE, 'Sabine Leitner', :d)", o=org, p=p_pm, d=_d(-20))
    for a, b, rel in [(p_pm, p_xai, "reuses"), (p_portal, p_ds, "reuses"), (p_tender, p_portal, "related")]:
        await x(db, "INSERT INTO project_relations (organization_id, project_id, related_project_id, relation) VALUES (:o, :a, :b, :r)", o=org, a=a, b=b, r=rel)
    await x(db, "INSERT INTO attachments (organization_id, entity_type, entity_id, name, url, created_by) VALUES (:o, 'project', :p, 'Project charter (demo link)', 'https://example.com/demo/charter', :u)", o=org, p=p_pm, u=uid["anna"])

    # ---- Key Account role scoped to customers
    cs_circle = circles["Customer Solutions"]
    role = await q1(
        db,
        """INSERT INTO roles (organization_id, circle_id, name, purpose, allow_multiple, can_govern, created_by, updated_by)
           VALUES (:o, :c, 'Key Account Manager', 'Strategic customers feel well looked after and grow with us.', TRUE, FALSE, :u, :u) RETURNING id""",
        o=org, c=cs_circle, u=uid["anna"],
    )
    await _replace_items(db, ctx, "accountabilities", ["Maintaining the relationship with assigned customers", "Preparing regular customer check-ins", "Passing customer needs to delivery and bid roles"], role_id=role["id"])
    await _replace_items(db, ctx, "domains", ["Customer relationship notes"], role_id=role["id"])
    snap = await role_snapshot(db, org, role["id"])
    await record_change(db, ctx, proposal_id=None, circle_id=cs_circle, entity_type="role", entity_id=role["id"], op="create", before=None, after=snap, source="seed", summary="Created role “Key Account Manager”", at=_t(-100))
    for person, scope_keys in {"markus": ["nord", "alpen"], "david": ["lindental", "prospect"]}.items():
        ra = await q1(db, "INSERT INTO role_assignments (organization_id, role_id, user_id, focus, created_by) VALUES (:o, :r, :u, :f, :by) RETURNING id", o=org, r=role["id"], u=uid[person], f="Key accounts", by=uid["anna"])
        for key in scope_keys:
            await x(db, "INSERT INTO crm_role_scopes (organization_id, role_assignment_id, scope_type, crm_org_id, created_by) VALUES (:o, :ra, 'organization', :c, :u)", o=org, ra=ra["id"], c=crm[key], u=uid["anna"])

    # ---- activities (one with a follow-up task)
    task = await q1(
        db,
        "INSERT INTO tasks (organization_id, assignee_id, title, description, due_date, created_by, updated_by) VALUES (:o, :a, 'Send revised offer to Nordklinik', 'Follow-up from CRM activity: Offer discussion', :d, :u, :u) RETURNING id",
        o=org, a=uid["markus"], d=_d(5), u=uid["markus"],
    )
    for org_key, ckey, kind, subject, body, days, project, person, follow in [
        ("nord", "c1", "meeting", "Offer discussion", "Walked through the platform concept; customer wants a revised price structure.", -4, p_tender, "markus", task["id"]),
        ("nord", "c2", "email", "Procurement requirements", "Received the formal procurement checklist.", -12, p_tender, "david", None),
        ("alpen", "c3", "call", "Quarterly check-in", "Satisfied with the beta; asks for a dealer onboarding workshop.", -9, p_portal, "markus", None),
        ("alpen", "c4", "note", "Scope change noted", "Product owner moved the reporting module to release 2.", -20, p_portal, "tobias", None),
        ("lindental", "c5", "visit", "Pilot site visit", "Visited the second pilot site; sensors installed, data flowing.", -30, p_pm, "ravi", None),
        ("lindental", "c6", "meeting", "Research alignment", "Agreed publication plan with the university partner.", -45, p_pm, "david", None),
        ("prospect", None, "call", "Intro call", "Initial conversation about warehouse analytics.", -100, None, "david", None),
    ]:
        await x(
            db,
            """INSERT INTO crm_activities (organization_id, crm_org_id, contact_id, project_id, kind, subject, body, occurred_at, follow_up_task_id, created_by, updated_by)
               VALUES (:o, :co, :c, :p, :k, :s, :b, :at, :t, :u, :u)""",
            o=org, co=crm[org_key], c=contact.get(ckey) if ckey else None, p=project, k=kind, s=subject, b=body, at=_t(days), t=follow, u=uid[person],
        )
    await x(db, "INSERT INTO audit_events (organization_id, actor_id, action, entity_type, summary) VALUES (:o, :u, 'demo.portfolio_seeded', 'organization', 'Portfolio and CRM demonstration data created')", o=org, u=uid["anna"])
    return True
