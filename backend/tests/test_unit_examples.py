"""Sample UNIT tests — hermetic: no real DB, no network, no real secrets.

Unit tests must be deterministic. They must NOT depend on a real database, a
real external service, real API keys, or ambient env vars. You get there by
MOCKING the boundary — the DB session or the external client — and asserting
YOUR code's behaviour. They run with ``pytest -m "not integration"`` and need no
``TEST_DATABASE_URL`` and no real keys.

Use these as the template for your own unit tests, then delete them.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import text


def test_mocked_external_client():
    """Mock the external client — never call the real service or require a real
    API key. Assert that YOUR code drives the client correctly."""

    async def send_welcome(email_client, address: str) -> bool:
        # Your code formats the message and hands off to the INJECTED client.
        await email_client.send(to=address, subject="Welcome")
        return True

    client = AsyncMock()
    assert asyncio.run(send_welcome(client, "user@example.com")) is True
    client.send.assert_awaited_once_with(to="user@example.com", subject="Welcome")


def test_logic_with_mocked_db_session(fake_db):
    """Unit-test DB-touching logic with a MOCKED session — no real database.
    Configure the mock's return, call your function, assert behaviour."""

    async def count_active(session) -> int:
        result = await session.execute(text("SELECT count(*) FROM users WHERE active"))
        return result.scalar_one()  # sync on SQLAlchemy's Result

    # `execute` is awaited (AsyncMock); its result is sync, so mock it as a
    # plain MagicMock whose `scalar_one()` returns the value.
    result = MagicMock()
    result.scalar_one.return_value = 3
    fake_db.execute.return_value = result
    assert asyncio.run(count_active(fake_db)) == 3
    fake_db.execute.assert_awaited_once()


def test_route_with_mocked_db(client_with_fake_db):
    """A DB-backed route can be unit-tested with NO real DB by overriding
    ``get_db`` with a fake session (see the ``client_with_fake_db`` fixture).
    Point this at one of YOUR DB-backed routes; here we hit /health as a stand-in."""
    r = client_with_fake_db.get("/health")
    assert r.status_code == 200
