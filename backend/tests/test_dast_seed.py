"""Keeps the DAST seed honest.

The pre-publish security scan logs into a throwaway copy of this app with the
identity ``tests/seed.py`` creates. If that seed drifts (renamed User model,
changed hashing, new required column), the scan silently loses its authenticated
coverage — so this test exercises the exact same ``seed_dast`` path the scanner
uses, turning any drift into a RED test instead of a quiet security gap.

Integration test: runs against the dedicated test DB, rolled back per test
(see conftest.py). Skips automatically on a project with no auth stack.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration

try:  # tolerate both the flat and src/ scaffold layouts
    from tests.seed import dast_seed_credentials, seed_dast
except ImportError:  # pragma: no cover - layout fallback
    from seed import dast_seed_credentials, seed_dast


async def test_seed_dast_creates_loginable_identity(db_session):
    """seed_dast writes a user whose password verifies with the app's own hasher —
    i.e. the scanner will actually be able to log in via /auth/login."""
    creds = await seed_dast(db_session)
    if creds is None:
        pytest.skip("no auth stack in this project — DAST runs unauthenticated")
    email, password = creds
    assert (email, password) == dast_seed_credentials()

    from models.user import User
    from services.auth import verify_password
    from sqlalchemy import select

    user = (await db_session.execute(select(User).where(User.email == email))).scalar_one()
    assert verify_password(password, user.password_hash)


async def test_seed_dast_is_idempotent(db_session):
    """Re-running the seed (a re-scan) leaves exactly one user, still log-in-able."""
    if await seed_dast(db_session) is None:
        pytest.skip("no auth stack in this project — DAST runs unauthenticated")
    await seed_dast(db_session)

    from models.user import User
    from sqlalchemy import func, select

    email, _ = dast_seed_credentials()
    count = (
        await db_session.execute(select(func.count()).select_from(User).where(User.email == email))
    ).scalar_one()
    assert count == 1
