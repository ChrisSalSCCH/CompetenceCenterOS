"""User model + request/response schemas for the custom auth stack."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from database import Base
from pydantic import BaseModel, EmailStr
from sqlalchemy import Column, DateTime, Text
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.sql import func


class User(Base):
    __tablename__ = "users"

    id = Column(PGUUID(as_uuid=True), primary_key=True, server_default=func.gen_random_uuid())
    email = Column(Text, unique=True, nullable=False, index=True)
    password_hash = Column(Text, nullable=False)
    display_name = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


# ---------- Pydantic schemas ----------


class UserRead(BaseModel):
    """Public user projection — safe to return from any endpoint."""

    id: UUID
    email: EmailStr
    display_name: str | None = None
    created_at: datetime

    model_config = {"from_attributes": True}


class SignupRequest(BaseModel):
    email: EmailStr
    password: str  # min-length validation enforced in the route for a clean error envelope
    display_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class TokenPair(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"  # noqa: S105 - OAuth2 token *type*, not a credential
