"""Shared pytest fixtures for the backend test suite.

Test hygiene this harness enforces:

* UNIT tests are hermetic — use ``client`` (no DB) or mock the boundary
  (override ``get_db`` with a fake, or mock an external client). They touch no
  real DB, no network and no real secrets, and don't depend on ambient env — so
  they're deterministic and parallel-safe. This is the default; see
  ``test_unit_examples.py``.
* INTEGRATION tests use ``db_session`` / ``async_client`` — a real DB, but the
  project's DEDICATED test database (``TEST_DATABASE_URL``, provisioned by the
  Testing integration), isolated per test by a transaction rolled back on
  teardown. They are auto-marked ``integration``.

Determinism: this file pins fixed test config in the environment BEFORE the app
is imported, so tests never inherit ambient env. It refuses to run DB tests
against the app's runtime/prod database (prod guard) — DB tests run only against
the dedicated test DB.

Parallelism: unit tests (no DB) parallelize freely under ``pytest -n auto``. For
parallel INTEGRATION tests, give each xdist worker its own schema in the test DB
(``search_path``) so they don't collide — a handful of schemas (= worker count),
not one DB per test. See the note in ``_test_engine``.
"""

from __future__ import annotations

import logging
import os
from unittest.mock import AsyncMock

# --- Deterministic test config: set BEFORE importing the app -----------------
# Never inherit ambient env — pin known values so the suite is reproducible on
# any machine / CI. DB-backed tests run ONLY against the dedicated test DB.
_RUNTIME_DATABASE_URL = os.environ.get("DATABASE_URL", "")
_TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", "")
if _TEST_DATABASE_URL:
    os.environ["DATABASE_URL"] = _TEST_DATABASE_URL
elif not _RUNTIME_DATABASE_URL:
    # Unit tests never connect; give the app a PARSEABLE placeholder so it
    # imports (create_async_engine parses lazily, no connection). Integration
    # tests skip without a real TEST_DATABASE_URL (see _test_engine).
    os.environ["DATABASE_URL"] = "postgresql://test:test@localhost:5432/test"
os.environ["ENVIRONMENT"] = "test"
os.environ.setdefault("APP_NAME", "test-app")
os.environ.setdefault("CORS_ORIGINS", "http://localhost")

import pytest
import pytest_asyncio

# Imports resolve via pytest.ini `pythonpath = src`.
from config import get_settings
from database import get_db
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from main import app
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

# Settings read env on instantiation; clear the cache so the pinned test values
# above are what the app sees. Guarded with hasattr so this harness still loads
# on an OLDER project config.py (plain singleton, no lru_cache) that the harness
# refresh ships this conftest alongside — there, fields are frozen at import (which
# happens after we pin env above), so no clear is needed anyway.
if hasattr(get_settings, "cache_clear"):
    get_settings.cache_clear()


def pytest_collection_modifyitems(config, items):
    """Auto-mark any test that uses a DB fixture as ``integration`` so the unit
    suite (``pytest -m "not integration"``) is guaranteed DB-free."""
    db_fixtures = {"db_session", "async_client", "_test_engine"}
    for item in items:
        if db_fixtures & set(getattr(item, "fixturenames", ())):
            item.add_marker("integration")


@pytest.fixture()
def settings():
    """The app's Settings (deterministic test config)."""
    return get_settings()


@pytest.fixture()
def client() -> TestClient:
    """Synchronous client for UNIT tests that don't hit the database.

    TestClient runs the app's lifespan when used as a context manager
    (``with client as c: ...``); the raw fixture is fine for stateless routes.
    """
    return TestClient(app)


@pytest.fixture()
def fake_db() -> AsyncMock:
    """An ``AsyncMock`` standing in for the DB session — for UNIT tests of
    DB-backed routes with NO real database. Configure return values per test,
    e.g. ``fake_db.execute.return_value.scalar_one.return_value = 42``."""
    return AsyncMock()


@pytest.fixture()
def client_with_fake_db(fake_db: AsyncMock) -> TestClient:
    """Sync client with ``get_db`` overridden to a fake session — unit-test a
    DB-backed route hermetically (no real DB, no network). NOT auto-marked
    integration; this stays a unit test."""

    async def _override_get_db():
        yield fake_db

    app.dependency_overrides[get_db] = _override_get_db
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.pop(get_db, None)


def _async_database_url() -> str:
    """The dedicated test DB as a SQLAlchemy asyncpg URL (mirrors database.py)."""
    url = get_settings().database_url
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url.replace("sslmode=", "ssl=")


@pytest_asyncio.fixture(scope="session")
async def _test_engine():
    """Session-wide async engine for INTEGRATION tests — the dedicated test DB
    only.

    Prod guard: skip DB tests unless a dedicated ``TEST_DATABASE_URL`` is set and
    differs from the runtime ``DATABASE_URL``, so a test can never mutate the
    app's runtime/prod database. (Enable the Testing integration to provision a
    test DB.)

    Parallel note: to run integration tests with ``pytest -n auto``, give each
    xdist worker its own schema in this test DB and pin ``search_path`` to it
    (read ``PYTEST_XDIST_WORKER``) so workers don't collide — a handful of
    schemas (= worker count), not one DB per test. Serial (the default) needs
    none of that; per-test isolation is the rollback in ``db_session``.
    """
    if not _TEST_DATABASE_URL:
        pytest.skip(
            "no TEST_DATABASE_URL — integration tests skipped. Enable the Testing "
            "integration to provision a dedicated test database."
        )
    if _RUNTIME_DATABASE_URL and _TEST_DATABASE_URL == _RUNTIME_DATABASE_URL:
        pytest.skip("TEST_DATABASE_URL must differ from the runtime DATABASE_URL (prod guard).")

    try:
        from db.migrations import run_migrations
    except ImportError:
        # No migration runner yet (early scaffold) — nothing to apply.
        logging.getLogger(__name__).info(
            "db.migrations not present — running tests against the schema as-is"
        )
    else:
        # A migration runner that EXISTS but fails is a real failure: surface it
        # rather than silently running the suite against a half-built schema.
        await run_migrations()  # Flyway-style version table → safe to re-run

    engine = create_async_engine(_async_database_url(), poolclass=NullPool)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest_asyncio.fixture()
async def db_session(_test_engine) -> AsyncSession:
    """A session wrapped in a transaction rolled back after each test — clean
    per-test state, no pollution, no mocking. ``create_savepoint`` lets route
    code call ``commit()`` without ending the outer, rolled-back transaction."""
    async with _test_engine.connect() as conn:
        trans = await conn.begin()
        session = AsyncSession(
            bind=conn,
            expire_on_commit=False,
            join_transaction_mode="create_savepoint",
        )
        try:
            yield session
        finally:
            await session.close()
            if trans.is_active:
                await trans.rollback()


@pytest_asyncio.fixture()
async def async_client(db_session) -> AsyncClient:
    """Async HTTP client bound to the app, with ``get_db`` overridden to the
    per-test transaction. Use for INTEGRATION tests of DB-backed routes."""

    async def _override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = _override_get_db
    try:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.dependency_overrides.pop(get_db, None)
