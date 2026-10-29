"""Commercial process API checks against the demonstration organization.

Runs only with a real database. Temporary rows are soft-deleted by the tests themselves.
"""

from __future__ import annotations

import os
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

PLACEHOLDER = "@localhost:5432/test"

pytestmark = pytest.mark.skipif(
    not os.environ.get("DATABASE_URL") or PLACEHOLDER in os.environ.get("DATABASE_URL", ""),
    reason="needs a real database",
)


@contextmanager
def _client():
    """TestClient that releases pooled connections, so the next test can open its own event loop."""
    from database import engine
    from main import app

    with TestClient(app) as client:
        try:
            yield client
        finally:
            client.portal.call(engine.dispose)


def _code(res) -> str:
    return res.json().get("error", {}).get("code", "")


def _login(client: TestClient, email: str) -> dict[str, str]:
    res = client.post("/api/auth/demo-login", json={"email": email})
    if res.status_code != 200:
        pytest.skip(f"demo organization not available: {res.status_code}")
    return {"Authorization": f"Bearer {res.json()['access_token']}"}


def test_opportunity_lifecycle():
    with _client() as client:
        admin = _login(client, "anna.berger@demo.circleos.app")
        member = _login(client, "felix.steiner@demo.circleos.app")
        observer = _login(client, "eva.lang@demo.circleos.app")
        orgs = client.get("/api/crm/organizations", headers=admin, params={"relation": "customer"}).json()
        if not orgs:
            pytest.skip("no CRM demonstration data")
        opp_id = None
        try:
            # ---- create + numbering
            res = client.post("/api/commercial/opportunities", headers=admin, json={
                "title": "Test opportunity pipeline", "crm_org_id": orgs[0]["id"], "value_amount": "10000.00", "currency": "EUR", "category": "development",
            })
            assert res.status_code == 200, res.text
            opp_id = res.json()["id"]
            assert res.json()["number"].startswith("OPP-")
            assert client.post("/api/commercial/opportunities", headers=observer, json={"title": "Observer try", "crm_org_id": orgs[0]["id"]}).status_code == 403

            detail = client.get(f"/api/commercial/opportunities/{opp_id}", headers=admin).json()
            assert detail["stage"] == "lead" and detail["effective_probability"] == 10
            assert float(detail["weighted_value"]) == 1000.0

            # ---- money is hidden from observers
            seen = client.get(f"/api/commercial/opportunities/{opp_id}", headers=observer).json()
            assert seen["value_amount"] is None and seen["weighted_value"] is None

            # ---- manual probability override
            assert client.patch(f"/api/commercial/opportunities/{opp_id}", headers=admin, json={"probability": 40}).status_code == 200
            detail = client.get(f"/api/commercial/opportunities/{opp_id}", headers=admin).json()
            assert detail["effective_probability"] == 40 and float(detail["weighted_value"]) == 4000.0

            # ---- stage rules
            res = client.post(f"/api/commercial/opportunities/{opp_id}/stage", headers=admin, json={"stage": "lost"})
            assert res.status_code == 422 and _code(res) == "LOST_REASON_REQUIRED"
            res = client.post(f"/api/commercial/opportunities/{opp_id}/stage", headers=admin, json={"stage": "proposal"})
            assert res.status_code == 422 and _code(res) == "BID_DECISION_REQUIRED"
            assert client.post(f"/api/commercial/opportunities/{opp_id}/stage", headers=admin, json={"stage": "qualification"}).status_code == 200

            # ---- pipeline and list reflect the move
            pipe = client.get("/api/commercial/pipeline", headers=admin).json()
            qual = next(s for s in pipe["stages"] if s["stage"] == "qualification")
            assert qual["count"] >= 1 and qual["value"]["EUR"] is not None
            assert client.get("/api/commercial/pipeline", headers=observer).json()["stages"][0]["value"] is None
            listed = client.get("/api/commercial/opportunities", headers=admin, params={"stage": "qualification"}).json()
            assert any(r["id"] == opp_id for r in listed)

            # ---- loss needs a reason, closes the opportunity, and only an admin reopens it
            assert client.post(f"/api/commercial/opportunities/{opp_id}/stage", headers=admin, json={"stage": "lost", "lost_reason": "Budget cut"}).status_code == 200
            closed = client.get(f"/api/commercial/opportunities/{opp_id}", headers=admin).json()
            assert closed["effective_probability"] == 0 and closed["lost_reason"] == "Budget cut"
            chain = client.get(f"/api/commercial/opportunities/{opp_id}/chain", headers=admin).json()
            assert chain["lost"] is True and chain["steps"][0]["status"] == "done"
            history = client.get(f"/api/commercial/opportunities/{opp_id}/history", headers=admin).json()
            assert any(h["action"] == "opportunity.stage_changed" for h in history)
            assert client.post(f"/api/commercial/opportunities/{opp_id}/stage", headers=member, json={"stage": "lead"}).status_code in (403, 404)
        finally:
            if opp_id:
                client.delete(f"/api/commercial/opportunities/{opp_id}", headers=admin)


