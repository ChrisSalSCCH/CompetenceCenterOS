"""Documents attached to projects, opportunities, proposals, contracts, NDAs and organizations.

A document is a link, an uploaded file (object storage, signed URLs only) or - later - a SharePoint item.
Every read and download passes the entity's access check and the document's confidentiality level;
anything the caller may not see is answered with 404 so it cannot be probed.
"""

from __future__ import annotations

from typing import Literal
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, Field
from routes.agreements import _can_edit_contract, _can_edit_nda, _contract, _nda
from routes.portfolio import _can_edit as _can_edit_project
from routes.work import _project
from services.commercial_db import can_edit_opp, check_member, get_opp
from services.ctx import CtxDep, require_write
from services.dbx import DbDep, err, q, q1, set_clause, x
from services.events import audit
from services.storage import get_serve_url, owns_key

router = APIRouter(prefix="/api/documents", tags=["documents"])

EntityType = Literal["project", "opportunity", "proposal", "contract", "nda", "crm_organization"]
Category = Literal["contract", "proposal", "nda", "report", "technical", "other"]
Confidentiality = Literal["internal", "restricted", "confidential"]
StorageKind = Literal["link", "file", "sharepoint"]
DOC_NOT_FOUND = "Document not found."
URL_PATTERN = r"^https://"
MAX_BYTES = 1024 * 1024 * 1024


class DocumentCreate(BaseModel):
    entity_type: EntityType
    entity_id: UUID
    name: str = Field(min_length=1, max_length=200)
    category: Category = "other"
    confidentiality: Confidentiality = "internal"
    storage_kind: StorageKind = "link"
    url: str | None = Field(default=None, max_length=1000, pattern=r"^https?://")
    file_key: str | None = Field(default=None, max_length=600)
    filename: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=120)
    size_bytes: int | None = Field(default=None, ge=0, le=MAX_BYTES)
    description: str = Field(default="", max_length=1000)
    access_user_ids: list[UUID] = Field(default_factory=list, max_length=50)


class DocumentUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    category: Category | None = None
    confidentiality: Confidentiality | None = None
    description: str | None = Field(default=None, max_length=1000)
    access_user_ids: list[UUID] | None = Field(default=None, max_length=50)


class VersionCreate(BaseModel):
    storage_kind: StorageKind = "file"
    url: str | None = Field(default=None, max_length=1000, pattern=r"^https?://")
    file_key: str | None = Field(default=None, max_length=600)
    filename: str | None = Field(default=None, max_length=255)
    content_type: str | None = Field(default=None, max_length=120)
    size_bytes: int | None = Field(default=None, ge=0, le=MAX_BYTES)
    comment: str | None = Field(default=None, max_length=500)


# ---------------------------------------------------------------- helpers


