"""Write-path smoke test against the live demonstration organization.

Opt-in (CIRCLEOS_WRITE_SMOKE=1) because it modifies data and finishes by resetting the
demo organization to its original sample content - which would discard manual demo edits.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi.testclient import TestClient

pytestmark = pytest.mark.skipif(
    os.environ.get("CIRCLEOS_WRITE_SMOKE") != "1",
    reason="opt-in: set CIRCLEOS_WRITE_SMOKE=1 (resets the demo organization afterwards)",
)


def test_write_flows_end_to_end():
    from database import engine
    from main import app

    failures: list[str] = []
    with TestClient(app) as client:
        try:
            def auth(email: str) -> dict[str, str]:
                res = client.post("/api/auth/demo-login", json={"email": email})
                assert res.status_code == 200, res.text
                return {"Authorization": f"Bearer {res.json()['access_token']}"}

            admin = auth("anna.berger@demo.circleos.app")
            member = auth("mira.hofer@demo.circleos.app")
            observer = auth("eva.lang@demo.circleos.app")

            def call(method: str, path: str, headers: dict[str, str], expect: int = 200, **kw):
                res = client.request(method, path, headers=headers, **kw)
                if res.status_code != expect:
                    failures.append(f"{method} {path} expected {expect} got {res.status_code}: {res.text[:300]}")
                    return {}
                return res.json() if res.content else {}

            structure = call("GET", "/api/structure", admin)
            circles = {c["name"]: c for c in structure["circles"]}
            roles = {r["name"]: r for r in structure["roles"]}
            vp, so = circles["Venture & Product"]["id"], circles["Service Operations"]["id"]

            # direct structural change in a direct-mode circle, versioned
            sub = call("POST", "/api/circles", admin, json={"parent_id": vp, "name": "Labs", "purpose": "Experiments"})
            assert sub["applied"] is True
            role = call("POST", "/api/roles", admin, json={"circle_id": sub["entity_id"], "name": "Lab Steward", "purpose": "p", "allow_multiple": True,
                                                          "accountabilities": [{"text": "Running experiments"}], "authorities": [{"text": "Stopping experiments", "level": "decides"}]})
            assert role["applied"] is True
            call("PATCH", f"/api/roles/{role['entity_id']}", admin, json={"purpose": "New purpose", "domains": [{"text": "Lab budget"}]})
            detail = call("GET", f"/api/roles/{role['entity_id']}", admin)
            assert len(detail["history"]) == 2 and detail["purpose"] == "New purpose"
            call("POST", f"/api/roles/{role['entity_id']}/assignments", admin, json={"user_id": session_id(client, admin), "focus": "x"})
            call("PATCH", f"/api/circles/{vp}", admin, 409, json={"parent_id": sub["entity_id"]})
            call("DELETE", f"/api/circles/{sub['entity_id']}", admin, 409)  # not empty
            old = call("GET", f"/api/structure?as_of=2020-01-01T00:00:00Z", admin)
            assert old["roles"] == []

            # observer is read-only; member needs governance
            call("POST", "/api/tensions", observer, 403, json={"title": "Not allowed"})
            denied = call("POST", "/api/roles", member, json={"circle_id": circles["Services & Solutions"]["id"], "name": "Proposed Role"})
            assert denied["applied"] is False
            call("POST", f"/api/proposals/{denied['proposal_id']}/decide", member, 403, json={"outcome": "accepted"})

            # proposal lifecycle: comments, objection blocks consent, acceptance applies transactionally
            pr = call("POST", "/api/proposals", member, json={
                "circle_id": so, "title": "Create role Metrics Analyst", "submit": True,
                "changes": [{"op": "create_role", "data": {"circle_id": so, "name": "Metrics Analyst", "purpose": "p"}}]})
            call("POST", f"/api/proposals/{pr['id']}/comments", admin, json={"kind": "question", "body": "Why now?"})
            call("POST", f"/api/proposals/{pr['id']}/comments", admin, 409, json={"kind": "objection", "body": "This is an objection text"})
            before = len(call("GET", "/api/structure", admin)["roles"])
            call("POST", f"/api/proposals/{pr['id']}/decide", admin, json={"outcome": "accepted", "rationale": "fine"})
            assert len(call("GET", "/api/structure", admin)["roles"]) == before + 1

            # consent circle: objection blocks until withdrawn
            cs = circles["Customer Solutions"]["id"]
            pc = call("POST", "/api/proposals", member, json={"circle_id": cs, "title": "Consent test", "submit": True, "changes": [{"op": "create_role", "data": {"circle_id": cs, "name": "Consent Role"}}]})
            ob = call("POST", f"/api/proposals/{pc['id']}/comments", admin, json={"kind": "objection", "body": "A real objection with reason"})
            call("POST", f"/api/proposals/{pc['id']}/decide", admin, 409, json={"outcome": "accepted"})
            call("PATCH", f"/api/proposal-comments/{ob['id']}", admin, json={"status": "resolved"})
            call("POST", f"/api/proposals/{pc['id']}/decide", admin, json={"outcome": "rejected", "rationale": "not needed"})

            # tensions -> task / proposal / resolution
            t1 = call("POST", "/api/tensions", member, json={"title": "Handover loses context", "circle_id": so})
            call("POST", f"/api/tensions/{t1['id']}/convert", member, json={"to": "task", "title": "Write handover template"})
            t2 = call("POST", "/api/tensions", member, json={"title": "Unclear owner of runbooks", "circle_id": so})
            conv = call("POST", f"/api/tensions/{t2['id']}/convert", member, json={"to": "proposal"})
            call("PATCH", f"/api/proposals/{conv['outcome_ref_id']}", member, json={"changes": [{"op": "update_role", "id": roles["Quality Steward"]["id"], "data": {"domains": [{"text": "Runbooks"}]}}]})
            call("POST", f"/api/proposals/{conv['outcome_ref_id']}/submit", member)
            t3 = call("POST", "/api/tensions", member, json={"title": "Minor annoyance"})
            call("POST", f"/api/tensions/{t3['id']}/convert", member, json={"to": "resolution", "note": "Fixed by talking"})
            call("GET", "/api/tensions?scope=mine", member)

            # work: project, milestone, tasks, comments, status changes
            pj = call("POST", "/api/projects", admin, json={"name": "Smoke project", "circle_id": vp, "owning_role_id": roles["Product Manager"]["id"], "person_ids": [session_id(client, admin)]})
            call("POST", f"/api/projects/{pj['id']}/milestones", admin, json={"title": "M1"})
            tk = call("POST", "/api/tasks", admin, json={"title": "Smoke task", "project_id": pj["id"], "assignee_id": session_id(client, admin), "due_date": "2020-01-01"})
            call("PATCH", f"/api/tasks/{tk['id']}", admin, json={"status": "doing"})
            call("PATCH", f"/api/tasks/{tk['id']}", observer, 403, json={"status": "done"})
            call("POST", f"/api/tasks/{tk['id']}/comments", admin, json={"body": "hello"})
            call("POST", "/api/attachments", admin, json={"entity_type": "task", "entity_id": tk["id"], "name": "Doc", "url": "https://example.org/doc"})
            overdue = call("GET", "/api/tasks?overdue=true", admin)
            assert any(x["id"] == tk["id"] and x["is_overdue"] for x in overdue)
            call("PATCH", f"/api/projects/{pj['id']}", admin, json={"status": "active"})

            # goals
            ob_ = call("POST", "/api/objectives", admin, json={"circle_id": vp, "title": "Smoke objective"})
            kr = call("POST", f"/api/objectives/{ob_['id']}/key-results", admin, json={"title": "Smoke KR", "target_value": 10})
            call("PATCH", f"/api/key-results/{kr['id']}", admin, json={"current_value": 5})
            mt = call("POST", "/api/metrics", admin, json={"circle_id": vp, "name": "Smoke KPI", "target_value": 10})
            call("POST", f"/api/metrics/{mt['id']}/readings", admin, json={"value": 7})

            # meetings
            mtg = call("POST", "/api/meetings", admin, json={"circle_id": vp, "title": "Smoke meeting", "meeting_type": "tactical", "scheduled_at": "2030-01-01T10:00:00Z"})
            call("POST", f"/api/meetings/{mtg['id']}/start", admin)
            call("POST", f"/api/meetings/{mtg['id']}/agenda", admin, json={"title": "Extra topic"})
            call("POST", f"/api/meetings/{mtg['id']}/decisions", admin, json={"title": "We decided"})
            call("POST", f"/api/meetings/{mtg['id']}/step", admin, json={"step": 2})
            call("POST", f"/api/meetings/{mtg['id']}/finish", admin)
            call("GET", f"/api/meetings/{mtg['id']}", admin)

            # admin
            email = f"smoke-{uuid.uuid4().hex[:8]}@demo-smoke.org"
            usr = call("POST", "/api/admin/users", admin, json={"email": email, "display_name": "Smoke User", "password": "Smoke-Password-1", "access_level": "observer"})
            call("POST", f"/api/admin/users/{usr['id']}/password", admin, json={"password": "Another-Password-2"})
            call("PATCH", f"/api/admin/users/{usr['id']}", admin, json={"active": False})
            call("GET", "/api/admin/users", member, 403)
            call("PUT", "/api/admin/ai", admin, json={"name": "x", "base_url": "https://llm.invalid/v1", "model": "m", "api_key": "secret", "enabled": False})
            cfg = call("GET", "/api/admin/ai", admin)
            assert cfg["has_key"] is True and "api_key" not in cfg
            call("POST", "/api/saved-filters", admin, json={"name": "s", "query": "bid"})
            call("POST", "/api/notifications/read-all", admin)
            call("PATCH", "/api/me/profile", admin, json={"skills": ["a", "b"], "notification_prefs": {"tasks": False}})
            call("POST", "/api/admin/reset-demo", admin)
            fresh = auth("anna.berger@demo.circleos.app")
            assert len(call("GET", "/api/structure", fresh)["roles"]) == 18
        finally:
            client.portal.call(engine.dispose)
    assert not failures, "\n".join(failures)


def session_id(client: TestClient, headers: dict[str, str]) -> str:
    return client.get("/api/session", headers=headers).json()["user"]["id"]
