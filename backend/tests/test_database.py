"""Sample INTEGRATION tests — proof that the DB harness works.

These run against the project's DEDICATED test database (see conftest.py:
``TEST_DATABASE_URL``, a NullPool engine, and a transaction rolled back per
test). They are the template for tests that genuinely need the DB — real
models, SQL and migrations, isolated per test. They are auto-marked
``integration`` (via any ``db_session``/``async_client`` fixture) and skipped
when no dedicated test DB is configured.

For most route/logic tests prefer a UNIT test that mocks the DB — see
``test_unit_examples.py``. Use these as the template for your own model/route
integration tests, then delete these.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

# Explicit marker (also auto-applied by the db_session/async_client fixtures).
pytestmark = pytest.mark.integration


async def test_db_session_is_real_postgres(db_session):
    """The session talks to a real Postgres server (the dedicated test DB)."""
    version = (await db_session.execute(text("SELECT version()"))).scalar_one()
    assert "PostgreSQL" in version


async def test_writes_are_real_then_rolled_back(db_session):
    """Writes inside a test are real and visible to the same session; the
    per-test transaction rolls them back on teardown so nothing persists.

    ``commit()`` here releases a SAVEPOINT (not a real COMMIT), exactly as a
    route handler's commit would — yet the outer transaction is still discarded.
    Replace the scratch table with your own models.
    """
    await db_session.execute(text("CREATE TABLE _harness_probe (id int PRIMARY KEY)"))
    await db_session.execute(text("INSERT INTO _harness_probe (id) VALUES (1)"))
    await db_session.commit()
    count = (await db_session.execute(text("SELECT count(*) FROM _harness_probe"))).scalar_one()
    assert count == 1


async def test_async_client_reaches_app(async_client):
    """The async client drives the real app in-process with get_db overridden to
    the per-test transaction — use it for DB-backed routes in integration tests."""
    r = await async_client.get("/health")
    assert r.status_code == 200
