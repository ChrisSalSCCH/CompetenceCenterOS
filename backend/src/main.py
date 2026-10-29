"""FastAPI application entry point.

Enterprise baseline — ships with:
  - lifespan context manager (replaces deprecated @app.on_event)
  - /health (liveness) and /ready (readiness with DB ping) endpoints
  - /docs and /redoc hidden only in prod (visible in local / dev / staging)
  - Global exception handler wrapping errors into { error: { code, ... } }
  - Request-ID middleware (X-Request-ID header, propagated to logs)
  - Security headers middleware (OWASP baseline: HSTS, X-Frame, CSP, ...)
  - Rate limiting via slowapi (100/min default, per-route override)
  - Upload validation helper in utils/uploads.py
  - Structured logging with module name + level
  - CORS origins read from CORS_ORIGINS env var
"""

import importlib
import logging
import pkgutil
import time
import uuid
from contextlib import asynccontextmanager
from contextvars import ContextVar
from pathlib import Path

from config import get_settings
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from limiter import limiter
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware

settings = get_settings()

# Structured logging. JSON format in prod for ELK/CloudWatch ingestion;
# human-readable in dev for tailing logs locally.
logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s [req=%(request_id)s] %(message)s",
)
logger = logging.getLogger(__name__)

# Id of the request being handled. A ContextVar, not a global: requests run
# concurrently on one event loop and each must log its own id. '-' when no
# request is in scope (startup, shutdown).
_request_id: ContextVar[str] = ContextVar("request_id", default="-")

_base_record_factory = logging.getLogRecordFactory()


def _record_factory(*args, **kwargs) -> logging.LogRecord:
    record = _base_record_factory(*args, **kwargs)
    record.request_id = _request_id.get()
    return record


# Installed once at import and never swapped per request.
logging.setLogRecordFactory(_record_factory)


class _RequestIdFilter(logging.Filter):
    """Guarantees `request_id` on records built without the factory above,
    so the log format never fails on a missing field.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        if not hasattr(record, "request_id"):
            record.request_id = _request_id.get()
        return True


for _h in logging.getLogger().handlers:
    _h.addFilter(_RequestIdFilter())


# Marks an exception the catch-all handler below has already logged.
_LOGGED_ATTR = "_app_logged"


# Servers that log the exception again after Starlette re-raises it:
# uvicorn ("Exception in ASGI application") and, on serverless hosting,
# Mangum ("An error occurred running the application.").
_SERVER_ERROR_LOGGERS = ("uvicorn.error", "mangum.http")


class _AlreadyLoggedFilter(logging.Filter):
    """Drops the server's re-log of an exception the catch-all handler
    already logged.

    Starlette re-raises after the handler has answered 500, so the server
    logs the same traceback a second time. One failure must be one log entry,
    or log-based error monitoring counts every failing request twice.
    Exceptions the handler never saw (it crashed, or one escaped elsewhere)
    are not marked and are still logged by the server.
    """

    def filter(self, record: logging.LogRecord) -> bool:
        exc = record.exc_info[1] if record.exc_info else None
        return not getattr(exc, _LOGGED_ATTR, False)


for _name in _SERVER_ERROR_LOGGERS:
    logging.getLogger(_name).addFilter(_AlreadyLoggedFilter())


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown hooks. Runs migrations once before serving traffic.

    NOTE: in multi-instance deployments, run migrations as a separate
    one-shot job (see scripts/migrate.py) rather than from startup — the
    concurrent-apply race is harmless with Flyway but wastes boot time.
    Left on here as a dev/single-instance convenience.
    """
    migrations_dir = Path(__file__).parent.parent / "migrations"
    if migrations_dir.exists() and settings.database_url:
        try:
            from db.migrations import run_migrations
        except ImportError:
            logger.debug("No migration runner configured — skipping")
        else:
            # Fail-closed: a failing migration must stop startup here (dev) and
            # fail the publish (prod) — never swallow it. run_migrations() is the
            # single provisioning path, shared with production; see db/migrations.py.
            await run_migrations()
            logger.info("Database migrations applied successfully")
            # Demonstration organization: only created while the database has no organization.
            from services.seed import seed_if_empty
            from services.seed_portfolio import seed_portfolio_if_missing

            await seed_if_empty()
            # Demo organizations created before the portfolio/CRM modules get their sample data once.
            await seed_portfolio_if_missing()

    yield
    logger.info("Shutdown complete")


_DOCS_ENABLED = settings.environment != "prod"

# Doc/OpenAPI paths — defined once and reused by the CSP middleware below so
# the security-header exclusion always matches the real swagger paths. These
# live under /api/ (the API is mounted there), so a hardcoded "/docs" check
# would never match and would wrongly apply `default-src 'none'` to swagger.
_DOCS_URL = "/api/docs"
_REDOC_URL = "/api/redoc"
_OPENAPI_URL = "/api/openapi.json"
_DOCS_PATHS = (_DOCS_URL, _REDOC_URL, _OPENAPI_URL)

