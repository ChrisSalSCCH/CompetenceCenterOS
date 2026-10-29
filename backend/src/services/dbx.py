"""Thin SQL helpers. All business queries are written as parameterised SQL (no string
interpolation of user input) and always carry an organization_id predicate."""

from __future__ import annotations

import json
from typing import Annotated, Any

from database import get_db
from fastapi import Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

DbDep = Annotated[AsyncSession, Depends(get_db)]

Row = dict[str, Any]


def _decode_json(row: Row) -> Row:
    """Some drivers hand back json/jsonb as text; make sure the API always sees structured data."""
    for key in JSON_COLUMNS:
        value = row.get(key)
        if isinstance(value, str) and value[:1] in ("[", "{"):
            try:
                row[key] = json.loads(value)
            except ValueError:
                continue
    return row


JSON_COLUMNS = ("changes", "people", "before_state", "after_state", "notification_prefs", "data", "snapshot")


async def q(db: AsyncSession, sql: str, **params: Any) -> list[Row]:
    """Run a SELECT / RETURNING statement and return all rows as dicts."""
    res = await db.execute(text(sql), params)
    return [_decode_json(dict(r._mapping)) for r in res.fetchall()]


async def q1(db: AsyncSession, sql: str, **params: Any) -> Row | None:
    rows = await q(db, sql, **params)
    return rows[0] if rows else None


async def x(db: AsyncSession, sql: str, **params: Any) -> None:
    await db.execute(text(sql), params)


def jb(value: Any) -> str:
    """Serialise a value for a CAST(:p AS jsonb) parameter."""
    return json.dumps(value, default=str)


def err(status: int, code: str, message: str, field: str | None = None) -> HTTPException:
    detail: dict[str, Any] = {"code": code, "message": message}
    if field:
        detail["field"] = field
    return HTTPException(status_code=status, detail=detail)


def set_clause(data: dict[str, Any], allowed: set[str]) -> tuple[str, dict[str, Any]]:
    """Build a `col = :col` list for a PATCH from the allowed column names."""
    cols = [k for k in data if k in allowed]
    return ", ".join(f"{c} = :{c}" for c in cols), {c: data[c] for c in cols}
