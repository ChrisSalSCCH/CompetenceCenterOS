"""Portfolio, catalog and CRM API checks against the demonstration organization.

Runs only with a real database. Every write is undone by the test itself (soft-deleted temporary rows).
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


def _code(res) -> str:
    return res.json().get("error", {}).get("code", "")


def test_portfolio_catalog_and_crm_rules():
    from database import engine
    from main import app

    with TestClient(app) as client:
        try:
            def login(email: str) -> dict[str, str]:
                res = client.post("/api/auth/demo-login", json={"email": email})
                if res.status_code != 200:
                    pytest.skip(f"demo organization not available: {res.status_code}")
                return {"Authorization": f"Bearer {res.json()['access_token']}"}

            admin = login("anna.berger@demo.circleos.app")
            member = login("felix.steiner@demo.circleos.app")
            observer = login("eva.lang@demo.circleos.app")

            rows = client.get("/api/portfolio", headers=admin).json()
            if not rows:
                pytest.skip("no portfolio demonstration data")
            assert len(rows) >= 8
            assert {r["classification"] for r in rows} == {"customer", "internal"}
            pm = next(r for r in rows if r["name"].startswith("Predictive Maintenance"))

            # ---- filters and search
            customer_only = client.get("/api/portfolio", headers=admin, params={"classification": "customer"}).json()
            assert customer_only and all(r["classification"] == "customer" for r in customer_only)
            by_alias = client.get("/api/portfolio", headers=admin, params={"search": "sklearn"}).json()
            assert any(r["id"] == pm["id"] for r in by_alias), "alias of a catalog entry finds the project"
            hits = client.get("/api/search", headers=admin, params={"q": "scikit"}).json()["results"]
            assert any(h["type"] == "project" and h["id"] == pm["id"] for h in hits)

            # ---- finance visibility
            as_admin = client.get(f"/api/portfolio/{pm['id']}", headers=admin).json()
            assert as_admin["finance"]["restricted"] is False and as_admin["finance"]["metrics"]["funding_rate"] == 50.0
            as_member = client.get(f"/api/portfolio/{pm['id']}", headers=member).json()
            assert as_member["finance"]["restricted"] is True and as_member["finance"]["data"] is None
            as_viewer = client.get(f"/api/portfolio/{pm['id']}", headers=observer).json()
            assert as_viewer["finance"]["restricted"] is False, "named finance viewer sees the data"
            assert client.put(f"/api/portfolio/{pm['id']}/finance", headers=member, json={"currency": "EUR"}).status_code == 403

            # ---- verification and observer rules
            res = client.put(f"/api/portfolio/{pm['id']}/knowledge/solution", headers=member, json={"verification": "verified"})
            assert res.status_code == 403 and _code(res) == "VERIFICATION_FORBIDDEN"
            assert client.patch(f"/api/portfolio/{pm['id']}", headers=observer, json={"priority": "high"}).status_code == 403
            contacts = client.get("/api/crm/contacts", headers=observer).json()
            assert contacts and all(c["email"] is None and c["phone"] is None for c in contacts)
            assert any(c["email"] for c in client.get("/api/crm/contacts", headers=admin).json())

            # ---- customer project needs a customer organization
            circle = client.get("/api/structure", headers=admin).json()["circles"][0]["id"]
            res = client.post("/api/portfolio", headers=admin, json={"name": "Orphan customer project", "circle_id": circle, "classification": "customer"})
            assert res.status_code == 422 and _code(res) == "CUSTOMER_REQUIRED"
            internal = client.post("/api/portfolio", headers=admin, json={"name": "Temporary internal project", "circle_id": circle, "classification": "internal"})
            assert internal.status_code == 200
            assert client.patch(f"/api/portfolio/{internal.json()['id']}", headers=admin, json={"classification": "customer"}).status_code == 422
            assert client.delete(f"/api/portfolio/{internal.json()['id']}", headers=admin).status_code == 200

            # ---- catalog: duplicates by spelling and alias, merge
            dup = client.post("/api/catalog", headers=admin, json={"kind": "technology", "name": "angular"})
            assert dup.status_code == 409 and _code(dup) == "CATALOG_DUPLICATE"
            alias_dup = client.post("/api/catalog", headers=admin, json={"kind": "technology", "name": "Postgres"})
            assert alias_dup.status_code == 409, "an alias counts as an existing name"
            a = client.post("/api/catalog", headers=admin, json={"kind": "technology", "name": "Zeta Test Tool"}).json()["id"]
            b = client.post("/api/catalog", headers=admin, json={"kind": "technology", "name": "Zeta Tool"}).json()["id"]
            assert client.post("/api/catalog", headers=admin, json={"kind": "technology", "name": "Zeta-Tool"}).status_code == 409
            assert client.post(f"/api/catalog/{a}/merge", headers=member, json={"target_id": b}).status_code == 403
            assert client.post(f"/api/catalog/{a}/merge", headers=admin, json={"target_id": b}).status_code == 200
            merged = next(e for e in client.get("/api/catalog", headers=admin, params={"kind": "technology"}).json() if e["id"] == b)
            assert any(al["alias"] == "Zeta Test Tool" for al in merged["aliases"]), "merged name stays findable as alias"
            suggest = client.get("/api/catalog/suggest", headers=admin, params={"kind": "technology", "text": "Zeta Test"}).json()
            assert [s["id"] for s in suggest] == [b]
            assert client.delete(f"/api/catalog/{b}", headers=admin).status_code == 200

            # ---- CRM: duplicate detection and 360 view
            orgs = client.get("/api/crm/organizations", headers=admin).json()
            nord = next(o for o in orgs if o["name"].startswith("Nordklinik"))
            dup_vat = client.post("/api/crm/organizations", headers=admin, json={"name": "Different Name", "vat_id": "atu 00000001"})
            assert dup_vat.status_code == 409 and _code(dup_vat) == "CRM_DUPLICATE"
            assert client.post("/api/crm/organizations", headers=admin, json={"name": "nordklinik health group"}).status_code == 409
            view = client.get(f"/api/crm/organizations/{nord['id']}", headers=admin).json()
            assert view["projects"] and view["contacts"] and view["activities"] and view["roles"], "360 view is populated"
            assert view["next_steps"], "open follow-up task appears as next step"
            dash = client.get("/api/crm/dashboard", headers=admin).json()
            assert dash["active_customers"] >= 3 and dash["planned_modules"] == []

            # ---- references expose only released content
            refs = client.get("/api/portfolio/references", headers=member).json()
            assert refs
            anonymised = next(r for r in refs if not r["name_released"])
            assert anonymised["title"].startswith("Confidential project") and "Portal" not in anonymised["title"]
        finally:
            client.portal.call(engine.dispose)
