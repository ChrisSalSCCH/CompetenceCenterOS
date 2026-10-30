"""Application configuration — all values overridable via environment."""

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _split_csv(value: str) -> list[str]:
    """Split a comma-separated env var, stripping whitespace. Empty string → []."""
    return [v.strip() for v in value.split(",") if v.strip()]


@dataclass
class Settings:
    """Application settings from environment variables.

    All production-relevant values come from env vars so the same artefact can
    run in dev / staging / prod without code changes. Each field is read from
    the environment **on instantiation** (via ``default_factory``) rather than
    frozen at import, so tests can set deterministic config and pick it up with
    ``get_settings.cache_clear()``.
    """

    # The application's own name — just the name ("Acme Shop"), with no role
    # suffix, so it is usable anywhere the app names itself: emails, page titles,
    # PDF headers, log context. The API docs append their own suffix (see
    # main.py), which is why this must NOT carry "API" itself.
    app_name: str = field(default_factory=lambda: os.getenv("APP_NAME", "scch/kernel"))
    environment: str = field(
        default_factory=lambda: os.getenv("ENVIRONMENT", "local")
    )  # local | dev | staging | prod
    debug: bool = field(default_factory=lambda: os.getenv("DEBUG", "false").lower() == "true")
    host: str = field(default_factory=lambda: os.getenv("HOST", "0.0.0.0"))  # nosec B104 - all interfaces required in-container
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8080")))

    # Database — injected by the workspace runner via .xaio_env.json in dev, by
    # ECS task definition / secrets in cloud. asyncpg expects `postgresql://` —
    # strip the SQLAlchemy driver suffix.
    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "").replace(
            "postgresql+asyncpg://", "postgresql://"
        )
    )

    # CORS — env-driven, comma-separated. Dev default covers common local ports;
    # production MUST set CORS_ORIGINS to the real domain(s).
    cors_origins: list[str] = field(
        default_factory=lambda: _split_csv(
            os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000")
        )
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the process-wide Settings singleton.

    Cached; call ``get_settings.cache_clear()`` (e.g. after a test pins env vars)
    to force a fresh read.
    """
    return Settings()