def _tamper_locked_version(version_id: str) -> str:
    """Try to change a locked version directly in the database; returns the outcome."""
    import asyncio

    import asyncpg
    from db.migrations import _asyncpg_dsn

    async def run() -> str:
        conn = await asyncpg.connect(_asyncpg_dsn(os.environ["DATABASE_URL"]))
        try:
            schema = os.environ.get("DATABASE_SCHEMA")
            if schema:
                await conn.execute(f'SET search_path TO "{schema}"')
            await conn.execute("UPDATE proposal_versions SET price_total = 1 WHERE id = $1", version_id)
            return "changed"
        except asyncpg.exceptions.CheckViolationError:
            return "blocked"
        finally:
            await conn.close()

    return asyncio.run(run())


def _exec_sql(sql: str, *args: str) -> None:
    """Test cleanup straight in the database (signed records have no delete endpoint by design)."""
    import asyncio

    import asyncpg
    from db.migrations import _asyncpg_dsn

    async def run() -> None:
        conn = await asyncpg.connect(_asyncpg_dsn(os.environ["DATABASE_URL"]))
        try:
            schema = os.environ.get("DATABASE_SCHEMA")
            if schema:
                await conn.execute(f'SET search_path TO "{schema}"')
            await conn.execute(sql, *args)
        finally:
            await conn.close()

    asyncio.run(run())


