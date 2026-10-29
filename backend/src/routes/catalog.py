"""Taxonomy catalog: technologies, industries, research areas, competencies, ...

Projects, roles and customers reference catalog entries instead of free text so that
search, filtering and later AI retrieval are consistent.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from services.catalog import duplicate_error, find_match, merge_entries, normalize
from services.ctx import CtxDep, require_admin, require_role, require_write
from services.dbx import DbDep, err, q, q1, set_clause, x
from services.events import audit

router = APIRouter(prefix="/api", tags=["catalog"])

CatalogKind = Literal["technology", "industry", "research_area", "competency", "method", "application_domain", "solution_type", "reusable_component"]
ENTRY_NOT_FOUND = "Catalog entry not found."


class EntryCreate(BaseModel):
    kind: CatalogKind
    name: str = Field(min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=60)
    description: str = Field(default="", max_length=2000)
    aliases: list[str] = Field(default_factory=list, max_length=20)


class EntryUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    category: str | None = Field(default=None, max_length=60)
    description: str | None = Field(default=None, max_length=2000)


class AliasCreate(BaseModel):
    alias: str = Field(min_length=1, max_length=120)


class MergeBody(BaseModel):
    target_id: UUID


class CompetencyIds(BaseModel):
    entry_ids: list[UUID] = Field(max_length=50)


USAGE_SQL = """(SELECT COUNT(*) FROM project_catalog_links l JOIN projects p ON p.id = l.project_id AND p.deleted_at IS NULL WHERE l.entry_id = e.id)
    + (SELECT COUNT(*) FROM role_catalog_links rl WHERE rl.entry_id = e.id)
    + (SELECT COUNT(*) FROM crm_organizations co WHERE co.industry_entry_id = e.id AND co.deleted_at IS NULL)"""


async def _entry(db, ctx, entry_id: UUID) -> dict:
    row = await q1(db, "SELECT * FROM catalog_entries WHERE id = :id AND organization_id = :o AND deleted_at IS NULL", id=entry_id, o=ctx.org_id)
    if row is None:
        raise err(404, "CATALOG_ENTRY_NOT_FOUND", ENTRY_NOT_FOUND)
    return row


async def _add_alias(db, ctx, entry: dict, alias: str) -> None:
    clean = alias.strip()
    key = normalize(clean)
    if not key:
        raise err(422, "INVALID_ALIAS", "Alias must contain letters or digits.", "alias")
    if key == entry["norm_name"]:
        return
    clash = await find_match(db, ctx.org_id, entry["kind"], clean, exclude_id=entry["id"])
    if clash:
        raise duplicate_error(clash)
    await x(
        db,
        """INSERT INTO catalog_aliases (organization_id, entry_id, kind, alias, norm_alias) VALUES (:o, :e, :k, :a, :n)
           ON CONFLICT (organization_id, kind, norm_alias) DO NOTHING""",
        o=ctx.org_id, e=entry["id"], k=entry["kind"], a=clean, n=key,
    )


@router.get("/catalog", summary="List catalog entries with aliases and usage counts")
async def list_catalog(ctx: CtxDep, db: DbDep, kind: CatalogKind | None = None, search: str | None = Query(default=None, max_length=100)) -> list[dict]:
    where = ["e.organization_id = :o", "e.deleted_at IS NULL"]
    params: dict = {"o": ctx.org_id}
    if kind:
        where.append("e.kind = :k")
        params["k"] = kind
    if search:
        where.append("(e.name ILIKE :s OR EXISTS (SELECT 1 FROM catalog_aliases a WHERE a.entry_id = e.id AND a.alias ILIKE :s))")
        params["s"] = f"%{search}%"
    return await q(
        db,
        f"""SELECT e.id, e.kind, e.name, e.category, e.description, ({USAGE_SQL}) AS usage_count,
                   COALESCE((SELECT json_agg(json_build_object('id', a.id, 'alias', a.alias) ORDER BY a.alias) FROM catalog_aliases a WHERE a.entry_id = e.id), '[]'::json) AS aliases
            FROM catalog_entries e WHERE {' AND '.join(where)} ORDER BY e.kind, e.name""",  # noqa: S608 - constants only
        **params,
    )


@router.get("/catalog/suggest", summary="Suggest entries for a typed text (names and aliases)")
async def suggest(ctx: CtxDep, db: DbDep, kind: CatalogKind | None = None, text: str = Query(default="", max_length=100)) -> list[dict]:
    if not text.strip():
        return await q(
            db,
            "SELECT e.id, e.kind, e.name, e.category, NULL AS matched_alias FROM catalog_entries e WHERE e.organization_id = :o AND e.deleted_at IS NULL AND (CAST(:k AS varchar) IS NULL OR e.kind = :k) ORDER BY e.name LIMIT 12",
            o=ctx.org_id, k=kind,
        )
    like = f"%{text.strip()}%"
    return await q(
        db,
        """SELECT e.id, e.kind, e.name, e.category,
                  (SELECT a.alias FROM catalog_aliases a WHERE a.entry_id = e.id AND a.alias ILIKE :l LIMIT 1) AS matched_alias
           FROM catalog_entries e
           WHERE e.organization_id = :o AND e.deleted_at IS NULL AND (CAST(:k AS varchar) IS NULL OR e.kind = :k)
             AND (e.name ILIKE :l OR EXISTS (SELECT 1 FROM catalog_aliases a WHERE a.entry_id = e.id AND a.alias ILIKE :l))
           ORDER BY (lower(e.name) = lower(:t)) DESC, e.name LIMIT 12""",
        o=ctx.org_id, k=kind, l=like, t=text.strip(),
    )


@router.post("/catalog", summary="Create a catalog entry", responses={409: {"description": "A matching entry or alias already exists"}})
async def create_entry(body: EntryCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    name = body.name.strip()
    key = normalize(name)
    if not key:
        raise err(422, "INVALID_NAME", "Name must contain letters or digits.", "name")
    clash = await find_match(db, ctx.org_id, body.kind, name)
    if clash:
        raise duplicate_error(clash)
    row = await q1(
        db,
        """INSERT INTO catalog_entries (organization_id, kind, name, norm_name, category, description, created_by, updated_by)
           VALUES (:o, :k, :n, :nn, :c, :d, :u, :u) RETURNING *""",
        o=ctx.org_id, k=body.kind, n=name, nn=key, c=body.category, d=body.description, u=ctx.user_id,
    )
    for alias in body.aliases:
        await _add_alias(db, ctx, row, alias)
    await audit(db, ctx, "catalog.created", "catalog_entry", row["id"], f"{body.kind}: {name}")
    await db.commit()
    return {"id": row["id"]}


@router.patch("/catalog/{entry_id}", summary="Update a catalog entry", responses={404: {"description": ENTRY_NOT_FOUND}, 409: {"description": "Name collides with another entry"}})
async def update_entry(entry_id: UUID, body: EntryUpdate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    entry = await _entry(db, ctx, entry_id)
    data = body.model_dump(exclude_unset=True)
    if data.get("name") is not None:
        data["name"] = data["name"].strip()
        key = normalize(data["name"])
        if not key:
            raise err(422, "INVALID_NAME", "Name must contain letters or digits.", "name")
        clash = await find_match(db, ctx.org_id, entry["kind"], data["name"], exclude_id=entry_id)
        if clash:
            raise duplicate_error(clash)
        data["norm_name"] = key
    sets, params = set_clause(data, {"name", "norm_name", "category", "description"})
    if sets:
        await x(db, f"UPDATE catalog_entries SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=entry_id, u=ctx.user_id, **params)  # noqa: S608
        await audit(db, ctx, "catalog.updated", "catalog_entry", entry_id, entry["name"])
    await db.commit()
    return {"ok": True}


@router.delete("/catalog/{entry_id}", summary="Delete an unused catalog entry (soft)", responses={409: {"description": "Entry is still in use - merge it instead"}})
async def delete_entry(entry_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    entry = await _entry(db, ctx, entry_id)
    usage = await q1(db, f"SELECT ({USAGE_SQL}) AS n FROM catalog_entries e WHERE e.id = :id", id=entry_id)  # noqa: S608
    if usage and usage["n"] > 0:
        raise err(409, "CATALOG_IN_USE", "This entry is in use. Merge it into another entry instead of deleting it.")
    await x(db, "UPDATE catalog_entries SET deleted_at = NOW(), updated_by = :u WHERE id = :id", id=entry_id, u=ctx.user_id)
    await audit(db, ctx, "catalog.deleted", "catalog_entry", entry_id, entry["name"])
    await db.commit()
    return {"ok": True}


@router.post("/catalog/{entry_id}/aliases", summary="Add an alias to an entry", responses={409: {"description": "Alias already used by another entry"}})
async def add_alias(entry_id: UUID, body: AliasCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    entry = await _entry(db, ctx, entry_id)
    await _add_alias(db, ctx, entry, body.alias)
    await db.commit()
    return {"ok": True}


@router.delete("/catalog/aliases/{alias_id}", summary="Remove an alias")
async def delete_alias(alias_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    await x(db, "DELETE FROM catalog_aliases WHERE id = :id AND organization_id = :o", id=alias_id, o=ctx.org_id)
    await db.commit()
    return {"ok": True}


@router.post("/catalog/{entry_id}/merge", summary="Merge this entry into another one", responses={422: {"description": "Entries must be different and of the same kind"}})
async def merge(entry_id: UUID, body: MergeBody, ctx: CtxDep, db: DbDep) -> dict:
    require_admin(ctx)
    source = await _entry(db, ctx, entry_id)
    target = await _entry(db, ctx, body.target_id)
    if source["id"] == target["id"] or source["kind"] != target["kind"]:
        raise err(422, "INVALID_MERGE", "Choose a different entry of the same kind as merge target.", "target_id")
    moved = await merge_entries(db, ctx.org_id, source, target, ctx.user_id)
    await audit(db, ctx, "catalog.merged", "catalog_entry", target["id"], f"Merged “{source['name']}” into “{target['name']}”", moved)
    await db.commit()
    return {"ok": True, "moved": moved}


@router.get("/roles/{role_id}/competencies", summary="Competencies and technologies associated with a role")
async def role_competencies(role_id: UUID, ctx: CtxDep, db: DbDep) -> list[dict]:
    await require_role(db, ctx, role_id)
    return await q(
        db,
        """SELECT e.id, e.kind, e.name, e.category FROM role_catalog_links l JOIN catalog_entries e ON e.id = l.entry_id AND e.deleted_at IS NULL
           WHERE l.role_id = :r ORDER BY e.name""",
        r=role_id,
    )


@router.put("/roles/{role_id}/competencies", summary="Replace the competencies of a role", responses={404: {"description": "Role or entry not found"}})
async def set_role_competencies(role_id: UUID, body: CompetencyIds, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    await require_role(db, ctx, role_id)
    await x(db, "DELETE FROM role_catalog_links WHERE role_id = :r", r=role_id)
    for eid in set(body.entry_ids):
        await _entry(db, ctx, eid)
        await x(db, "INSERT INTO role_catalog_links (organization_id, role_id, entry_id) VALUES (:o, :r, :e)", o=ctx.org_id, r=role_id, e=eid)
    await db.commit()
    return {"ok": True}
