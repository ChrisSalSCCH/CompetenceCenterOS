"""Custom email/password authentication.

Implements password hashing (argon2) and JWT issuance/verification (HS256) in
plain Python — no external auth service, no Supabase. Backed by the `users`
table in the project's PostgreSQL database.

Config:
    JWT_SECRET   — HS256 signing secret (set by the Backend integration).
                   Do NOT make this optional; a missing secret is a security
                   hole and must raise at startup.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID

import jwt as pyjwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_JWT_SECRET = os.getenv("JWT_SECRET")
if not _JWT_SECRET:
    # HARD FAIL — never sign JWTs with an empty secret.
    raise RuntimeError(
        "JWT_SECRET env var is required. Enable the Backend integration or "
        "set it manually in the project's Environment settings."
    )

_JWT_ALG = "HS256"
_ACCESS_TOKEN_MINUTES = int(os.getenv("ACCESS_TOKEN_MINUTES", "60"))
_REFRESH_TOKEN_DAYS = int(os.getenv("REFRESH_TOKEN_DAYS", "30"))

_hasher = PasswordHasher()
_security = HTTPBearer(auto_error=False)


# ---------- Registration mode ----------
# REGISTRATION_MODE controls public self-registration via POST /auth/signup:
#   "open"   (default) — anyone may register through the signup endpoint.
#   "closed"           — public registration is disabled; only users created
#                        directly in the `users` table (admin-seeded) may log
#                        in. The signup endpoint returns 403.
# Set per-project by the XAIO Backend integration (its `registration_mode`
# option). When the env var is absent the mode is "open", so existing apps
# keep their current behavior. Read at call time (not import time) so a
# backend restart after changing the value takes effect immediately.


def registration_mode() -> str:
    """Return the normalized registration mode: 'open' or 'closed'."""
    mode = (os.getenv("REGISTRATION_MODE", "open") or "open").strip().lower()
    return mode if mode in ("open", "closed") else "open"


def public_signup_enabled() -> bool:
    """True when public self-registration (POST /auth/signup) is allowed."""
    return registration_mode() == "open"


def require_public_signup_enabled() -> None:
    """FastAPI dependency that guards the public signup endpoint.

    Raises 403 when registration is closed (admin-only app), so the ENDPOINT —
    not just the UI — rejects self-registration. Apply with
    `Depends(require_public_signup_enabled)` on `POST /auth/signup`.
    """
    if not public_signup_enabled():
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Public registration is disabled for this app.",
        )


def hash_password(plain: str) -> str:
    """Argon2id hash. Includes salt + params in the returned string."""
    return _hasher.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    """Constant-time argon2 verify. Returns False on mismatch, never raises."""
    try:
        _hasher.verify(hashed, plain)
        return True
    except VerifyMismatchError:
        return False
    except Exception:
        return False


def _issue(sub: str, token_type: str, ttl: timedelta) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": sub,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
    }
    return pyjwt.encode(payload, _JWT_SECRET, algorithm=_JWT_ALG)


def issue_access_token(user_id: str) -> str:
    return _issue(user_id, "access", timedelta(minutes=_ACCESS_TOKEN_MINUTES))


def issue_refresh_token(user_id: str) -> str:
    return _issue(user_id, "refresh", timedelta(days=_REFRESH_TOKEN_DAYS))


def decode_token(token: str, expected_type: str) -> dict:
    """Decode + validate a token. Raises 401 on any failure."""
    try:
        payload = pyjwt.decode(token, _JWT_SECRET, algorithms=[_JWT_ALG])
    except pyjwt.ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired")
    except pyjwt.InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    if payload.get("type") != expected_type:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Wrong token type")
    return payload


def get_current_user_id(
    creds: Annotated[HTTPAuthorizationCredentials | None, Depends(_security)],
) -> UUID:
    """FastAPI dependency: resolves the authenticated user's UUID from the
    Authorization: Bearer <access_token> header. Use in routes that require
    authentication: `user_id: UUID = Depends(get_current_user_id)`.
    """
    if creds is None or not creds.credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
            headers={"WWW-Authenticate": "Bearer"},
        )
    payload = decode_token(creds.credentials, expected_type="access")
    sub = payload.get("sub")
    if not sub:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token payload"
        )
    try:
        return UUID(sub)
    except (ValueError, TypeError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token subject"
        )


def public_endpoint(reason: str) -> dict:
    """Declare a route INTENTIONALLY unauthenticated (public catalog, webhook
    receiver, contact form, ...). Spread the result into the route decorator:

        @router.get("/products", **public_endpoint("Public catalog — read-only"))
        def list_products(...): ...

    The pre-publish gate lists every endpoint reachable without authentication and
    asks the user to confirm it. Marking a route here tells the gate the exposure
    is deliberate, so it stops warning about it — the route still appears in the
    publish summary with `reason` for review. Do NOT use this to silence the gate
    on a route that should require auth; add `Depends(get_current_user_id)` instead.

    `reason` is required and must be a non-empty, human-readable justification.
    """
    if not reason or not reason.strip():
        raise ValueError("public_endpoint(reason) requires a non-empty reason")
    return {"openapi_extra": {"x-xaio-public": {"reason": reason.strip()}}}