def test_nda_and_contract_rules():
    from datetime import date, timedelta

    with _client() as client:
        admin = _login(client, "anna.berger@demo.circleos.app")
        member = _login(client, "felix.steiner@demo.circleos.app")
        observer = _login(client, "eva.lang@demo.circleos.app")
        orgs = client.get("/api/crm/organizations", headers=admin, params={"relation": "customer"}).json()
        if not orgs:
            pytest.skip("no CRM demonstration data")
        nda_ids: list[str] = []
        contract_ids: list[str] = []
        try:
            # ---- NDA: only the creator, customer owner or admin edits; signing needs authority
            soon = (date.today() + timedelta(days=20)).isoformat()
            res = client.post("/api/commercial/ndas", headers=admin, json={"crm_org_id": orgs[0]["id"], "title": "Test NDA coverage", "valid_to": soon})
            assert res.status_code == 200, res.text
            nda = res.json()["id"]
            nda_ids.append(nda)
            assert res.json()["number"].startswith("NDA-")
            assert client.get(f"/api/commercial/ndas/{nda}", headers=admin).json()["coverage"] == "draft"
            assert client.post(f"/api/commercial/ndas/{nda}/sign", headers=member, json={}).status_code == 403
            res = client.post(f"/api/commercial/ndas/{nda}/sign", headers=admin, json={})
            assert res.status_code == 422 and _code(res) == "OVERRIDE_NOTE_REQUIRED"
            assert client.post(f"/api/commercial/ndas/{nda}/sign", headers=admin, json={"override_note": "No NDA signature rule yet", "signatory_name": "A. Berger"}).status_code == 200
            cov = client.get("/api/commercial/nda-coverage", headers=member, params={"crm_org_id": orgs[0]["id"]}).json()
            assert cov["state"] in ("active", "expiring") and "publication" in cov["notice"]
            assert client.delete(f"/api/commercial/ndas/{nda}", headers=admin).status_code == 409
            assert client.post("/api/commercial/reminders/run", headers=admin).status_code == 200
            assert client.post("/api/commercial/reminders/run", headers=admin).json()["sent"] == 0, "each reminder is sent once"
            assert any(r["entity_id"] == nda and r["kind"] == "expires_soon" for r in client.get("/api/commercial/reminders", headers=admin).json())

            # ---- contracts: framework + call-off, conditions visibility, amendments
            fw = client.post("/api/commercial/contracts", headers=admin, json={
                "crm_org_id": orgs[0]["id"], "title": "Test framework agreement", "contract_kind": "framework", "value_amount": "100000",
                "valid_from": "2026-01-01", "valid_to": "2030-12-31",
            })
            assert fw.status_code == 200, fw.text
            contract_ids.append(fw.json()["id"])
            projects = client.get("/api/portfolio", headers=admin).json()
            call = client.post("/api/commercial/contracts", headers=admin, json={
                "crm_org_id": orgs[0]["id"], "title": "Test call-off", "parent_contract_id": fw.json()["id"], "value_amount": "20000",
                "project_ids": [p["id"] for p in projects[:2]],
            })
            assert call.status_code == 200, call.text
            contract_ids.append(call.json()["id"])
            bad = client.post("/api/commercial/contracts", headers=admin, json={"crm_org_id": orgs[0]["id"], "title": "Child of a call-off", "parent_contract_id": call.json()["id"]})
            assert bad.status_code == 422 and _code(bad) == "PARENT_NOT_FRAMEWORK"
            detail = client.get(f"/api/commercial/contracts/{fw.json()['id']}", headers=admin).json()
            assert [c["id"] for c in detail["children"]] == [call.json()["id"]] and float(detail["value_amount"]) == 100000.0
            linked = client.get(f"/api/commercial/contracts/{call.json()['id']}", headers=admin).json()
            assert len(linked["projects"]) == len(projects[:2])

            # conditions only for people with a reason
            for who in (member, observer):
                seen = client.get(f"/api/commercial/contracts/{fw.json()['id']}", headers=who).json()
                assert seen["value_amount"] is None and seen["terms_visible"] is False
            assert all(c["value_amount"] is None for c in client.get("/api/commercial/contracts", headers=observer).json())

            res = client.post(f"/api/commercial/contracts/{fw.json()['id']}/sign", headers=admin, json={"override_note": "No signature rule yet"})
            assert res.status_code == 200 and res.json()["admin_override"] is True
            res = client.patch(f"/api/commercial/contracts/{fw.json()['id']}", headers=admin, json={"value_amount": "1"})
            assert res.status_code == 409 and _code(res) == "USE_AMENDMENT"
            assert client.post(f"/api/commercial/contracts/{fw.json()['id']}/amendments", headers=admin, json={"title": "Increase", "value_delta": "5000", "new_valid_to": "2031-06-30", "signed": True}).status_code == 200
            after = client.get(f"/api/commercial/contracts/{fw.json()['id']}", headers=admin).json()
            assert float(after["value_amount"]) == 105000.0 and after["valid_to"] == "2031-06-30" and after["state"] == "active"
            assert client.delete(f"/api/commercial/contracts/{fw.json()['id']}", headers=admin).status_code == 409
        finally:
            for cid in contract_ids:
                _exec_sql("UPDATE contracts SET deleted_at = NOW() WHERE id = $1::uuid", cid)
            for nid in nda_ids:
                _exec_sql("UPDATE ndas SET deleted_at = NOW() WHERE id = $1::uuid", nid)


