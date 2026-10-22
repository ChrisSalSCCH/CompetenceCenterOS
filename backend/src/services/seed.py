"""Demonstration data (clearly labelled: the organization is flagged `is_demo`).

Runs at startup only when no organization exists, and via the administrator's reset function.
It never touches non-demo organizations.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from database import async_session
from services.auth import hash_password
from services.ctx import Ctx
from services.dbx import jb, q1, x
from services.governance import _replace_items, circle_snapshot, record_change, role_snapshot

logger = logging.getLogger(__name__)

DEMO_DOMAIN = "demo.circleos.app"
DEMO_PASSWORD = "Demo-Circle-2025!"  # noqa: S105 - documented demonstration credential, not a secret
ORG_SLUG = "services-solutions-demo"

# key, name, job title, access level, color, skills, availability
PEOPLE: list[tuple[str, str, str, str, str, list[str], str]] = [
    ("anna", "Anna Berger", "Managing Director", "org_admin", "#C2512D", ["strategy", "leadership"], "Full time"),
    ("markus", "Markus Huber", "Head of Customer Solutions", "member", "#1F5C4A", ["sales", "consulting", "negotiation"], "Full time"),
    ("lena", "Lena Fischer", "Product Manager", "member", "#2F4B7C", ["product strategy", "roadmapping"], "Full time"),
    ("david", "David Mayer", "Bid Manager", "member", "#8A5A00", ["bid writing", "pricing", "public tenders"], "4 days / week"),
    ("sophie", "Sophie Wagner", "People & Culture", "member", "#7A3E65", ["coaching", "recruiting"], "Full time"),
    ("jonas", "Jonas Bauer", "Innovation Lead", "member", "#3E6B5C", ["innovation workshops", "research"], "Full time"),
    ("mira", "Mira Hofer", "Operations Excellence", "member", "#9C4A1A", ["process design", "ITIL", "facilitation"], "Full time"),
    ("tobias", "Tobias Gruber", "Project Manager", "member", "#4A4E8A", ["project management", "agile"], "Full time"),
    ("clara", "Clara Moser", "UX Specialist", "member", "#B3541E", ["user research", "interaction design"], "3 days / week"),
    ("ravi", "Ravi Patel", "AI Engineer", "member", "#1F6F78", ["machine learning", "LLM", "python"], "Full time"),
    ("felix", "Felix Steiner", "Software Engineer", "member", "#5A6B2E", ["typescript", "cloud", "testing"], "Full time"),
    ("eva", "Eva Lang", "Controller (observer)", "observer", "#6B5B73", ["controlling", "reporting"], "2 days / week"),
]

CIRCLES: list[dict[str, Any]] = [
    {
        "key": "root", "parent": None, "name": "Services & Solutions", "mode": "holacracy",
        "purpose": "Turn software and innovation expertise into lasting value for our customers and a healthy, learning organization.",
        "description": "Demonstration data: root circle of a fictional software and innovation company.",
        "accountabilities": ["Aligning the sub-circles with the organization's strategy", "Keeping the organization's governance clear and current"],
        "domains": ["Organization-wide budget", "Company brand"],
        "policies": ["Customer projects above 150 k EUR need a review by the Circle Lead before a bid is submitted."],
    },
    {
        "key": "cs", "parent": "root", "name": "Customer Solutions", "mode": "consent",
        "purpose": "Win and deliver customer projects that solve real problems.",
        "description": "Bids, delivery and customer relationships for project business.",
        "accountabilities": ["Acquiring and delivering customer projects", "Maintaining long-term customer relationships"],
        "domains": ["Customer contracts and bids"],
        "policies": ["Every bid is reviewed by a second person before submission."],
    },
    {
        "key": "so", "parent": "root", "name": "Service Operations", "mode": "approval",
        "purpose": "Run reliable, continuously improving services for our customers.",
        "description": "Operations, support and service quality.",
        "accountabilities": ["Operating customer-facing services reliably", "Continuously improving service processes"],
        "domains": ["Operational runbooks"],
        "policies": ["Incidents are acknowledged within four working hours."],
    },
    {
        "key": "vp", "parent": "root", "name": "Venture & Product", "mode": "direct",
        "purpose": "Build and validate new products with high customer and business potential.",
        "description": "Product discovery, development and early market validation.",
        "accountabilities": ["Discovering and validating product opportunities", "Developing product increments"],
        "domains": ["Product roadmap"],
        "policies": ["New product ideas are validated with at least three customers before development starts."],
    },
]

# key, circle, name, purpose, accountabilities, domains, authorities[(text, level)], can_govern, multi, holders[(person, focus)]
ROLES: list[dict[str, Any]] = [
    {"key": "lead_root", "circle": "root", "name": "Circle Lead Services & Solutions", "can_govern": True, "multi": False,
     "purpose": "The circle's purpose is pursued coherently and its governance stays healthy.",
     "acc": ["Assigning people to the circle's roles", "Allocating the circle's budget among its sub-circles", "Resolving tensions that sub-circles cannot resolve themselves"],
     "dom": [], "aut": [("Assigning and removing role holders in the root circle", "decides"), ("Reviewing customer projects above 150 k EUR", "consents")],
     "holders": [("anna", None)]},
    {"key": "facilitator", "circle": "root", "name": "Facilitator", "can_govern": False, "multi": False,
     "purpose": "Meetings are effective and follow the agreed process.",
     "acc": ["Facilitating governance and tactical meetings of the root circle", "Coaching members on the meeting process"],
     "dom": ["Meeting process"], "aut": [], "holders": [("mira", None)]},
    {"key": "secretary", "circle": "root", "name": "Secretary", "can_govern": False, "multi": False,
     "purpose": "The circle's records are complete and trustworthy.",
     "acc": ["Scheduling the circle's meetings", "Capturing and publishing meeting outcomes", "Maintaining the governance records"],
     "dom": ["Circle records and meeting minutes"], "aut": [], "holders": [("tobias", None)]},
    {"key": "innovation", "circle": "root", "name": "Innovation Catalyst", "can_govern": False, "multi": False,
     "purpose": "Innovation happens deliberately across all circles instead of by accident.",
     "acc": ["Coordinating innovation activities and ideas across circles", "Running quarterly innovation workshops", "Connecting internal teams with external research partners"],
     "dom": ["Innovation idea pipeline"], "aut": [("Deciding which ideas enter the innovation pipeline", "decides")], "holders": [("jonas", "Cross-circle")]},
    {"key": "people", "circle": "root", "name": "People Lead", "can_govern": False, "multi": False,
     "purpose": "People grow, feel supported and contribute their strengths.",
     "acc": ["Coordinating personnel development and training plans for all members", "Supporting onboarding of new members", "Maintaining the skills overview", "Recruiting new members together with the hiring circle"],
     "dom": ["Personnel development plans", "Skills overview"], "aut": [("Approving training budgets up to 2 k EUR per person", "decides")], "holders": [("sophie", None)]},
    {"key": "finance", "circle": "root", "name": "Finance Steward", "can_govern": False, "multi": False,
     "purpose": "The organization uses its financial resources transparently and sustainably.",
     "acc": ["Tracking budgets and preparing financial reports", "Checking the commercial viability of larger bids"],
     "dom": ["Organization-wide budget tracking"], "aut": [("Approving expenses above the circle budget", "decides")], "holders": []},
    {"key": "lead_cs", "circle": "cs", "name": "Customer Solutions Lead", "can_govern": True, "multi": False,
     "purpose": "Customer Solutions wins and delivers projects that create customer value.",
     "acc": ["Prioritizing the customer project pipeline", "Coordinating training and personnel development of the circle's members", "Escalating cross-circle tensions"],
     "dom": ["Customer project portfolio"],
     "aut": [("Deciding whether a new customer project is accepted (go/no-go) within the approved budget framework", "decides")],
     "holders": [("markus", None)]},
    {"key": "bid", "circle": "cs", "name": "Bid Manager", "can_govern": False, "multi": False,
     "purpose": "Promising customer opportunities are turned into convincing, profitable bids.",
     "acc": ["Qualifying and acquiring new customer projects (project acquisition)", "Preparing bids and proposals", "Tracking the bid pipeline and win rate"],
     "dom": ["Bid documents and templates"],
     "aut": [("Recommending go/no-go for new customer projects to the Customer Solutions Lead", "consulted")],
     "holders": [("david", None)]},
    {"key": "pm", "circle": "cs", "name": "Project Manager", "can_govern": False, "multi": True,
     "purpose": "Customer projects are delivered on time, within scope and with transparent status.",
     "acc": ["Planning milestones and tracking progress of customer projects", "Surfacing risks and blockers early", "Reporting project status to customers"],
     "dom": ["Project plans and timelines"], "aut": [("Deciding project sequencing within the agreed scope", "decides")],
     "holders": [("tobias", "Customer Portal Relaunch")]},
    {"key": "ux", "circle": "cs", "name": "UX Specialist", "can_govern": False, "multi": False,
     "purpose": "Digital solutions are intuitive and a pleasure to use.",
     "acc": ["Conducting user research and usability tests", "Designing interaction flows and prototypes", "Maintaining the design system"],
     "dom": ["Design system"], "aut": [("Deciding interaction design details within the agreed scope", "decides")],
     "holders": [("clara", None)]},
    {"key": "success", "circle": "cs", "name": "Customer Success Steward", "can_govern": False, "multi": False,
     "purpose": "Customers achieve their goals with our solutions and stay with us.",
     "acc": ["Running regular check-ins with key customers", "Collecting and relaying customer feedback"],
     "dom": ["Customer feedback log"], "aut": [], "holders": []},
    {"key": "lead_so", "circle": "so", "name": "Service Operations Lead", "can_govern": True, "multi": False,
     "purpose": "Services run reliably and improve continuously.",
     "acc": ["Prioritizing operational work and improvements", "Staffing the on-call rota"],
     "dom": ["On-call rota"], "aut": [("Deciding on the service level targets offered to customers", "decides")],
     "holders": [("mira", None)]},
    {"key": "process", "circle": "so", "name": "Process Innovation Steward", "can_govern": False, "multi": False,
     "purpose": "Service processes keep getting simpler, faster and more automated.",
     "acc": ["Coordinating process improvement ideas and automation activities", "Documenting and publishing process changes", "Measuring the effect of process changes"],
     "dom": ["Process documentation"], "aut": [("Deciding which process improvements are piloted", "decides")],
     "holders": [("mira", "Automation")]},
    {"key": "quality", "circle": "so", "name": "Quality Steward", "can_govern": False, "multi": False,
     "purpose": "Deliverables meet the agreed quality standards.",
     "acc": ["Defining and maintaining quality standards and checklists", "Reviewing deliverables against the standards"],
     "dom": ["Quality standards and checklists"], "aut": [("Deciding whether a deliverable meets the quality bar", "decides")],
     "holders": [("felix", None)]},
    {"key": "lead_vp", "circle": "vp", "name": "Venture & Product Lead", "can_govern": True, "multi": False,
     "purpose": "Venture & Product turns validated ideas into products.",
     "acc": ["Allocating development capacity between product bets", "Deciding when a product bet is stopped or scaled"],
     "dom": ["Product development capacity"], "aut": [("Deciding to stop or scale a product bet", "decides")],
     "holders": [("lena", None)]},
    {"key": "product", "circle": "vp", "name": "Product Manager", "can_govern": False, "multi": False,
     "purpose": "Customer value is maximised through a clear, prioritised product backlog.",
     "acc": ["Maintaining and prioritising the product backlog", "Clarifying requirements with customers and stakeholders", "Accepting delivered product increments"],
     "dom": ["Product backlog", "Product roadmap"], "aut": [("Deciding backlog priority", "decides")],
     "holders": [("lena", None)]},
    {"key": "ai", "circle": "vp", "name": "AI Specialist", "can_govern": False, "multi": False,
     "purpose": "AI capabilities are applied responsibly where they create customer value.",
     "acc": ["Evaluating AI models and techniques for product use cases", "Building and maintaining AI prototypes", "Advising other roles on AI feasibility"],
     "dom": ["AI model evaluations"], "aut": [("Deciding which AI models are used in prototypes", "decides")],
     "holders": [("ravi", None)]},
    {"key": "swe", "circle": "vp", "name": "Software Engineer", "can_govern": False, "multi": True,
     "purpose": "Working software is delivered continuously with high technical quality.",
     "acc": ["Implementing product increments", "Writing automated tests and reviewing code", "Operating the build and deployment pipeline"],
     "dom": ["Source code and deployment pipeline"], "aut": [("Deciding technical implementation details", "decides")],
     "holders": [("felix", None), ("ravi", "Prototyping")]},
]


def _d(days: int) -> date:
    return (datetime.now(timezone.utc) + timedelta(days=days)).date()


def _t(days: float, hour: int | None = None) -> datetime:
    base = datetime.now(timezone.utc) + timedelta(days=days)
    return base.replace(hour=hour, minute=0, second=0, microsecond=0) if hour is not None else base


async def seed_if_empty() -> None:
    async with async_session() as db:
        row = await q1(db, "SELECT COUNT(*) AS n FROM organizations")
        if row and row["n"] == 0:
            await seed_demo(db)
            await db.commit()
            logger.info("Demonstration organization created")


async def reset_demo(db, org_id: UUID) -> None:
    """Delete the demo organization and recreate the sample data (users keep their ids)."""
    await x(db, "DELETE FROM organizations WHERE id = :o AND is_demo", o=org_id)
    await seed_demo(db)


async def _ins(db, sql: str, **p: Any) -> UUID:
    row = await q1(db, sql, **p)
    return row["id"]


async def seed_demo(db) -> UUID:  # noqa: PLR0915 - one linear data script
    pw = hash_password(DEMO_PASSWORD)
    uid: dict[str, UUID] = {}
    for key, name, _title, _lvl, _color, _skills, _av in PEOPLE:
        email = f"{name.lower().replace(' ', '.')}@{DEMO_DOMAIN}"
        uid[key] = await _ins(
            db,
            """INSERT INTO users (email, password_hash, display_name) VALUES (:e, :p, :n)
               ON CONFLICT (email) DO UPDATE SET password_hash = EXCLUDED.password_hash, display_name = EXCLUDED.display_name, updated_at = NOW()
               RETURNING id""",
            e=email, p=pw, n=name,
        )
    org = await _ins(
        db,
        """INSERT INTO organizations (name, slug, default_governance_mode, is_demo, created_by)
           VALUES ('Services & Solutions (demonstration data)', :s, 'holacracy', TRUE, :u) RETURNING id""",
        s=ORG_SLUG, u=uid["anna"],
    )
    for key, _name, title, level, color, skills, avail in PEOPLE:
        await x(
            db,
            """INSERT INTO memberships (organization_id, user_id, access_level, job_title, skills, availability, avatar_color, created_by)
               VALUES (:o, :u, :l, :t, :s, :a, :c, :by)""",
            o=org, u=uid[key], l=level, t=title, s=skills, a=avail, c=color, by=uid["anna"],
        )
    ctx = Ctx(user_id=uid["anna"], org_id=org, level="org_admin", name="Anna Berger", email=f"anna.berger@{DEMO_DOMAIN}")
    created_at = _t(-120)

    # ---- circles
    cid: dict[str, UUID] = {}
    for pos, c in enumerate(CIRCLES):
        cid[c["key"]] = await _ins(
            db,
            """INSERT INTO circles (organization_id, parent_id, name, purpose, description, governance_mode, position, created_by, updated_by)
               VALUES (:o, :p, :n, :pu, :d, :m, :pos, :u, :u) RETURNING id""",
            o=org, p=cid.get(c["parent"]) if c["parent"] else None, n=c["name"], pu=c["purpose"], d=c["description"], m=c["mode"], pos=pos, u=uid["anna"],
        )
        await _replace_items(db, ctx, "accountabilities", c["accountabilities"], circle_id=cid[c["key"]])
        await _replace_items(db, ctx, "domains", c["domains"], circle_id=cid[c["key"]])
        await _replace_items(db, ctx, "policies", c["policies"], circle_id=cid[c["key"]])
        snap = await circle_snapshot(db, org, cid[c["key"]])
        await record_change(db, ctx, proposal_id=None, circle_id=cid[c["key"]], entity_type="circle", entity_id=cid[c["key"]], op="create",
                            before=None, after=snap, source="seed", summary=f"Created circle “{c['name']}”", at=created_at)

    # ---- roles
    rid: dict[str, UUID] = {}
    bid_v1 = ["Qualifying and acquiring new customer projects (project acquisition)", "Preparing bids and proposals"]
    for r in ROLES:
        rid[r["key"]] = await _ins(
            db,
            """INSERT INTO roles (organization_id, circle_id, name, purpose, allow_multiple, can_govern, created_by, updated_by)
               VALUES (:o, :c, :n, :p, :m, :g, :u, :u) RETURNING id""",
            o=org, c=cid[r["circle"]], n=r["name"], p=r["purpose"], m=r["multi"], g=r["can_govern"], u=uid["anna"],
        )
        acc = bid_v1 if r["key"] == "bid" else r["acc"]
        await _replace_items(db, ctx, "accountabilities", acc, role_id=rid[r["key"]])
        await _replace_items(db, ctx, "domains", r["dom"], role_id=rid[r["key"]])
        await _replace_items(db, ctx, "authorities", [{"text": t, "level": lvl} for t, lvl in r["aut"]], role_id=rid[r["key"]])
        snap = await role_snapshot(db, org, rid[r["key"]])
        await record_change(db, ctx, proposal_id=None, circle_id=cid[r["circle"]], entity_type="role", entity_id=rid[r["key"]], op="create",
                            before=None, after=snap, source="seed", summary=f"Created role “{r['name']}”", at=created_at)
        for person, focus in r["holders"]:
            await x(db, "INSERT INTO role_assignments (organization_id, role_id, user_id, focus, created_by) VALUES (:o, :r, :u, :f, :by)", o=org, r=rid[r["key"]], u=uid[person], f=focus, by=uid["anna"])
    await x(db, "UPDATE roles SET lead_user_id = :u WHERE id = :r", u=uid["jonas"], r=rid["innovation"])

    # ---- governance history: accepted proposal that extended the Bid Manager role 30 days ago
    p_hist = await _ins(
        db,
        """INSERT INTO governance_proposals (organization_id, circle_id, title, description, reason, expected_impact, proposal_type, workflow, status, changes,
                                             initiator_id, decided_by, decided_at, decision_note, created_at, updated_at)
           VALUES (:o, :c, 'Extend Bid Manager accountabilities with pipeline tracking', 'Add tracking of the bid pipeline and win rate to the Bid Manager role.',
                   'Nobody tracked how many bids we win; leadership lacked data.', 'Better forecast of project revenue.', 'change_accountabilities', 'consent', 'accepted',
                   '[]', :i, :d, :dt, 'No objections raised.', :ts, :dt) RETURNING id""",
        o=org, c=cid["cs"], i=uid["david"], d=uid["markus"], dt=_t(-30), ts=_t(-34),
    )
    before = await role_snapshot(db, org, rid["bid"])
    await _replace_items(db, ctx, "accountabilities", next(r for r in ROLES if r["key"] == "bid")["acc"], role_id=rid["bid"])
    after = await role_snapshot(db, org, rid["bid"])
    await record_change(db, ctx, proposal_id=p_hist, circle_id=cid["cs"], entity_type="role", entity_id=rid["bid"], op="update", before=before, after=after,
                        source="proposal", summary="Updated role “Bid Manager”", reason="Nobody tracked how many bids we win; leadership lacked data.", at=_t(-30))
    await x(db, "UPDATE governance_proposals SET changes = CAST(:c AS jsonb) WHERE id = :p", c=jb([{"op": "update_role", "id": str(rid["bid"]), "data": {"accountabilities": [{"text": t} for t in next(r for r in ROLES if r["key"] == "bid")["acc"]]}}]), p=p_hist)
    await x(db, "INSERT INTO governance_decisions (organization_id, circle_id, proposal_id, title, outcome, rationale, decided_by, created_at) VALUES (:o, :c, :p, 'Extend Bid Manager accountabilities with pipeline tracking', 'accepted', 'No objections raised.', :u, :ts)", o=org, c=cid["cs"], p=p_hist, u=uid["markus"], ts=_t(-30))

    # ---- open and closed proposals for the demo
    p_sla = await _ins(
        db,
        """INSERT INTO governance_proposals (organization_id, circle_id, title, description, reason, expected_impact, proposal_type, workflow, status, changes, initiator_id, created_at)
           VALUES (:o, :c, 'Create role Service Level Analyst', 'A new role that measures and reports service levels for all customer-facing services.',
                   'Service level reporting is done ad hoc and nobody feels accountable for it.', 'Transparent service levels; relief for the Service Operations Lead.',
                   'create_role', 'holacracy', 'objections', CAST(:ch AS jsonb), :i, :ts) RETURNING id""",
        o=org, c=cid["so"], ch=jb([{"op": "create_role", "data": {"circle_id": str(cid["so"]), "name": "Service Level Analyst", "purpose": "Service levels are measured transparently and drive improvement.",
                                                              "accountabilities": [{"text": "Measuring service level indicators for customer-facing services"}, {"text": "Publishing a monthly service level report"}],
                                                              "domains": [{"text": "Service level reports"}], "authorities": []}}]), i=uid["mira"], ts=_t(-6),
    )
    for author, kind, body, status in [
        ("felix", "question", "Which services are in scope for the first report?", "open"),
        ("mira", "answer", "All services with a customer contract; internal tools later.", "open"),
        ("clara", "reaction", "Sounds helpful. I would like the report to include satisfaction scores, too.", "open"),
        ("markus", "objection", "The role overlaps with my Service Operations Lead duty to define service level targets; as written it could make me lose decision authority over targets.", "open"),
    ]:
        await x(db, "INSERT INTO proposal_comments (organization_id, proposal_id, author_id, kind, body, status, created_at) VALUES (:o, :p, :u, :k, :b, :s, :ts)", o=org, p=p_sla, u=uid[author], k=kind, b=body, s=status, ts=_t(-5))

    new_cs_acc = [t for t in next(r for r in ROLES if r["key"] == "lead_cs")["acc"] if "personnel development" not in t]
    p_own = await _ins(
        db,
        """INSERT INTO governance_proposals (organization_id, circle_id, title, description, reason, expected_impact, proposal_type, workflow, status, changes, initiator_id, created_at)
           VALUES (:o, :c, 'Clarify ownership of personnel development', 'Remove personnel development coordination from the Customer Solutions Lead; the People Lead keeps it.',
                   'Two roles claim the coordination of personnel development, which leads to duplicate conversations.', 'One clear contact for personnel development.',
                   'change_accountabilities', 'consent', 'submitted', CAST(:ch AS jsonb), :i, :ts) RETURNING id""",
        o=org, c=cid["cs"], ch=jb([{"op": "update_role", "id": str(rid["lead_cs"]), "data": {"accountabilities": [{"text": t} for t in new_cs_acc]}}]), i=uid["sophie"], ts=_t(-2),
    )
    await x(db, "INSERT INTO proposal_comments (organization_id, proposal_id, author_id, kind, body) VALUES (:o, :p, :u, 'question', 'Does this affect the annual development talks that I run for my team?')", o=org, p=p_own, u=uid["markus"])

    p_rej = await _ins(
        db,
        """INSERT INTO governance_proposals (organization_id, circle_id, title, description, reason, expected_impact, proposal_type, workflow, status, changes, initiator_id,
                                             decided_by, decided_at, decision_note, created_at, updated_at)
           VALUES (:o, :c, 'Merge Quality Steward into Service Operations Lead', 'Remove the Quality Steward role and move its accountabilities to the Service Operations Lead.',
                   'Too many roles for a small circle.', 'Fewer roles to maintain.', 'remove_role', 'approval', 'rejected', '[]', :i, :d, :dt,
                   'Quality reviews need a second pair of eyes; the lead should not review their own deliverables.', :ts, :dt) RETURNING id""",
        o=org, c=cid["so"], i=uid["felix"], d=uid["anna"], dt=_t(-15), ts=_t(-18),
    )
    await x(db, "INSERT INTO governance_decisions (organization_id, circle_id, proposal_id, title, outcome, rationale, decided_by, created_at) VALUES (:o, :c, :p, 'Merge Quality Steward into Service Operations Lead', 'rejected', 'Quality reviews need a second pair of eyes; the lead should not review their own deliverables.', :u, :ts)", o=org, c=cid["so"], p=p_rej, u=uid["anna"], ts=_t(-15))

    t_ai = await _ins(
        db,
        """INSERT INTO tensions (organization_id, title, description, creator_id, context_type, circle_id, role_id, priority, status, created_by)
           VALUES (:o, 'AI work lacks a rule on responsible use', 'We experiment with LLMs on customer data but nobody has defined what is allowed.', :u, 'role', :c, :r, 'high', 'processing', :u) RETURNING id""",
        o=org, u=uid["ravi"], c=cid["vp"], r=rid["ai"],
    )
    p_ai = await _ins(
        db,
        """INSERT INTO governance_proposals (organization_id, circle_id, title, description, reason, expected_impact, proposal_type, workflow, status, changes, initiator_id, source_tension_id, created_at)
           VALUES (:o, :c, 'Add Responsible AI domain to the AI Specialist', 'The AI Specialist owns the guidelines for using AI on customer data.',
                   'Nobody defines what AI use is allowed on customer data.', 'Clear rules, fewer ad hoc decisions.', 'change_domains', 'approval', 'draft', CAST(:ch AS jsonb), :i, :t, :ts) RETURNING id""",
        o=org, c=cid["vp"], ch=jb([{"op": "update_role", "id": str(rid["ai"]), "data": {"domains": [{"text": "AI model evaluations"}, {"text": "Guidelines for responsible AI use on customer data"}]}}]), i=uid["ravi"], t=t_ai, ts=_t(-1),
    )
    await x(db, "UPDATE tensions SET outcome_type = 'proposal', outcome_ref_id = :p WHERE id = :t", p=p_ai, t=t_ai)

    # ---- more tensions
    tension_rows = [
        ("lena", "Customer feedback reaches the product team too late", "Feedback from delivery projects arrives weeks after it was given.", "role", "vp", "product", "high", "open", None),
        ("felix", "No clear owner for the deployment pipeline", "Pipeline failures wait days because nobody feels in charge.", "responsibility", "vp", None, "medium", "open", "Deployment pipeline operations"),
        ("clara", "UX reviews are skipped under bid pressure", "Bids go out without a usability check of the proposed solution.", "process", "cs", "ux", "medium", "open", "Bid review process"),
        ("sophie", "Onboarding checklist is outdated", "New members receive a checklist from two years ago.", "circle", "root", "people", "low", "open", None),
        ("david", "Unclear who decides on bids above 150 k EUR", "The policy says the Circle Lead reviews them, but the go/no-go authority sits with the Customer Solutions Lead.", "responsibility", "cs", "bid", "high", "open", "Go/no-go for large bids"),
    ]
    for who, title, desc, ctype, circ, role, prio, status, label in tension_rows:
        await x(
            db,
            """INSERT INTO tensions (organization_id, title, description, creator_id, context_type, circle_id, role_id, context_label, priority, status, created_by, created_at)
               VALUES (:o, :t, :d, :u, :ct, :c, :r, :l, :p, :s, :u, :ts)""",
            o=org, t=title, d=desc, u=uid[who], ct=ctype, c=cid[circ], r=rid[role] if role else None, l=label, p=prio, s=status, ts=_t(-3),
        )

    # ---- objectives, key results, metrics
    async def objective(circle: str, title: str, parent: UUID | None, role: str | None = None, period: str = "FY2025") -> UUID:
        return await _ins(db, "INSERT INTO objectives (organization_id, circle_id, role_id, parent_id, title, period, created_by, updated_by) VALUES (:o, :c, :r, :p, :t, :pe, :u, :u) RETURNING id",
                          o=org, c=cid[circle], r=rid[role] if role else None, p=parent, t=title, pe=period, u=uid["anna"])

    async def key_result(obj: UUID, title: str, unit: str, start: float, target: float, current: float) -> None:
        await x(db, "INSERT INTO key_results (organization_id, objective_id, title, unit, start_value, target_value, current_value) VALUES (:o, :ob, :t, :un, :s, :tg, :c)", o=org, ob=obj, t=title, un=unit, s=start, tg=target, c=current)

    o_root = await objective("root", "Grow sustainable customer business", None)
    await key_result(o_root, "Revenue from new customers", "kEUR", 0, 800, 520)
    await key_result(o_root, "Share of recurring revenue", "%", 20, 35, 27)
    o_cs = await objective("cs", "Win six strategic bids", o_root)
    await key_result(o_cs, "Bids submitted", "", 0, 12, 8)
    await key_result(o_cs, "Win rate", "%", 0, 35, 28)
    o_bid = await objective("cs", "Raise the quality of our bids", o_cs, "bid")
    await key_result(o_bid, "Bids reviewed by a second person", "%", 50, 100, 90)
    o_vp = await objective("vp", "Launch the AI assistant pilot", o_root)
    await key_result(o_vp, "Pilot customers onboarded", "", 0, 5, 2)
    await key_result(o_vp, "Pilot satisfaction (NPS)", "", 0, 40, 25)
    o_so = await objective("so", "Raise service reliability", o_root)
    await key_result(o_so, "Incidents acknowledged within 4 hours", "%", 80, 98, 91)

    metrics = [
        ("cs", None, "Bid win rate", "%", "up", 35, [18, 21, 24, 22, 26, 28], "quarterly"),
        ("cs", "bid", "Bids submitted per month", "", "up", 4, [2, 3, 3, 4, 2, 3], "monthly"),
        ("so", None, "Mean time to resolve incidents", "h", "down", 8, [14, 13, 12, 11, 11.5, 10.5], "monthly"),
        ("vp", None, "Active pilot users", "", "up", 200, [20, 45, 70, 90, 105, 120], "monthly"),
        ("root", None, "Employee satisfaction", "/5", "up", 4.2, [3.7, 3.8, 3.8, 3.9, 4.0, 4.0], "quarterly"),
    ]
    for circ, role, name, unit, direction, target, series, period in metrics:
        mid = await _ins(db, "INSERT INTO metrics (organization_id, circle_id, role_id, name, unit, direction, target_value, current_value, period, created_by) VALUES (:o, :c, :r, :n, :un, :d, :t, :cv, :p, :u) RETURNING id",
                         o=org, c=cid[circ], r=rid[role] if role else None, n=name, un=unit, d=direction, t=target, cv=series[-1], p=period, u=uid["anna"])
        for i, val in enumerate(series):
            await x(db, "INSERT INTO metric_readings (organization_id, metric_id, value, recorded_at) VALUES (:o, :m, :v, :ts)", o=org, m=mid, v=val, ts=_t(-30 * (len(series) - 1 - i)))

    # ---- projects, milestones, tasks
    projects = [
        ("tender", "cs", "bid", "Tender: Regional Hospital Platform", "Respond to the public tender for a patient portal platform.", "active", "high", -10, 21, o_bid, ["david", "clara", "markus"]),
        ("portal", "cs", "pm", "Customer Portal Relaunch", "Relaunch of a customer's self-service portal.", "active", "medium", -40, 60, o_cs, ["tobias", "clara", "felix"]),
        ("aipilot", "vp", "ai", "AI Assistant Pilot", "Pilot of an AI assistant with three early customers.", "active", "high", -25, 45, o_vp, ["ravi", "felix", "lena"]),
        ("desk", "so", "process", "Service Desk Automation", "Automate ticket routing and the first-response workflow.", "planned", "medium", 10, 90, o_so, ["mira", "felix"]),
        ("sprint", "root", "innovation", "Innovation Sprint Q3", "Cross-circle innovation sprint with external partners.", "on_hold", "low", 30, 75, None, ["jonas"]),
    ]
    pid: dict[str, UUID] = {}
    for key, circ, role, name, desc, status, prio, sd, dd, obj, people in projects:
        pid[key] = await _ins(db, """INSERT INTO projects (organization_id, circle_id, owning_role_id, name, description, status, priority, start_date, due_date, objective_id, created_by, updated_by)
                                     VALUES (:o, :c, :r, :n, :d, :s, :p, :sd, :dd, :ob, :u, :u) RETURNING id""",
                              o=org, c=cid[circ], r=rid[role], n=name, d=desc, s=status, p=prio, sd=_d(sd), dd=_d(dd), ob=obj, u=uid["anna"])
        for person in people:
            await x(db, "INSERT INTO project_people (organization_id, project_id, user_id) VALUES (:o, :p, :u)", o=org, p=pid[key], u=uid[person])
    for key, title, due, done in [("tender", "Qualification questionnaire submitted", -5, True), ("tender", "Final bid submitted", 18, False), ("portal", "Design system approved", -15, True),
                                  ("portal", "Beta release", 30, False), ("aipilot", "First customer live", -3, True), ("aipilot", "Third customer live", 35, False)]:
        await x(db, "INSERT INTO project_milestones (organization_id, project_id, title, due_date, done) VALUES (:o, :p, :t, :d, :dn)", o=org, p=pid[key], t=title, d=_d(due), dn=done)

    tasks = [
        ("tender", "bid", "david", "Draft the solution architecture chapter", "doing", "high", 3),
        ("tender", "bid", "david", "Collect customer references", "todo", "medium", -2),
        ("tender", "ux", "clara", "Prepare clickable prototype for the bid", "doing", "high", 6),
        ("tender", "lead_cs", "markus", "Go/no-go decision on the tender", "done", "high", -8),
        ("portal", "pm", "tobias", "Update the project plan after scope change", "todo", "medium", -4),
        ("portal", "swe", "felix", "Migrate authentication to the new identity provider", "blocked", "high", 5),
        ("portal", "ux", "clara", "Run usability tests with five end users", "todo", "medium", 12),
        ("aipilot", "ai", "ravi", "Evaluate three LLMs on the support dataset", "doing", "high", 2),
        ("aipilot", "product", "lena", "Interview pilot customers about missing features", "todo", "medium", 9),
        ("aipilot", "swe", "felix", "Add automated regression tests for the assistant", "todo", "low", -1),
        ("desk", "process", "mira", "Map the current ticket routing process", "done", "medium", -6),
        ("desk", "process", "mira", "Select automation tooling", "todo", "medium", 14),
        (None, "people", "sophie", "Refresh the onboarding checklist", "todo", "low", 20),
        (None, "secretary", "tobias", "Publish governance meeting minutes", "done", "low", -9),
    ]
    for proj, role, who, title, status, prio, due in tasks:
        circ = next(r["circle"] for r in ROLES if r["key"] == role)
        await x(
            db,
            """INSERT INTO tasks (organization_id, project_id, circle_id, role_id, assignee_id, title, status, priority, due_date, completed_at, created_by, updated_by)
               VALUES (:o, :p, :c, :r, :a, :t, :s, :pr, :d, CASE WHEN CAST(:s AS varchar) = 'done' THEN NOW() ELSE NULL END, :u, :u)""",
            o=org, p=pid[proj] if proj else None, c=cid[circ], r=rid[role], a=uid[who], t=title, s=status, pr=prio, d=_d(due), u=uid["anna"],
        )

    # ---- meetings
    m_tac = await _ins(db, """INSERT INTO meetings (organization_id, circle_id, title, meeting_type, scheduled_at, duration_min, facilitator_id, status, created_by, updated_by)
                              VALUES (:o, :c, 'Customer Solutions – weekly tactical', 'tactical', :ts, 60, :f, 'scheduled', :u, :u) RETURNING id""",
                       o=org, c=cid["cs"], ts=_t(2, 10), f=uid["markus"], u=uid["markus"])
    for person in ("markus", "david", "tobias", "clara"):
        await x(db, "INSERT INTO meeting_participants (organization_id, meeting_id, user_id) VALUES (:o, :m, :u)", o=org, m=m_tac, u=uid[person])
    tension_david = await q1(db, "SELECT id, title FROM tensions WHERE organization_id = :o AND title LIKE 'Unclear who decides%'", o=org)
    tension_clara = await q1(db, "SELECT id, title FROM tensions WHERE organization_id = :o AND title LIKE 'UX reviews%'", o=org)
    agenda = [("checkin", "Check-in round", None), ("checklist", "Checklist review", None), ("metrics", "Metrics review", None), ("projects", "Project updates", None),
              ("tension", tension_david["title"], tension_david["id"]), ("tension", tension_clara["title"], tension_clara["id"]), ("closing", "Closing round", None)]
    for pos, (kind, title, tid) in enumerate(agenda):
        await x(db, "INSERT INTO agenda_items (organization_id, meeting_id, position, title, kind, tension_id) VALUES (:o, :m, :p, :t, :k, :tid)", o=org, m=m_tac, p=pos, t=title, k=kind, tid=tid)

    m_gov = await _ins(db, """INSERT INTO meetings (organization_id, circle_id, title, meeting_type, scheduled_at, duration_min, facilitator_id, status, notes, checkin_notes, created_by, updated_by)
                              VALUES (:o, :c, 'Governance meeting – Services & Solutions', 'governance', :ts, 90, :f, 'completed', :n, 'Everyone present; short check-in on workload.', :u, :u) RETURNING id""",
                       o=org, c=cid["root"], ts=_t(-10, 14), f=uid["mira"], n="Reviewed the Innovation Catalyst role and agreed to revisit overlapping accountabilities with the Process Innovation Steward next quarter.", u=uid["mira"])
    for person in ("anna", "mira", "jonas", "sophie", "tobias"):
        await x(db, "INSERT INTO meeting_participants (organization_id, meeting_id, user_id, attended) VALUES (:o, :m, :u, TRUE)", o=org, m=m_gov, u=uid[person])
    for pos, (kind, title) in enumerate([("checkin", "Check-in round"), ("custom", "Proposals"), ("closing", "Closing round")]):
        await x(db, "INSERT INTO agenda_items (organization_id, meeting_id, position, title, kind, status) VALUES (:o, :m, :p, :t, :k, 'done')", o=org, m=m_gov, p=pos, t=title, k=kind)
    await x(db, "INSERT INTO governance_decisions (organization_id, circle_id, meeting_id, title, outcome, rationale, decided_by, created_at) VALUES (:o, :c, :m, 'Revisit innovation accountabilities next quarter', 'recorded', 'Both roles are new; collect experience first.', :u, :ts)", o=org, c=cid["root"], m=m_gov, u=uid["mira"], ts=_t(-10, 15))
    await x(db, "INSERT INTO tasks (organization_id, circle_id, role_id, assignee_id, meeting_id, title, status, due_date, created_by) VALUES (:o, :c, :r, :a, :m, 'Collect examples of overlapping innovation work', 'todo', :d, :u)", o=org, c=cid["root"], r=rid["innovation"], a=uid["jonas"], m=m_gov, d=_d(25), u=uid["mira"])

    # ---- notifications and audit trail
    for person, kind, title, link in [
        ("anna", "governance", "Proposal waiting: Create role Service Level Analyst", f"/governance/proposals/{p_sla}"),
        ("markus", "governance", "Proposal waiting: Clarify ownership of personnel development", f"/governance/proposals/{p_own}"),
        ("markus", "meeting", "Invitation: Customer Solutions – weekly tactical", f"/meetings/{m_tac}"),
        ("david", "task", "Task overdue: Collect customer references", "/work"),
    ]:
        await x(db, "INSERT INTO notifications (organization_id, user_id, kind, title, link) VALUES (:o, :u, :k, :t, :l)", o=org, u=uid[person], k=kind, t=title, l=link)
    for action, summary in [("demo.seeded", "Demonstration data created"), ("proposal.created", "Create role Service Level Analyst"), ("proposal.rejected", "Merge Quality Steward into Service Operations Lead")]:
        await x(db, "INSERT INTO audit_events (organization_id, actor_id, action, entity_type, summary) VALUES (:o, :u, :a, 'organization', :s)", o=org, u=uid["anna"], a=action, s=summary)
    return org