app = FastAPI(
    # APP_NAME is the application's name, not a title — the "API" belongs to
    # these docs, so it is appended here rather than baked into the variable.
    title=f"{settings.app_name} API",
    lifespan=lifespan,
    # OpenAPI UI is visible in local / dev / staging and hidden only in prod.
    # Using `environment` (not `debug`) so switching DEBUG for log-verbosity
    # doesn't accidentally toggle public API-doc visibility.
    docs_url=_DOCS_URL if _DOCS_ENABLED else None,
    redoc_url=_REDOC_URL if _DOCS_ENABLED else None,
    openapi_url=_OPENAPI_URL if _DOCS_ENABLED else None,
)


# =============================================================================
# Request-ID middleware — trace a request end-to-end across logs.
# =============================================================================


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach a unique X-Request-ID to every request + response.

    The id is accepted from the incoming header if present (for upstream
    tracing), else generated. Every log line emitted during the request
    includes the id via the logging filter configured above.
    """

    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        # request.state outlives this middleware: the catch-all exception
        # handler runs outside it and reads the id from there.
        request.state.request_id = req_id
        token = _request_id.set(req_id)
        try:
            start = time.perf_counter()
            response = await call_next(request)
            elapsed_ms = (time.perf_counter() - start) * 1000
            response.headers["X-Request-ID"] = req_id
            logger.info(
                "%s %s -> %d (%.1fms)",
                request.method,
                request.url.path,
                response.status_code,
                elapsed_ms,
            )
            return response
        finally:
            _request_id.reset(token)


app.add_middleware(RequestIdMiddleware)


# =============================================================================
# Security headers — OWASP baseline on every response.
# =============================================================================


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """OWASP security headers applied to every response.

    - X-Content-Type-Options: nosniff — prevents MIME-type sniffing attacks
    - X-Frame-Options: DENY — prevents clickjacking (no framing ever)
    - Referrer-Policy: no-referrer — strip Referer on outbound links
    - Permissions-Policy: disables browser features the API never needs
    - Strict-Transport-Security: enforce HTTPS (non-local envs only —
      local dev uses plain http, HSTS would poison the browser cache)
    - Content-Security-Policy: `default-src 'none'` for JSON API paths;
      skipped for the swagger paths (_DOCS_PATHS: /api/docs, /api/redoc,
      /api/openapi.json) which need inline scripts/styles.
    """

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=(), interest-cohort=()"
        )
        if settings.environment != "local":
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        path = request.url.path
        if not path.startswith(_DOCS_PATHS):
            response.headers["Content-Security-Policy"] = (
                "default-src 'none'; frame-ancestors 'none'"
            )
        return response


app.add_middleware(SecurityHeadersMiddleware)


# =============================================================================
# Rate limiting — slowapi attaches to app.state; per-route decorators
# tighten the global default for sensitive endpoints (login, search, LLM).
# =============================================================================

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)

# CORS — registered LAST so it is the OUTERMOST middleware. Starlette runs
# middleware in reverse order of registration, so this guarantees CORS headers
# on every response (including errors raised by inner middleware) and that
# preflight OPTIONS are answered before rate limiting. Origins from env.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    expose_headers=["X-Request-ID"],
)


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded):
    """Wrap slowapi's 429 in the standard error envelope."""
    return JSONResponse(
        status_code=429,
        content=_error_envelope(
            code="RATE_LIMITED",
            message="Too many requests — try again shortly",
            details={"limit": str(exc.detail)},
        ),
        headers={"Retry-After": "60"},
    )


# =============================================================================
# Global exception handlers — consistent { error: {...} } envelope.
# =============================================================================