def test_document_confidentiality_and_versions():
    with _client() as client:
        admin = _login(client, "anna.berger@demo.circleos.app")
        member = _login(client, "felix.steiner@demo.circleos.app")
        observer = _login(client, "eva.lang@demo.circleos.app")
        orgs = client.get("/api/crm/organizations", headers=admin, params={"relation": "customer"}).json()
        users = client.get("/api/people", headers=admin).json()
        if not orgs:
            pytest.skip("no CRM demonstration data")
        felix = next((u for u in (users if isinstance(users, list) else users.get("items", [])) if str(u.get("name", u.get("display_name", ""))).startswith("Felix")), None)
        opp_id = None
        try:
            opp_id = client.post("/api/commercial/opportunities", headers=admin, json={"title": "Document test opportunity", "crm_org_id": orgs[0]["id"]}).json()["id"]
            scope = {"entity_type": "opportunity", "entity_id": opp_id}
            base = {**scope, "storage_kind": "link", "url": "https://example.com/spec.pdf"}
            internal = client.post("/api/documents", headers=admin, json={**base, "name": "Public spec"})
            secret = client.post("/api/documents", headers=admin, json={**base, "name": "Pricing sheet", "confidentiality": "confidential", "category": "proposal"})
            assert internal.status_code == 200 and secret.status_code == 200, secret.text

            # ---- the list and the download respect confidentiality
            seen = client.get("/api/documents", headers=member, params=scope).json()
            assert [d["name"] for d in seen["items"]] == ["Public spec"] and seen["hidden_count"] == 1
            assert client.get(f"/api/documents/{secret.json()['id']}/download", headers=member).status_code == 404
            assert client.get(f"/api/documents/{secret.json()['id']}", headers=observer).status_code == 404
            assert [d["name"] for d in client.get("/api/documents", headers=observer, params=scope).json()["items"]] == ["Public spec"]
            assert len(client.get("/api/documents", headers=admin, params=scope).json()["items"]) == 2

            # ---- the access list opens a confidential document and the download is audited
            if felix:
                uid = felix.get("user_id") or felix["id"]
                assert client.patch(f"/api/documents/{secret.json()['id']}", headers=admin, json={"access_user_ids": [uid]}).status_code == 200
                got = client.get(f"/api/documents/{secret.json()['id']}/download", headers=member)
                assert got.status_code == 200 and got.json()["url"] == "https://example.com/spec.pdf"
            history = client.get(f"/api/commercial/opportunities/{opp_id}/history", headers=admin).json()
            assert any(h["action"] == "document.created" for h in history)

            # ---- versions
            res = client.post(f"/api/documents/{internal.json()['id']}/versions", headers=admin, json={"storage_kind": "link", "url": "https://example.com/spec-v2.pdf", "comment": "Revised"})
            assert res.status_code == 200 and res.json()["version_no"] == 2
            detail = client.get(f"/api/documents/{internal.json()['id']}", headers=admin).json()
            assert detail["current_version"] == 2 and len(detail["versions"]) == 2
            old = client.get(f"/api/documents/{internal.json()['id']}/download", headers=admin, params={"version": 1}).json()
            assert old["url"].endswith("spec.pdf")

            # ---- uploads must be finalized by the caller; invented keys and read-only users are refused
            res = client.post("/api/documents", headers=admin, json={**scope, "name": "Fake file", "storage_kind": "file", "file_key": "private/someone-else/file.pdf"})
            assert res.status_code == 404 and _code(res) == "FILE_NOT_FOUND"
            assert client.post("/api/documents", headers=observer, json={**base, "name": "Observer doc"}).status_code == 403
            res = client.post("/api/documents", headers=admin, json={**scope, "name": "Bad link", "storage_kind": "link", "url": "javascript:alert(1)"})
            assert res.status_code == 422
            assert client.delete(f"/api/documents/{internal.json()['id']}", headers=admin).status_code == 200
        finally:
            if opp_id:
                client.delete(f"/api/commercial/opportunities/{opp_id}", headers=admin)


