"""DAST seed — provision ONE known test identity for pre-publish security scanning.

Purpose: XAIO's pre-publish DAST (OWASP ZAP) scans a **throwaway** copy of this
app so it can safely exercise the authenticated ``/api`` surface. Most routes sit
behind auth, so the scanner needs a real account it can log into. This module
creates that account — a single known user — directly in the database, using the
app's OWN model and password hashing, so it stays correct even when you extend the
``User`` model or change the auth stack.

Where it runs (NEVER against real data):
* The XAIO platform runs ``seed_dast()`` inside the **throwaway scan instance**
  (an ephemeral pod with a disposable database), invoked on startup when
  ``XAIO_DAST_SEED=1``. The scanner then logs in via the app's real
  ``POST /auth/login`` with the credentials from :func:`dast_seed_credentials`.
* Your **integration tests** may call ``seed_dast(session)`` too, so the exact
  same seed path the scanner relies on is exercised by the suite — if it drifts,
  a test goes red (a loud signal), never a silently-degraded security scan.

DO NOT DELETE this file or remove ``seed_dast``: without it the security scan can
only reach public routes, so the authenticated part of your API ships un-scanned.

Tier 1 today = one authenticated identity. To deepen coverage (active-scan
access-control / IDOR checks), EXTEND ``seed_dast`` to also create representative
domain data (e.g. a couple of your own records, a second user) — see the marked
extension point below. Keep it idempotent.
"""

from __future__ import annotations

import asyncio
import logging
import os

from sqlalchemy import select

logger = logging.getLogger(__name__)

# The scanner and the seed MUST agree on the credentials. The platform overrides
# these per scan run (a random password); the defaults keep local test runs and
# `python -m tests.seed` working without any env set. Never rely on the default
# password reaching a real environment — the seed only ever runs on the throwaway.
_DEFAULT_EMAIL = "dast-scanner@xaio.test"
_DEFAULT_PASSWORD = "dast-scanner-local-only"  # noqa: S105 - throwaway-instance only


def dast_seed_credentials() -> tuple[str, str]:
    """The (email, password) the scanner will log in with. Single source of truth
    for both the seed (writes the user) and any test that logs in as it."""
    return (
        os.getenv("DAST_SEED_EMAIL", _DEFAULT_EMAIL),
        os.getenv("DAST_SEED_PASSWORD", _DEFAULT_PASSWORD),
    )


async def seed_dast(session) -> tuple[str, str] | None:
    """Upsert the known DAST user into ``session`` and return its credentials.

    Idempotent: if the user already exists its password hash is refreshed, so a
    re-run (or a re-scan) always leaves the account log-in-able with the current
    password. Commits the change.

    Returns ``(email, password)`` on success, or ``None`` when there's no auth
    stack to seed against (this app has no ``User`` model / password hashing) —
    in which case the scan simply runs unauthenticated. Never raises for the
    "no auth" case; real DB errors propagate so a broken seed is visible.
    """
    try:
        # Import inside the function: an app without the auth template has neither
        # module, and that's a valid "nothing to seed" state, not an error.
        from models.user import User
        from services.auth import hash_password
    except ImportError:
        logger.info("seed_dast: no auth stack (models.user / services.auth) — nothing to seed")
        return None

    email, password = dast_seed_credentials()

    existing = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if existing is not None:
        existing.password_hash = hash_password(password)
    else:
        session.add(
            User(email=email, password_hash=hash_password(password), display_name="DAST Scanner")
        )

    # --- EXTENSION POINT (Tier 2) -------------------------------------------
    # To unlock access-control / IDOR / data-dependent active-scan checks, create
    # a little of YOUR domain data here against the same session (and optionally a
    # second user), so the scanner reaches data-backed routes instead of 404s.
    # Keep it idempotent (check-then-insert) so re-runs stay clean.
    # ------------------------------------------------------------------------

    await session.commit()
    logger.info("seed_dast: ensured DAST test identity %s", email)
    return email, password


async def _main() -> None:
    """Standalone entry — used by the platform inside the throwaway scan instance
    (``XAIO_DAST_SEED=1``). Opens its own session against the app's configured
    database and seeds. Safe to run repeatedly."""
    from database import async_session

    async with async_session() as session:
        await seed_dast(session)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    asyncio.run(_main())
