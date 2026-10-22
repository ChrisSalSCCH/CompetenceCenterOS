"""End-to-end smoke test: starts the real app (migrations + demo seed) and calls every read
endpoint plus the deterministic assistant as the demo administrator.

Only runs when a real database is configured (it is skipped for the placeholder URL used
by hermetic unit-test runs). It is read-only apart from audit entries written by the AI endpoints.
"""

from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

PLACEHOLDER = "@localhost:5432/test"

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL") or PLACEHOLDER in os.environ.get("DATABASE_URL", ""),
    reason="needs a real database",
)

EXAMPLES = [
    "Who is responsible for customer acquisition?",
    "Who decides whether we accept a new customer project?",
    "Which roles are responsible for personnel development?",
    "What responsibilities overlap?",
    "Which roles currently have no assigned person?",
    "What changed in the organization last month?",
    "Which governance proposals are awaiting a decision?",
    "Which tasks are overdue in my circles?",
    "Suggest a role that coordinates innovation activities across multiple circles.",
    "Welche Rollen sind unbesetzt?",
]


def test_all_read_endpoints_and_assistant_work_on_demo_data():
    from database import engine
    from main import app

    failures: list[str] = []
    with TestClient(app) as client:
        try:
            login = client.post("/api/auth/demo-login", json={"email": "anna.berger@demo.circleos.app"})
            if login.status_code != 200:
                pytest.skip(f"demo organization not available: {login.status_code}")
            headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

            def get(path: str, **params):
                res = client.get(path, headers=headers, params=params)
                if res.status_code != 200:
                    failures.append(f"GET {path} {params} -> {res.status_code} {res.text[:300]}")
                    return None
                return res.json()

            session = get("/api/session")
            assert session and session["access_level"] == "org_admin"
            structure = get("/api/structure")
            assert structure and len(structure["roles"]) >= 15 and len(structure["circles"]) == 4
            assert get("/api/structure", as_of="2020-01-01T00:00:00Z")["circles"] == []
            get("/api/structure/analysis")
            root = next(c for c in structure["circles"] if c["parent_id"] is None)
            bid = next(r for r in structure["roles"] if r["name"] == "Bid Manager")
            get(f"/api/circles/{root['id']}")
            get(f"/api/circles/{root['id']}/dashboard")
            detail = get(f"/api/roles/{bid['id']}")
            assert detail and detail["history"], "Bid Manager has a versioned history"
            get("/api/role-templates")
            people = get("/api/people")
            assert people and len(people) == 12
            get(f"/api/people/{people[0]['id']}")
            get("/api/my-roles")
            get("/api/dashboard")
            hits = get("/api/search", q="project acquisition")
            assert hits and any(h["type"] == "role" and h["title"] == "Bid Manager" for h in hits["results"])
            resp = get("/api/responsibilities", q="accept a new customer project")
            assert resp and resp["roles"]
            get("/api/saved-filters")
            proposals = get("/api/proposals")
            assert proposals and len(proposals) >= 4
            for p in proposals:
                get(f"/api/proposals/{p['id']}")
            get("/api/governance/history")
            get("/api/governance/decisions")
            get("/api/tensions", scope="all")
            meetings = get("/api/meetings", scope="all")
            assert meetings and len(meetings) >= 2
            for m in meetings:
                get(f"/api/meetings/{m['id']}")
            projects = get("/api/projects")
            assert projects
            for p in projects:
                get(f"/api/projects/{p['id']}")
            tasks = get("/api/tasks")
            assert tasks
            get(f"/api/tasks/{tasks[0]['id']}")
            goals = get("/api/goals")
            assert goals and goals["objectives"] and goals["metrics"]
            get("/api/notifications")
            get("/api/admin/users")
            get("/api/admin/org")
            get("/api/admin/audit")
            get("/api/admin/ai")
            get("/api/admin/export")
            get("/api/ai/capabilities")

            for question in EXAMPLES:
                res = client.post("/api/ai/ask", headers=headers, json={"question": question, "lang": "en"})
                if res.status_code != 200:
                    failures.append(f"ASK {question!r} -> {res.status_code} {res.text[:300]}")
                    continue
                body = res.json()
                assert body["mode"] == "deterministic" and body["answer"]
            res = client.post("/api/ai/suggest-role", headers=headers, json={"brief": EXAMPLES[-2]})
            if res.status_code != 200:
                failures.append(f"suggest-role -> {res.status_code} {res.text[:300]}")

            unauth = client.get("/api/structure")
            assert unauth.status_code == 401
        finally:
            client.portal.call(engine.dispose)
    assert not failures, "\n".join(failures)