def test_conversion_into_projects():
    with _client() as client:
        admin = _login(client, "anna.berger@demo.circleos.app")
        orgs = client.get("/api/crm/organizations", headers=admin, params={"relation": "customer"}).json()
        circles = client.get("/api/structure", headers=admin).json()["circles"]
        if not orgs or not circles:
            pytest.skip("no demonstration data")
        opp_ids: list[str] = []
        project_ids: list[str] = []
        contract_ids: list[str] = []
        try:
            def won_opportunity(title: str, with_proposal: bool) -> str:
                opp = client.post("/api/commercial/opportunities", headers=admin, json={"title": title, "crm_org_id": orgs[0]["id"], "circle_id": circles[0]["id"], "value_amount": "30000", "category": "development", "description": "From the sales process"})
                assert opp.status_code == 200, opp.text
                oid = opp.json()["id"]
                opp_ids.append(oid)
                assert client.post(f"/api/commercial/opportunities/{oid}/bid/decision", headers=admin, json={"decision": "bid", "rationale": "Go", "override_note": "Test"}).status_code == 200
                if with_proposal:
                    created = client.post("/api/commercial/proposals", headers=admin, json={"opportunity_id": oid, "title": "Conversion proposal"}).json()
                    pid, vid = created["id"], created["version_id"]
                    content = {
                        "work_packages": [{"code": "WP1", "title": "Analysis", "milestone_title": "Analysis done", "milestone_due": "2026-12-01"}, {"code": "WP2", "title": "Build"}],
                        "lines": [{"description": "Work", "quantity": "20", "unit": "day", "unit_cost": "500", "unit_price": "900", "wp_index": 0}],
                    }
                    assert client.put(f"/api/commercial/proposals/{pid}/versions/{vid}", headers=admin, json=content).status_code == 200
                    assert client.post(f"/api/commercial/proposals/{pid}/versions/{vid}/request-approval", headers=admin).status_code == 200
                    step = client.get(f"/api/commercial/proposals/{pid}/versions/{vid}", headers=admin).json()["approvals"][0]
                    assert client.post(f"/api/commercial/proposals/{pid}/versions/{vid}/approvals/{step['id']}", headers=admin, json={"decision": "approve", "note": "Test approval"}).status_code == 200
                    assert client.post(f"/api/commercial/proposals/{pid}/versions/{vid}/submit", headers=admin).status_code == 200
                    assert client.post(f"/api/commercial/proposals/{pid}/outcome", headers=admin, json={"outcome": "accepted"}).status_code == 200
                else:
                    assert client.post(f"/api/commercial/opportunities/{oid}/stage", headers=admin, json={"stage": "won"}).status_code == 200
                return oid

            # ---- not won yet
            early = client.post("/api/commercial/opportunities", headers=admin, json={"title": "Not yet won", "crm_org_id": orgs[0]["id"], "circle_id": circles[0]["id"]}).json()["id"]
            opp_ids.append(early)
            res = client.post(f"/api/commercial/opportunities/{early}/convert", headers=admin, json={})
            assert res.status_code == 409 and _code(res) == "OPPORTUNITY_NOT_WON"

            # ---- new project with work packages, milestones and budget
            oid = won_opportunity("Conversion test opportunity", True)
            contract = client.post("/api/commercial/contracts", headers=admin, json={"crm_org_id": orgs[0]["id"], "title": "Conversion contract", "opportunity_id": oid}).json()
            contract_ids.append(contract["id"])
            preview = client.get(f"/api/commercial/opportunities/{oid}/convert-preview", headers=admin).json()
            assert preview["can_convert"] and preview["mode"] == "new" and preview["source_proposal"]["version_no"] == 1
            assert preview["will_link"]["work_packages"] == 2 and preview["will_link"]["milestones"] == 1 and preview["will_link"]["contracts"] == 1
            assert {r["field"] for r in preview["fields"]} >= {"name", "budget_total", "effort_days"}
            done = client.post(f"/api/commercial/opportunities/{oid}/convert", headers=admin, json={})
            assert done.status_code == 200, done.text
            project_ids.append(done.json()["project_id"])
            assert done.json()["created"] is True and done.json()["work_packages"] == 2
            project = client.get(f"/api/portfolio/{done.json()['project_id']}", headers=admin).json()
            assert project["classification"] == "customer" and project["source_opportunity_id"] == oid
            assert len(project["work_packages"]) == 2 and any(o["id"] == orgs[0]["id"] and o["relation"] == "customer" for o in project["orgs"])
            assert float(project["finance"]["data"]["budget_total"]) == 18000.0 and float(project["effort_days"]) == 20.0
            linked = client.get(f"/api/commercial/contracts/{contract['id']}", headers=admin).json()
            assert [p["id"] for p in linked["projects"]] == [done.json()["project_id"]]
            again = client.post(f"/api/commercial/opportunities/{oid}/convert", headers=admin, json={})
            assert again.status_code == 409 and _code(again) == "ALREADY_CONVERTED"
            assert client.get(f"/api/commercial/opportunities/{oid}", headers=admin).json()["project_id"] == done.json()["project_id"]

            # ---- existing project: empty fields are filled, differing ones only on request
            existing = client.post("/api/portfolio", headers=admin, json={"name": "Existing internal project", "circle_id": circles[0]["id"], "classification": "internal", "description": ""}).json()["id"]
            project_ids.append(existing)
            second = won_opportunity("Second conversion opportunity", False)
            plan = client.get(f"/api/commercial/opportunities/{second}/convert-preview", headers=admin, params={"project_id": existing}).json()
            actions = {r["field"]: r["action"] for r in plan["fields"]}
            assert plan["mode"] == "existing" and actions["classification"] == "conflict" and actions["description"] == "fill" and actions["name"] == "conflict"
            res = client.post(f"/api/commercial/opportunities/{second}/convert", headers=admin, json={"project_id": existing})
            assert res.status_code == 200 and res.json()["created"] is False
            enriched = client.get(f"/api/portfolio/{existing}", headers=admin).json()
            assert enriched["classification"] == "internal" and enriched["name"] == "Existing internal project" and enriched["description"] == "From the sales process"
            assert enriched["source_opportunity_id"] == second
        finally:
            for pid in project_ids:
                _exec_sql("UPDATE projects SET deleted_at = NOW() WHERE id = $1::uuid", pid)
            for cid in contract_ids:
                _exec_sql("UPDATE contracts SET deleted_at = NOW() WHERE id = $1::uuid", cid)
            for oid in opp_ids:
                _exec_sql("UPDATE opportunities SET deleted_at = NOW() WHERE id = $1::uuid", oid)


