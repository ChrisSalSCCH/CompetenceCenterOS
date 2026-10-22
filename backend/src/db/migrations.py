"""Database migrations runner — the single provisioning path.

This is the ONE place the schema is provisioned. It runs the versioned
``V*.sql`` migrations in order, tracked in a ``schema_migrations`` table, and
runs identically everywhere:

  * local / dev — from the FastAPI lifespan under uvicorn;
  * production  — the platform invokes the app's lifespan once at deploy time.

Keep it the single source of truth: do NOT add a second migrator and do NOT
rely on ORM ``Base.metadata.create_all`` for DDL, or dev and prod drift apart
(that divergence is exactly what this unification removes).

Fail-closed: the first failing migration raises (naming the version), so a
broken migration is surfaced — it blocks startup in dev and fails the publish
in prod — instead of silently leaving the schema half-migrated and every later
migration blocked. A failed migration is not recorded, so it retries on the
next start once the SQL is fixed.
"""

import os
import re
from pathlib import Path

import asyncpg
from config import get_settings

settings = get_settings()

_SAFE_SCHEMA_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,62}$")


def _asyncpg_dsn(url: str) -> str:
    """asyncpg wants a plain libpq DSN — strip SQLAlchemy's +asyncpg driver
    tag and any pgbouncer-style query args it doesn't understand."""
    return url.replace("postgresql+asyncpg://", "postgresql://").split("?pgbouncer")[0]


def _advisory_lock_key(schema: str) -> int:
    """Deterministic 31-bit key for pg_advisory_lock.

    Must be stable across processes — Python's built-in hash() is per-process
    randomised (PYTHONHASHSEED), which would give each instance a different key
    and defeat the lock. Serialises concurrent migrators (multiple instances
    booting at once).
    """
    key = 0
    for ch in schema:
        key = (key * 31 + ord(ch)) & 0x7FFFFFFF
    return key


async def _apply_schema(conn: "asyncpg.Connection", schema: str) -> None:
    """Create the per-app schema and pin ``search_path`` to it.

    A schema is an IDENTIFIER, and Postgres does not accept bind parameters in
    utility statements — ``CREATE SCHEMA $1`` is not a thing. So the name is
    sent as a parameter to ``format('%I', ...)`` and the DATABASE does the
    quoting; the statement that finally runs is composed server-side. No
    f-string, ``%`` or ``.format()`` in Python goes near the SQL.

    The ``::text`` casts are load-bearing, not decoration. ``format()`` is
    declared ``format(text, VARIADIC "any")``, and a bind parameter in a
    ``VARIADIC "any"`` slot has no inferable type, so Postgres rejects the
    statement at Parse time with:

        could not determine data type of parameter $1   (SQLSTATE 42P18)

    That failure happens before any migration runs, which in production means
    the deploy-time bootstrap fails and the publish is rolled back. Keep the
    casts.
    """
    create_schema = await conn.fetchval(
        "SELECT format('CREATE SCHEMA IF NOT EXISTS %I', $1::text)", schema
    )
    await conn.execute(create_schema)
    # search_path is a VALUE, not an identifier, so it needs no DDL at all:
    # set_config takes it as a bind parameter, quote_ident does the quoting.
    await conn.execute("SELECT set_config('search_path', quote_ident($1::text), false)", schema)


async def run_migrations() -> list[str]:
    """Apply pending V*.sql migrations. Returns the versions applied this run."""
    dsn = _asyncpg_dsn(os.getenv("DATABASE_URL") or settings.database_url)
    schema = os.getenv("DATABASE_SCHEMA")

    applied: list[str] = []
    conn = await asyncpg.connect(dsn)
    try:
        # Per-app schema isolation: create the schema and pin the search_path
        # for this connection so both the DDL below and the seeded rows land in
        # the right place. (Also pinned server-side via ALTER ROLE, but doing it
        # here makes a fresh-schema first boot deterministic.)
        if schema:
            # The name must be a plain identifier before anything happens: a
            # value that could never be a schema is rejected outright, rather
            # than travelling through quoting we would then have to trust.
            if not _SAFE_SCHEMA_RE.match(schema):
                raise ValueError(f"Invalid DATABASE_SCHEMA: {schema!r}")
            await _apply_schema(conn, schema)

        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version VARCHAR(255) PRIMARY KEY,
                applied_at TIMESTAMP DEFAULT NOW()
            )
            """
        )

        lock_key = _advisory_lock_key(schema or "public")
        await conn.execute("SELECT pg_advisory_lock($1)", lock_key)
        try:
            await conn.execute("SET statement_timeout = 30000")
            migrations_dir = Path(__file__).parent.parent.parent / "migrations"
            for sql_file in sorted(migrations_dir.glob("V*.sql")):
                version = sql_file.stem
                if await conn.fetchval(
                    "SELECT 1 FROM schema_migrations WHERE version = $1", version
                ):
                    continue
                try:
                    await conn.execute(sql_file.read_text())
                except Exception as e:
                    # Fail loudly, naming the migration. It is deliberately NOT
                    # recorded, so it retries next boot once fixed.
                    raise RuntimeError(f"migration {version} failed: {e}") from e
                await conn.execute("INSERT INTO schema_migrations (version) VALUES ($1)", version)
                applied.append(version)
                print(f"Migration applied: {version}")
        finally:
            await conn.execute("SELECT pg_advisory_unlock($1)", lock_key)

        print(f"Migrations done ({len(applied)} applied)")
        return applied
    finally:
        await conn.close()
