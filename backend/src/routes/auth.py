"""Email/password auth routes.

Endpoints:
- POST /api/auth/signup   → creates a user, returns (access, refresh) tokens
- POST /api/auth/login    → verifies password, returns tokens
- POST /api/auth/refresh  → exchanges a valid refresh token for a new pair
- POST /api/auth/logout   → 204 no-content (tokens are stateless; frontend discards them)
- GET  /api/auth/me       → returns the current user (requires Bearer access token)

No OAuth, no magic-link, no password reset by design — keep this file small.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from database import get_db
from fastapi import APIRouter, Depends, HTTPException, Request, status
from limiter import limiter
from models.user import (
    LoginRequest,
    RefreshRequest,
    SignupRequest,
    TokenPair,
    User,
    UserRead,
)
from services.auth import (
    decode_token,
    get_current_user_id,
    hash_password,
    issue_access_token,
    issue_refresh_token,
    public_signup_enabled,
    require_public_signup_enabled,
    verify_password,
)
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/api/auth", tags=["auth"])

_MIN_PASSWORD_LEN = 8


def _tokens_for(user_id: UUID) -> TokenPair:
    sub = str(user_id)
    return TokenPair(
        access_token=issue_access_token(sub),
        refresh_token=issue_refresh_token(sub),
    )


@router.get("/config")
def auth_config() -> dict:
    """Public auth configuration for the frontend.

    Exposes only whether self-registration is enabled, so the SPA can show or
    hide the Signup page. Safe to call unauthenticated — it reveals a single
    boolean, never user data.
    """
    return {"public_signup_enabled": public_signup_enabled()}


@router.post("/signup", status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def signup(
    request: Request,
    body: SignupRequest,
    _: Annotated[None, Depends(require_public_signup_enabled)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenPair:
    if len(body.password) < _MIN_PASSWORD_LEN:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Password must be at least {_MIN_PASSWORD_LEN} characters.",
        )
    user = User(
        email=body.email.lower(),
        password_hash=hash_password(body.password),
        display_name=body.display_name,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered.",
        )
    await db.refresh(user)
    return _tokens_for(user.id)


@router.post("/login")
@limiter.limit("5/minute")
async def login(
    request: Request, body: LoginRequest, db: Annotated[AsyncSession, Depends(get_db)]
) -> TokenPair:
    result = await db.execute(select(User).where(func.lower(User.email) == body.email.lower()))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(body.password, user.password_hash):
        # Same error for both branches — avoid email-enumeration.
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
        )
    return _tokens_for(user.id)


@router.post("/refresh")
def refresh(body: RefreshRequest) -> TokenPair:
    payload = decode_token(body.refresh_token, expected_type="refresh")
    try:
        user_id = UUID(payload["sub"])
    except (KeyError, ValueError, TypeError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    return _tokens_for(user_id)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
def logout() -> None:
    # Stateless JWTs — the client discards both tokens. If you need true
    # revocation, add a Redis deny-list of refresh-token JTIs and check it
    # in /refresh. Omitted to keep the baseline template minimal.
    return None


@router.get("/me")
async def me(
    user_id: Annotated[UUID, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> UserRead:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return UserRead.model_validate(user)