def test_proposal_calculation_versions_and_locking():
    with _client() as client:
        admin = _login(client, "anna.berger@demo.circleos.app")
        member = _login(client, "felix.steiner@demo.circleos.app")
        observer = _login(client, "eva.lang@demo.circleos.app")
        orgs = client.get("/api/crm/organizations", headers=admin, params={"relation": "customer"}).json()
        if not orgs:
            pytest.skip("no CRM demonstration data")
        opp_ids: list[str] = []
        try:
            def new_opp(title: str) -> str:
                res = client.post("/api/commercial/opportunities", headers=admin, json={"title": title, "crm_org_id": orgs[0]["id"], "value_amount": "10000.00"})
                assert res.status_code == 200, res.text
                opp_ids.append(res.json()["id"])
                return res.json()["id"]

            opp = new_opp("Proposal test opportunity")
            base = f"/api/commercial/opportunities/{opp}"
            res = client.post("/api/commercial/proposals", headers=admin, json={"opportunity_id": opp, "title": "Too early"})
            assert res.status_code == 422 and _code(res) == "BID_DECISION_REQUIRED"
            res = client.post(f"{base}/bid/decision", headers=admin, json={"decision": "bid", "rationale": "Go", "override_note": "Test without rule"})
            assert res.status_code == 200, res.text

            created = client.post("/api/commercial/proposals", headers=admin, json={"opportunity_id": opp, "title": "Platform proposal"})
            assert created.status_code == 200, created.text
            pid, v1 = created.json()["id"], created.json()["version_id"]
            assert created.json()["number"].startswith("ANG-")

            # ---- calculation: rounding, effort, margin
            content = {
                "summary": "First offer", "scope_text": "Build the platform",
                "work_packages": [{"code": "WP1", "title": "Implementation"}],
                "lines": [
                    {"description": "Development", "quantity": "10", "unit": "day", "unit_cost": "600", "unit_price": "1000", "wp_index": 0},
                    {"line_kind": "travel", "description": "On-site", "quantity": "1", "unit": "piece", "unit_cost": "300.25", "unit_price": "500.50"},
                ],
            }
            saved = client.put(f"/api/commercial/proposals/{pid}/versions/{v1}", headers=admin, json=content)
            assert saved.status_code == 200, saved.text
            assert float(saved.json()["price_total"]) == 10500.5 and float(saved.json()["margin_pct"]) == 40.0 and float(saved.json()["effort_days"]) == 10.0
            foreign = {"lines": [{"description": "USD item", "quantity": "1", "unit_cost": "1", "unit_price": "2", "currency": "USD"}]}
            res = client.put(f"/api/commercial/proposals/{pid}/versions/{v1}", headers=admin, json=foreign)
            assert res.status_code == 422 and _code(res) == "FX_RATE_REQUIRED"
            assert float(client.get(f"/api/commercial/proposals/{pid}/versions/{v1}", headers=admin).json()["price_total"]) == 10500.5, "failed save changes nothing"

            # ---- cost and margin visibility
            seen = client.get(f"/api/commercial/proposals/{pid}/versions/{v1}", headers=observer).json()
            assert seen["price_total"] is None and seen["cost_total"] is None and all(ln["unit_cost"] is None for ln in seen["lines"])
            peer = client.get(f"/api/commercial/proposals/{pid}/versions/{v1}", headers=member).json()
            assert peer["cost_total"] is None and peer["price_total"] is not None
            assert client.put(f"/api/commercial/proposals/{pid}/versions/{v1}", headers=member, json=content).status_code == 403

            # ---- approval without a rule: administrator with a note
            assert client.post(f"/api/commercial/proposals/{pid}/versions/{v1}/request-approval", headers=admin).status_code == 200
            assert client.put(f"/api/commercial/proposals/{pid}/versions/{v1}", headers=admin, json=content).status_code == 409
            step = client.get(f"/api/commercial/proposals/{pid}/versions/{v1}", headers=admin).json()["approvals"][0]
            assert step["can_decide"] is True and step["needs_override_note"] is True
            url = f"/api/commercial/proposals/{pid}/versions/{v1}/approvals/{step['id']}"
            assert client.post(url, headers=member, json={"decision": "approve"}).status_code == 403
            res = client.post(url, headers=admin, json={"decision": "approve"})
            assert res.status_code == 422 and _code(res) == "OVERRIDE_NOTE_REQUIRED"
            res = client.post(url, headers=admin, json={"decision": "approve", "note": "Approved by administrator"})
            assert res.status_code == 200 and res.json()["result"] == "approved"

            # ---- locked: API and database both refuse changes
            locked = client.get(f"/api/commercial/proposals/{pid}/versions/{v1}", headers=admin).json()
            assert locked["status"] == "approved" and locked["locked_at"] and len(locked["snapshot_hash"]) == 64
            res = client.put(f"/api/commercial/proposals/{pid}/versions/{v1}", headers=admin, json=content)
            assert res.status_code == 409 and _code(res) == "VERSION_LOCKED"
            assert _tamper_locked_version(v1) == "blocked"

            # ---- a new version leaves the approved one untouched
            rev = client.post(f"/api/commercial/proposals/{pid}/versions", headers=admin, json={"kind": "revision"})
            assert rev.status_code == 200 and rev.json()["version_no"] == 2
            v2 = rev.json()["id"]
            changed = {**content, "lines": [{**content["lines"][0], "quantity": "12"}], "work_packages": content["work_packages"] + [{"title": "Rollout"}]}
            assert client.put(f"/api/commercial/proposals/{pid}/versions/{v2}", headers=admin, json=changed).status_code == 200
            assert float(client.get(f"/api/commercial/proposals/{pid}/versions/{v1}", headers=admin).json()["price_total"]) == 10500.5
            diff = client.get(f"/api/commercial/proposals/{pid}/compare", headers=admin, params={"a": v1, "b": v2}).json()
            assert diff["work_packages_added"] == ["Rollout"] and diff["lines_removed"] == ["On-site"]
            assert float(diff["totals"]["price_total"]["delta"]) == 1499.5

            # ---- sending to the customer verifies the snapshot, acceptance wins the opportunity
            assert client.post(f"/api/commercial/proposals/{pid}/versions/{v1}/submit", headers=admin).status_code == 200
            assert client.post(f"/api/commercial/proposals/{pid}/outcome", headers=admin, json={"outcome": "accepted"}).status_code == 200
            assert client.get(f"{base}", headers=admin).json()["stage"] == "won"
            assert client.delete(f"/api/commercial/proposals/{pid}", headers=admin).status_code == 409
        finally:
            for oid in opp_ids:
                client.delete(f"/api/commercial/opportunities/{oid}", headers=admin)