def _error_envelope(
    *, code: str, message: str, field: str | None = None, details: dict | None = None
) -> dict:
    return {"error": {"code": code, "message": message, "field": field, "details": details or {}}}


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """Wrap HTTPException responses in the standard envelope.

    Handlers that raise `HTTPException(404, detail={"code":"CUSTOMER_NOT_FOUND",
    "message":"..."})` get their structured detail preserved; raising with
    a plain string falls back to a generic code derived from the status.
    """
    detail = exc.detail
    if isinstance(detail, dict) and "code" in detail:
        payload = _error_envelope(
            code=detail["code"],
            message=detail.get("message", ""),
            field=detail.get("field"),
            details=detail.get("details", {}),
        )
    else:
        generic_code = {
            400: "BAD_REQUEST",
            401: "UNAUTHORIZED",
            403: "FORBIDDEN",
            404: "NOT_FOUND",
            409: "CONFLICT",
            422: "UNPROCESSABLE_ENTITY",
            429: "RATE_LIMITED",
            500: "INTERNAL_ERROR",
            503: "SERVICE_UNAVAILABLE",
        }.get(exc.status_code, "HTTP_ERROR")
        payload = _error_envelope(code=generic_code, message=str(detail) if detail else "")
    return JSONResponse(status_code=exc.status_code, content=payload)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Turn Pydantic validation errors into structured per-field details."""
    errors = exc.errors()
    first_field = ".".join(str(x) for x in errors[0]["loc"][1:]) if errors else None
    return JSONResponse(
        status_code=422,
        content=_error_envelope(
            code="VALIDATION_ERROR",
            message=errors[0]["msg"] if errors else "Validation failed",
            field=first_field,
            details={"errors": errors},
        ),
    )


try:
    from sqlalchemy.exc import IntegrityError

    @app.exception_handler(IntegrityError)
    async def integrity_error_handler(request: Request, exc: IntegrityError):
        """Map SQLAlchemy IntegrityError to 409 with a structured code.

        The default behavior (catch-all below) would return 500 for unique
        constraint violations, foreign key failures, and NOT NULL breaches
        — but these are CLIENT errors (duplicate email, orphan reference,
        missing required field), not server errors. 409 Conflict lets the
        frontend show a sensible message like "This email is already in
        use" instead of a generic "Internal server error".

        We detect the specific failure via the psycopg/asyncpg `orig` error
        on the IntegrityError — unique vs. foreign-key vs. check vs.
        not-null — and emit a distinct code for each so the frontend can
        switch on it.
        """
        orig_name = type(exc.orig).__name__ if exc.orig else ""
        msg = str(exc.orig) if exc.orig else str(exc)

        if "UniqueViolation" in orig_name:
            code = "UNIQUE_CONSTRAINT_VIOLATION"
            status = 409
        elif "ForeignKeyViolation" in orig_name:
            code = "FOREIGN_KEY_VIOLATION"
            status = 409
        elif "NotNullViolation" in orig_name:
            code = "MISSING_REQUIRED_FIELD"
            status = 422
        elif "CheckViolation" in orig_name:
            code = "CHECK_CONSTRAINT_VIOLATION"
            status = 422
        else:
            code = "INTEGRITY_ERROR"
            status = 409

        logger.warning(
            "IntegrityError on %s %s: %s (%s)",
            request.method,
            request.url.path,
            orig_name,
            msg,
        )
        return JSONResponse(
            status_code=status,
            content=_error_envelope(
                code=code,
                message=msg[:200],
                details={"db_error_type": orig_name} if orig_name else {},
            ),
        )

except ImportError:
    # SQLAlchemy not installed — skip. The catch-all below still handles
    # any error, just as 500 rather than 409.
    pass


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    """Catch-all. Logs the full traceback, returns a redacted envelope."""
    # Runs outside RequestIdMiddleware (Starlette's outermost layer), so the
    # request's id is restored from request.state for the log and the header.
    req_id = getattr(request.state, "request_id", None)
    token = _request_id.set(req_id or "-")
    try:
        logger.error("Unhandled exception on %s %s", request.method, request.url.path, exc_info=exc)
    finally:
        _request_id.reset(token)
    setattr(exc, _LOGGED_ATTR, True)  # the server must not log it again
    return JSONResponse(
        status_code=500,
        content=_error_envelope(
            code="INTERNAL_ERROR",
            message="An unexpected error occurred. Check the request-id in the response header for correlation.",
        ),
        headers={"X-Request-ID": req_id} if req_id else None,
    )


# =============================================================================
# Health / Readiness probes.
# =============================================================================


@app.get("/health")
async def health():
    """Liveness probe. MUST NOT touch DB or external deps. Always 200
    unless the process is literally crashed — LB treats failure as
    'restart this container'.
    """
    return {"status": "healthy"}


@app.get("/ready")
async def ready():
    """Readiness probe. Pings the database. Failure = remove from LB
    pool but keep the container — LB should route traffic to healthy
    replicas while this one recovers.
    """
    if not settings.database_url:
        # No DB configured = service isn't actually ready to serve.
        return JSONResponse(
            status_code=503,
            content=_error_envelope(code="DB_NOT_CONFIGURED", message="DATABASE_URL is empty"),
        )
    try:
        from database import async_session  # type: ignore[attr-defined]

        async with async_session() as session:
            await session.execute(text("SELECT 1"))
        return {"status": "ready"}
    except Exception as e:
        logger.warning("Readiness check failed: %s", e)
        return JSONResponse(
            status_code=503,
            content=_error_envelope(code="DB_UNREACHABLE", message="Database not reachable"),
        )


# =============================================================================
# Auto-discover routers from routes/ — unchanged.
# =============================================================================

routes_dir = Path(__file__).parent / "routes"
if routes_dir.exists():
    for module_info in pkgutil.iter_modules([str(routes_dir)]):
        module = importlib.import_module(f"routes.{module_info.name}")
        if hasattr(module, "router"):
            app.include_router(module.router)
            logger.debug("Registered router: routes.%s", module_info.name)
