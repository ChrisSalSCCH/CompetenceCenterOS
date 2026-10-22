"""Integration tests (need TEST_DATABASE_URL; skipped otherwise).

They exercise the real SQL, the transactional governance engine and the server-side
authorization against the demonstration organization.
"""

from __future__ import annotations

import uuid

import pytest
from services.auth import hash_password, issue_access_token
from services.dbx import q1
from services.seed import DEMO_DOMAIN, seed_demo
from sqlalchemy import text


async def _uid(db, name: str):
    row = await q1(db, "SELECT id FROM users WHERE email = :e", e=f"{name}@{DEMO_DOMAIN}")
    return row["id"]


async def _headers(db, name: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(str(await _uid(db, name)))}"}


@pytest.fixture()
async def seeded(db_session):
    await db_session.execute(text("DELETE FROM organizations"))
    org = await seed_demo(db_session)
    return org


async def _circle(db, org, name: str):
    return (await q1(db, "SELECT id FROM circles WHERE organization_id = :o AND name = :n", o=org, n=name))["id"]


async def _role_count(client, headers) -> int:
    res = await client.get("/api/structure", headers=headers)
    return len(res.json()["roles"])


async def test_unauthenticated_requests_are_rejected(async_client):
    assert (await async_client.get("/api/structure")).status_code == 401


async def test_observer_cannot_change_structure(async_client, db_session, seeded):
    h = await _headers(db_session, "eva.lang")
    root = await _circle(db_session, seeded, "Services & Solutions")
    res = await async_client.post("/api/roles", headers=h, json={"circle_id": str(root), "name": "Sneaky"})
    assert res.status_code == 403


async def test_member_without_governance_role_only_creates_a_proposal(async_client, db_session, seeded):
    h = await _headers(db_session, "felix.steiner")
    root = await _circle(db_session, seeded, "Services & Solutions")
    before = await _role_count(async_client, h)
    res = await async_client.post("/api/roles", headers=h, json={"circle_id": str(root), "name": "Experiment Steward", "purpose": "x"})
    assert res.status_code == 200
    body = res.json()
    assert body["applied"] is False
    assert body["proposal_id"]
    assert await _role_count(async_client, h) == before


async def test_direct_change_is_applied_and_versioned_in_authorized_circle(async_client, db_session, seeded):
    h = await _headers(db_session, "lena.fischer")  # governance role in the direct-mode circle Venture & Product
    vp = await _circle(db_session, seeded, "Venture & Product")
    res = await async_client.post("/api/roles", headers=h, json={"circle_id": str(vp), "name": "Data Steward", "purpose": "Data is trustworthy", "accountabilities": [{"text": "Curating datasets"}]})
    assert res.status_code == 200
    assert res.json()["applied"] is True
    changes = await db_session.execute(text("SELECT op, source, after_state FROM governance_changes WHERE entity_id = :e"), {"e": res.json()["entity_id"]})
    row = changes.first()
    assert row is not None and row.op == "create" and row.source == "direct"


async def test_accepted_proposal_changes_structure_and_rejected_does_not(async_client, db_session, seeded):
    admin = await _headers(db_session, "anna.berger")
    member = await _headers(db_session, "mira.hofer")
    so = await _circle(db_session, seeded, "Service Operations")
    before = await _role_count(async_client, admin)

    def payload(name: str):
        return {
            "circle_id": str(so), "title": f"Create {name}", "submit": True, "proposal_type": "create_role",
            "changes": [{"op": "create_role", "data": {"circle_id": str(so), "name": name, "purpose": "p", "accountabilities": [{"text": "Measuring things"}]}}],
        }

    accepted = (await async_client.post("/api/proposals", headers=member, json=payload("Metrics Analyst"))).json()["id"]
    rejected = (await async_client.post("/api/proposals", headers=member, json=payload("Ghost Role"))).json()["id"]

    res = await async_client.post(f"/api/proposals/{rejected}/decide", headers=admin, json={"outcome": "rejected", "rationale": "not needed"})
    assert res.status_code == 200
    assert await _role_count(async_client, admin) == before

    res = await async_client.post(f"/api/proposals/{accepted}/decide", headers=admin, json={"outcome": "accepted", "rationale": "ok"})
    assert res.status_code == 200
    assert await _role_count(async_client, admin) == before + 1
    detail = (await async_client.get(f"/api/proposals/{accepted}", headers=admin)).json()
    assert detail["status"] == "accepted" and detail["applied_changes"]


async def test_a_failing_modification_rolls_back_the_whole_proposal(async_client, db_session, seeded):
    admin = await _headers(db_session, "anna.berger")
    member = await _headers(db_session, "mira.hofer")
    so = await _circle(db_session, seeded, "Service Operations")
    before = await _role_count(async_client, admin)
    body = {
        "circle_id": str(so), "title": "Two changes, one invalid", "submit": True,
        "changes": [
            {"op": "create_role", "data": {"circle_id": str(so), "name": "Valid New Role"}},
            {"op": "update_role", "id": str(uuid.uuid4()), "data": {"name": "Does not exist"}},
        ],
    }
    pid = (await async_client.post("/api/proposals", headers=member, json=body)).json()["id"]
    res = await async_client.post(f"/api/proposals/{pid}/decide", headers=admin, json={"outcome": "accepted"})
    assert res.status_code == 404
    await db_session.rollback()
    assert await _role_count(async_client, admin) == before


async def test_circle_cannot_be_moved_below_its_own_subcircle(async_client, db_session, seeded):
    h = await _headers(db_session, "anna.berger")
    vp = await _circle(db_session, seeded, "Venture & Product")
    child = await async_client.post("/api/circles", headers=h, json={"parent_id": str(vp), "name": "Labs"})
    assert child.json()["applied"] is True
    res = await async_client.patch(f"/api/circles/{vp}", headers=h, json={"parent_id": child.json()["entity_id"]})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "CIRCLE_CYCLE"


async def test_single_holder_role_rejects_second_assignment(async_client, db_session, seeded):
    h = await _headers(db_session, "anna.berger")
    role = (await q1(db_session, "SELECT id FROM roles WHERE organization_id = :o AND name = 'Bid Manager'", o=seeded))["id"]
    other = await _uid(db_session, "sophie.wagner")
    res = await async_client.post(f"/api/roles/{role}/assignments", headers=h, json={"user_id": str(other)})
    assert res.status_code == 409
    assert res.json()["error"]["code"] == "ROLE_ALREADY_FILLED"


async def test_tenant_isolation(async_client, db_session, seeded):
    org2 = (await q1(db_session, "INSERT INTO organizations (name, slug) VALUES ('Other', :s) RETURNING id", s=f"other-{uuid.uuid4().hex[:8]}"))["id"]
    user2 = (await q1(db_session, "INSERT INTO users (email, password_hash, display_name) VALUES (:e, :p, 'Other Admin') RETURNING id", e=f"admin-{uuid.uuid4().hex[:6]}@other.org", p=hash_password("Other-Password-1")))["id"]
    await db_session.execute(text("INSERT INTO memberships (organization_id, user_id, access_level) VALUES (:o, :u, 'org_admin')"), {"o": org2, "u": user2})
    h2 = {"Authorization": f"Bearer {issue_access_token(str(user2))}"}
    foreign_circle = await _circle(db_session, seeded, "Customer Solutions")
    assert (await async_client.get(f"/api/circles/{foreign_circle}", headers=h2)).status_code == 404
    assert (await async_client.get("/api/structure", headers=h2)).json()["roles"] == []
    assert (await async_client.patch(f"/api/circles/{foreign_circle}", headers=h2, json={"name": "Hijacked"})).status_code == 404