def test_bid_decision_authority():
    with _client() as client:
        admin = _login(client, "anna.berger@demo.circleos.app")
        member = _login(client, "felix.steiner@demo.circleos.app")
        orgs = client.get("/api/crm/organizations", headers=admin, params={"relation": "customer"}).json()
        roles = client.get("/api/structure", headers=admin).json()["roles"]
        felix_role = next((r for r in roles if any(h["name"].startswith("Felix") for h in r["holders"])), None)
        if not orgs or felix_role is None:
            pytest.skip("no demonstration data")
        if client.get("/api/commercial/decision-rules", headers=admin, params={"decision_type": "bid"}).json():
            pytest.skip("bid rules already configured")
        opp_ids: list[str] = []
        rule_id = None
        try:
            def new_opp(title: str) -> str:
                res = client.post("/api/commercial/opportunities", headers=admin, json={
                    "title": title, "crm_org_id": orgs[0]["id"], "value_amount": "10000.00", "category": "development",
                })
                assert res.status_code == 200, res.text
                opp_ids.append(res.json()["id"])
                return res.json()["id"]

            first = new_opp("Bid test one")
            second = new_opp("Bid test two")

            # ---- score is calculated, never decided automatically
            scores = [
                {"criterion": "strategic_fit", "rating": 5, "weight": 3},
                {"criterion": "capacity", "rating": 3, "weight": 3},
            ]
            saved = client.put(f"/api/commercial/opportunities/{first}/bid/scores", headers=admin, json={"scores": scores})
            assert saved.status_code == 200 and float(saved.json()["score"]) == 80.0 and saved.json()["complete"] is False
            bid = client.get(f"/api/commercial/opportunities/{first}/bid", headers=admin).json()
            assert bid["assessment"]["decision"] == "pending" and bid["authority"]["unclear"] is True

            # ---- no rule: a member cannot decide, an administrator needs a note
            body = {"decision": "bid", "rationale": "Fits our strategy"}
            res = client.post(f"/api/commercial/opportunities/{first}/bid/decision", headers=member, json=body)
            assert res.status_code == 403 and _code(res) == "AUTHORITY_REQUIRED"
            res = client.post(f"/api/commercial/opportunities/{first}/bid/decision", headers=admin, json=body)
            assert res.status_code == 422 and _code(res) == "OVERRIDE_NOTE_REQUIRED"
            res = client.post(f"/api/commercial/opportunities/{first}/bid/decision", headers=admin, json={**body, "override_note": "No rule defined yet"})
            assert res.status_code == 200 and res.json()["admin_override"] is True and res.json()["authority_unclear"] is True
            assert res.json()["stage"] == "proposal"
            res = client.put(f"/api/commercial/opportunities/{first}/bid/scores", headers=admin, json={"scores": scores})
            assert res.status_code == 409 and _code(res) == "BID_DECIDED"

            # ---- a rule that does not match the value still leaves the authority unclear
            res = client.post("/api/commercial/decision-rules", headers=admin, json={
                "decision_type": "bid", "label": "Bid owner", "role_id": felix_role["id"], "min_value": "50000",
            })
            assert res.status_code == 200, res.text
            rule_id = res.json()["id"]
            assert client.post("/api/commercial/decision-rules", headers=member, json={"decision_type": "bid", "label": "Member try", "role_id": felix_role["id"]}).status_code == 403
            res = client.post(f"/api/commercial/opportunities/{second}/bid/decision", headers=member, json=body)
            assert res.status_code == 403

            # ---- once the rule matches, the role holder decides, and No-Bid closes the opportunity
            assert client.patch(f"/api/commercial/decision-rules/{rule_id}", headers=admin, json={"min_value": "0"}).status_code == 200
            info = client.get(f"/api/commercial/opportunities/{second}/bid", headers=member).json()
            assert info["authority"]["authorized"] is True and info["can_decide"] is True
            res = client.post(f"/api/commercial/opportunities/{second}/bid/decision", headers=member, json={"decision": "no_bid", "rationale": "Not enough capacity"})
            assert res.status_code == 200 and res.json()["admin_override"] is False and res.json()["stage"] == "lost"
            lost = client.get(f"/api/commercial/opportunities/{second}", headers=admin).json()
            assert lost["stage"] == "lost" and lost["lost_reason"].startswith("No-Bid")
            res = client.post(f"/api/commercial/opportunities/{first}/bid/decision", headers=member, json={"decision": "no_bid"})
            assert res.status_code == 422 and _code(res) == "RATIONALE_REQUIRED"
        finally:
            if rule_id:
                client.delete(f"/api/commercial/decision-rules/{rule_id}", headers=admin)
            for oid in opp_ids:
                client.delete(f"/api/commercial/opportunities/{oid}", headers=admin)
