"""Controlled vocabulary helpers: normalisation, duplicate detection and merge."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from services.dbx import q, q1, x

CATALOG_KINDS = (
    "technology",
    "industry",
    "research_area",
    "competency",
    "method",
    "application_domain",
    "solution_type",
    "reusable_component",
)

_STRIP = re.compile(r"[^a-z0-9+#]+")


def normalize(value: str) -> str:
    """Comparison key: lower-case, only letters, digits, '+' and '#' (so 'Node.js' == 'NodeJS', 'C#' != 'C')."""
    return _STRIP.sub("", value.casefold())


def duplicate_error(existing: dict[str, Any], what: str = "entry") -> HTTPException:
    return HTTPException(
        status_code=409,
        detail={
            "code": "CATALOG_DUPLICATE",
            "message": f"A matching {what} already exists: “{existing['name']}”.",
            "field": "name",
            "details": {"existing": {"id": str(existing["id"]), "name": existing["name"], "kind": existing["kind"]}},
        },
    )


async def find_match(db, org_id: UUID, kind: str, name: str, exclude_id: UUID | None = None) -> dict | None:
    """Entry of the same kind whose name OR alias normalises to the same key."""
    key = normalize(name)
    if not key:
        return None
    return await q1(
        db,
        """SELECT e.id, e.name, e.kind FROM catalog_entries e
           WHERE e.organization_id = :o AND e.kind = :k AND e.deleted_at IS NULL
             AND (CAST(:ex AS uuid) IS NULL OR e.id <> CAST(:ex AS uuid))
             AND (e.norm_name = :n OR EXISTS (SELECT 1 FROM catalog_aliases a WHERE a.entry_id = e.id AND a.norm_alias = :n))
           LIMIT 1""",
        o=org_id, k=kind, n=key, ex=exclude_id,
    )


async def merge_entries(db, org_id: UUID, source: dict, target: dict, actor: UUID) -> dict[str, int]:
    """Re-point every reference of `source` to `target`, keep the old name as alias, soft-delete `source`."""
    moved = {}
    rows = await q(
        db,
        """UPDATE project_catalog_links SET entry_id = :t
           WHERE entry_id = :s AND project_id NOT IN (SELECT project_id FROM project_catalog_links WHERE entry_id = :t) RETURNING id""",
        s=source["id"], t=target["id"],
    )
    moved["projects"] = len(rows)
    await x(db, "DELETE FROM project_catalog_links WHERE entry_id = :s", s=source["id"])
    rows = await q(
        db,
        """UPDATE role_catalog_links SET entry_id = :t
           WHERE entry_id = :s AND role_id NOT IN (SELECT role_id FROM role_catalog_links WHERE entry_id = :t) RETURNING id""",
        s=source["id"], t=target["id"],
    )
    moved["roles"] = len(rows)
    await x(db, "DELETE FROM role_catalog_links WHERE entry_id = :s", s=source["id"])
    rows = await q(db, "UPDATE crm_organizations SET industry_entry_id = :t WHERE industry_entry_id = :s RETURNING id", s=source["id"], t=target["id"])
    moved["customers"] = len(rows)
    # Aliases of the source become aliases of the target (skip those the target already answers to).
    await x(
        db,
        """UPDATE catalog_aliases SET entry_id = :t WHERE entry_id = :s AND norm_alias <> :tn
             AND norm_alias NOT IN (SELECT norm_alias FROM catalog_aliases WHERE entry_id = :t)""",
        s=source["id"], t=target["id"], tn=target["norm_name"],
    )
    await x(db, "DELETE FROM catalog_aliases WHERE entry_id = :s", s=source["id"])
    if source["norm_name"] != target["norm_name"]:
        await x(
            db,
            """INSERT INTO catalog_aliases (organization_id, entry_id, kind, alias, norm_alias) VALUES (:o, :t, :k, :a, :n)
               ON CONFLICT (organization_id, kind, norm_alias) DO NOTHING""",
            o=org_id, t=target["id"], k=target["kind"], a=source["name"], n=source["norm_name"],
        )
    await x(db, "UPDATE catalog_entries SET deleted_at = NOW(), updated_by = :u WHERE id = :s", s=source["id"], u=actor)
    return moved
