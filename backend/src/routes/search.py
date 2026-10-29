"""Search endpoints and saved filters."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from services.ctx import CtxDep, require_write
from services.dbx import DbDep, q, q1, x
from services.orgdata import load_structure
from services.search import rank_roles, search_all

router = APIRouter(prefix="/api", tags=["search"])


class SavedFilterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    query: str = Field(min_length=1, max_length=300)


@router.get("/search", summary="Search circles, roles, people, responsibilities, proposals, work and meetings")
async def search(
    ctx: CtxDep,
    db: DbDep,
    q_: str = Query(default="", alias="q", max_length=300),
    types: str | None = Query(default=None, max_length=200),
) -> dict:
    wanted = {t.strip() for t in types.split(",") if t.strip()} if types else None
    results = await search_all(db, ctx.org_id, q_, wanted, observer=ctx.level == "observer")
    return {"query": q_, "results": results}


@router.get("/responsibilities", summary="Which roles are responsible for a topic (accountability vs domain vs decision authority)")
async def responsibilities(ctx: CtxDep, db: DbDep, q_: str = Query(alias="q", min_length=1, max_length=300)) -> dict:
    structure = await load_structure(db, ctx.org_id)
    return {"query": q_, "roles": rank_roles(structure, q_)}


@router.get("/saved-filters", summary="Own saved searches")
async def list_filters(ctx: CtxDep, db: DbDep) -> list[dict]:
    return await q(db, "SELECT id, name, query FROM saved_filters WHERE user_id = :u AND organization_id = :o ORDER BY created_at DESC", u=ctx.user_id, o=ctx.org_id)


@router.post("/saved-filters", summary="Save a search")
async def create_filter(body: SavedFilterCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    row = await q1(
        db,
        "INSERT INTO saved_filters (organization_id, user_id, name, query) VALUES (:o, :u, :n, :q) RETURNING id",
        o=ctx.org_id, u=ctx.user_id, n=body.name, q=body.query,
    )
    await db.commit()
    return {"id": row["id"]}


@router.delete("/saved-filters/{filter_id}", summary="Delete a saved search")
async def delete_filter(filter_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    await x(db, "DELETE FROM saved_filters WHERE id = :id AND user_id = :u AND organization_id = :o", id=filter_id, u=ctx.user_id, o=ctx.org_id)
    await db.commit()
    return {"ok": True}