async def _entity_access(db, ctx, entity_type: str, entity_id: UUID) -> bool:
    """Raise 404 when the entity does not exist; return whether the caller may edit it."""
    if entity_type == "project":
        p = await _project(db, ctx, entity_id)
        return await _can_edit_project(db, ctx, p)
    if entity_type == "opportunity":
        return await can_edit_opp(db, ctx, await get_opp(db, ctx, entity_id))
    if entity_type == "proposal":
        prop = await q1(db, "SELECT opportunity_id FROM proposals WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=entity_id, o=ctx.org_id)
        if prop is None:
            raise err(404, "PROPOSAL_NOT_FOUND", "Proposal not found.")
        return await can_edit_opp(db, ctx, await get_opp(db, ctx, prop["opportunity_id"]))
    if entity_type == "contract":
        return await _can_edit_contract(db, ctx, await _contract(db, ctx, entity_id))
    if entity_type == "nda":
        return await _can_edit_nda(db, ctx, await _nda(db, ctx, entity_id))
    org = await q1(db, "SELECT 1 AS ok FROM crm_organizations WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=entity_id, o=ctx.org_id)
    if org is None:
        raise err(404, "CRM_ORG_NOT_FOUND", "Organization not found.")
    return ctx.level != "observer"


def _visible(ctx, doc: dict, can_edit: bool, in_access_list: bool) -> bool:
    """Confidentiality: internal = every member (observers too), restricted = editors and listed people, confidential = listed people only."""
    if ctx.level == "org_admin" or doc["created_by"] == ctx.user_id or in_access_list:
        return True
    if ctx.level == "observer":
        return doc["confidentiality"] == "internal"
    if doc["confidentiality"] == "internal":
        return True
    return doc["confidentiality"] == "restricted" and can_edit


async def _load(db, ctx, doc_id: UUID) -> tuple[dict, bool, bool]:
    """(document, caller may edit it, caller may see it) - 404 when the document does not exist."""
    doc = await q1(db, "SELECT * FROM documents WHERE id = :i AND organization_id = :o AND deleted_at IS NULL", i=doc_id, o=ctx.org_id)
    if doc is None:
        raise err(404, "DOCUMENT_NOT_FOUND", DOC_NOT_FOUND)
    can_edit_entity = await _entity_access(db, ctx, doc["entity_type"], doc["entity_id"])
    listed = await q1(db, "SELECT 1 AS ok FROM document_access WHERE document_id = :d AND user_id = :u", d=doc_id, u=ctx.user_id)
    can_edit = ctx.level != "observer" and (can_edit_entity or doc["created_by"] == ctx.user_id or ctx.level == "org_admin")
    return doc, can_edit, _visible(ctx, doc, can_edit_entity, listed is not None)


async def _load_visible(db, ctx, doc_id: UUID) -> tuple[dict, bool]:
    doc, can_edit, visible = await _load(db, ctx, doc_id)
    if not visible:
        raise err(404, "DOCUMENT_NOT_FOUND", DOC_NOT_FOUND)
    return doc, can_edit


def _check_source(kind: str, url: str | None, file_key: str | None, user_id: UUID) -> None:
    if kind == "file":
        if not file_key or not owns_key(file_key, str(user_id)):
            raise err(404, "FILE_NOT_FOUND", "The uploaded file was not found. Upload it again.", "file_key")
    elif not url:
        raise err(422, "URL_REQUIRED", "A link needs a URL.", "url")
    elif kind == "sharepoint" and not url.startswith("https://"):
        raise err(422, "URL_INVALID", "A SharePoint link must start with https://.", "url")


async def _set_access(db, ctx, doc_id: UUID, user_ids: list[UUID]) -> None:
    for uid in set(user_ids):
        await check_member(db, ctx, uid, "access_user_ids")
    await x(db, "DELETE FROM document_access WHERE document_id = :d", d=doc_id)
    for uid in set(user_ids):
        await x(db, "INSERT INTO document_access (organization_id, document_id, user_id) VALUES (:o, :d, :u)", o=ctx.org_id, d=doc_id, u=uid)


def _public(doc: dict) -> dict:
    """Never hand out the storage key or raw URL of a file in lists; downloads go through the guarded endpoint."""
    out = {k: doc.get(k) for k in ("id", "entity_type", "entity_id", "name", "category", "confidentiality", "storage_kind", "filename", "content_type", "size_bytes", "current_version", "description", "created_at", "updated_at", "author_name")}
    out["is_link"] = doc["storage_kind"] != "file"
    return out


# ------------------------------------------------------------------- API


@router.get("", summary="Documents of one project, opportunity, proposal, contract, NDA or organization")
async def list_documents(ctx: CtxDep, db: DbDep, entity_type: EntityType, entity_id: UUID) -> dict:
    can_edit_entity = await _entity_access(db, ctx, entity_type, entity_id)
    rows = await q(
        db,
        """SELECT d.*, u.display_name AS author_name, EXISTS (SELECT 1 FROM document_access a WHERE a.document_id = d.id AND a.user_id = :u) AS listed
           FROM documents d LEFT JOIN users u ON u.id = d.created_by
           WHERE d.organization_id = :o AND d.entity_type = :t AND d.entity_id = :e AND d.deleted_at IS NULL ORDER BY d.created_at DESC""",
        o=ctx.org_id, t=entity_type, e=entity_id, u=ctx.user_id,
    )
    visible = [d for d in rows if _visible(ctx, d, can_edit_entity, d["listed"])]
    return {"items": [_public(d) for d in visible], "hidden_count": len(rows) - len(visible), "can_edit": can_edit_entity and ctx.level != "observer"}


@router.post("", summary="Add a link, an uploaded file or a SharePoint item", responses={404: {"description": "Entity or uploaded file not found"}, 403: {"description": "Not allowed to add documents here"}})
async def create_document(body: DocumentCreate, ctx: CtxDep, db: DbDep) -> dict:
    require_write(ctx)
    if not await _entity_access(db, ctx, body.entity_type, body.entity_id):
        raise err(403, "DOCUMENT_FORBIDDEN", "You are not allowed to add documents to this record.")
    _check_source(body.storage_kind, body.url, body.file_key, ctx.user_id)
    row = await q1(
        db,
        """INSERT INTO documents (organization_id, entity_type, entity_id, name, category, confidentiality, storage_kind, url, file_key, filename, content_type, size_bytes, description, created_by, updated_by)
           VALUES (:o, :et, :ei, :n, :ca, :co, :sk, :url, :fk, :fn, :ct, :sz, :de, :u, :u) RETURNING id""",
        o=ctx.org_id, et=body.entity_type, ei=body.entity_id, n=body.name.strip(), ca=body.category, co=body.confidentiality, sk=body.storage_kind,
        url=body.url if body.storage_kind != "file" else None, fk=body.file_key if body.storage_kind == "file" else None,
        fn=body.filename, ct=body.content_type, sz=body.size_bytes, de=body.description, u=ctx.user_id,
    )
    await x(
        db,
        """INSERT INTO document_versions (organization_id, document_id, version_no, storage_kind, url, file_key, filename, content_type, size_bytes, created_by)
           VALUES (:o, :d, 1, :sk, :url, :fk, :fn, :ct, :sz, :u)""",
        o=ctx.org_id, d=row["id"], sk=body.storage_kind, url=body.url if body.storage_kind != "file" else None, fk=body.file_key if body.storage_kind == "file" else None,
        fn=body.filename, ct=body.content_type, sz=body.size_bytes, u=ctx.user_id,
    )
    if body.confidentiality != "internal" and body.access_user_ids:
        await _set_access(db, ctx, row["id"], body.access_user_ids)
    await audit(db, ctx, "document.created", body.entity_type, body.entity_id, f"Document added: {body.name}", {"document_id": str(row["id"]), "kind": body.storage_kind, "confidentiality": body.confidentiality})
    await db.commit()
    return {"id": row["id"]}


@router.get("/{doc_id}", summary="Document detail with versions and access list", responses={404: {"description": DOC_NOT_FOUND}})
async def document_detail(doc_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    doc, can_edit = await _load_visible(db, ctx, doc_id)
    author = await q1(db, "SELECT display_name AS author_name FROM users WHERE id = :u", u=doc["created_by"]) if doc["created_by"] else None
    versions = await q(
        db,
        """SELECT v.id, v.version_no, v.storage_kind, v.filename, v.content_type, v.size_bytes, v.comment, v.created_at, u.display_name AS author_name
           FROM document_versions v LEFT JOIN users u ON u.id = v.created_by WHERE v.document_id = :d ORDER BY v.version_no DESC""",
        d=doc_id,
    )
    access = await q(db, "SELECT u.id AS user_id, u.display_name AS name FROM document_access a JOIN users u ON u.id = a.user_id WHERE a.document_id = :d ORDER BY u.display_name", d=doc_id) if can_edit else []
    return {**_public({**doc, **(author or {})}), "versions": versions, "access": access, "can_edit": can_edit}


@router.patch("/{doc_id}", summary="Change name, category, confidentiality or access list")
async def update_document(doc_id: UUID, body: DocumentUpdate, ctx: CtxDep, db: DbDep) -> dict:
    doc, can_edit = await _load_visible(db, ctx, doc_id)
    if not can_edit:
        raise err(403, "DOCUMENT_FORBIDDEN", "You are not allowed to change this document.")
    data = body.model_dump(exclude_unset=True, exclude={"access_user_ids"})
    for required in ("name", "category", "confidentiality"):
        if required in data and data[required] is None:
            raise err(422, "VALIDATION_ERROR", f"{required} cannot be empty.", required)
    sets, params = set_clause(data, {"name", "category", "confidentiality", "description"})
    if sets:
        await x(db, f"UPDATE documents SET {sets}, updated_at = NOW(), updated_by = :u WHERE id = :id", id=doc_id, u=ctx.user_id, **params)  # noqa: S608
    if body.access_user_ids is not None:
        await _set_access(db, ctx, doc_id, body.access_user_ids)
    await audit(db, ctx, "document.updated", doc["entity_type"], doc["entity_id"], f"Document changed: {doc['name']}", {"document_id": str(doc_id), "fields": sorted(data)})
    await db.commit()
    return {"ok": True}


@router.post("/{doc_id}/versions", summary="Upload or link a new version", responses={404: {"description": "Document or file not found"}})
async def add_version(doc_id: UUID, body: VersionCreate, ctx: CtxDep, db: DbDep) -> dict:
    doc, can_edit = await _load_visible(db, ctx, doc_id)
    if not can_edit:
        raise err(403, "DOCUMENT_FORBIDDEN", "You are not allowed to change this document.")
    _check_source(body.storage_kind, body.url, body.file_key, ctx.user_id)
    version_no = doc["current_version"] + 1
    url = body.url if body.storage_kind != "file" else None
    key = body.file_key if body.storage_kind == "file" else None
    await x(
        db,
        """INSERT INTO document_versions (organization_id, document_id, version_no, storage_kind, url, file_key, filename, content_type, size_bytes, comment, created_by)
           VALUES (:o, :d, :n, :sk, :url, :fk, :fn, :ct, :sz, :cm, :u)""",
        o=ctx.org_id, d=doc_id, n=version_no, sk=body.storage_kind, url=url, fk=key, fn=body.filename, ct=body.content_type, sz=body.size_bytes, cm=body.comment, u=ctx.user_id,
    )
    await x(
        db,
        """UPDATE documents SET current_version = :n, storage_kind = :sk, url = :url, file_key = :fk, filename = :fn, content_type = :ct, size_bytes = :sz,
               updated_at = NOW(), updated_by = :u WHERE id = :d""",
        n=version_no, sk=body.storage_kind, url=url, fk=key, fn=body.filename, ct=body.content_type, sz=body.size_bytes, u=ctx.user_id, d=doc_id,
    )
    await audit(db, ctx, "document.version_added", doc["entity_type"], doc["entity_id"], f"{doc['name']} v{version_no}", {"document_id": str(doc_id)})
    await db.commit()
    return {"ok": True, "version_no": version_no}


@router.get("/{doc_id}/download", summary="Short-lived download URL after the access check (audited)", responses={404: {"description": DOC_NOT_FOUND}})
async def download(doc_id: UUID, ctx: CtxDep, db: DbDep, version: int | None = Query(default=None, ge=1)) -> dict:
    doc, _ = await _load_visible(db, ctx, doc_id)
    ver = await q1(
        db,
        "SELECT storage_kind, url, file_key, filename FROM document_versions WHERE document_id = :d AND version_no = :v",
        d=doc_id, v=version or doc["current_version"],
    )
    if ver is None:
        raise err(404, "DOCUMENT_NOT_FOUND", DOC_NOT_FOUND)
    if ver["storage_kind"] == "file":
        try:
            url = get_serve_url(ver["file_key"])
        except ValueError as exc:
            raise err(404, "FILE_NOT_FOUND", "The stored file is no longer available.") from exc
    else:
        url = ver["url"]
    await audit(db, ctx, "document.downloaded", doc["entity_type"], doc["entity_id"], f"Document opened: {doc['name']}", {"document_id": str(doc_id), "version": version or doc["current_version"]})
    await db.commit()
    return {"url": url, "name": ver["filename"] or doc["name"], "kind": ver["storage_kind"]}


@router.delete("/{doc_id}", summary="Remove a document (soft)")
async def delete_document(doc_id: UUID, ctx: CtxDep, db: DbDep) -> dict:
    doc, can_edit = await _load_visible(db, ctx, doc_id)
    if not can_edit:
        raise err(403, "DOCUMENT_FORBIDDEN", "You are not allowed to remove this document.")
    await x(db, "UPDATE documents SET deleted_at = NOW(), updated_by = :u WHERE id = :i", i=doc_id, u=ctx.user_id)
    await audit(db, ctx, "document.deleted", doc["entity_type"], doc["entity_id"], f"Document removed: {doc['name']}", {"document_id": str(doc_id)})
    await db.commit()
    return {"ok": True}
