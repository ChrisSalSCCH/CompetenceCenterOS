# XAIO-MANAGED: file_storage facade v2 — do not edit
# Installed and refreshed by the XAIO platform. Edits are overwritten.
"""Provider-neutral file storage for this app.

One contract on every object store (AWS S3 and S3-compatible stores, Azure Blob,
Google Cloud Storage):

1. get_upload_url(size=...)        -> a short-lived signed PUT for a STAGING key.
                                      The browser uploads directly to the store.
2. finalize_upload(upload_key=...) -> server-side: checks the size, detects the
                                      real file type from its bytes, writes the
                                      final object with safe headers, deletes the
                                      staging copy. Returns the file_key to store.
3. get_serve_url(file_key)         -> a short-lived signed GET for downloads.

No signed upload URL ever points at a final key, so a finalized file cannot be
replaced. The type the browser claims is ignored; only raster images (and
audio/video) are served inline, everything else as an attachment.

Credentials are never handled here: each provider's default credential chain is
used (AWS env / role, Azure managed identity, Google ADC).

Configuration (environment variables):
    STORAGE_PROVIDER        s3 (default) | azure | gcs
    STORAGE_BUCKET          bucket / container       (fallback: S3_BUCKET)
    STORAGE_PREFIX          key prefix for this app  (fallback: S3_PREFIX)
                            Uploads are staged under staging/<prefix>/ — outside
                            the app's files, so one lifecycle rule ("expire
                            staging/ after 1 day") cleans abandoned uploads on
                            every provider.
    STORAGE_MAX_FILE_BYTES  per-file limit           (fallback: S3_MAX_FILE_BYTES)
    STORAGE_ENDPOINT_URL    S3-compatible endpoint (MinIO, sovereign clouds)
    AWS_REGION              S3 region
    AZURE_STORAGE_ACCOUNT   Azure storage account
"""

import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import PurePosixPath

logger = logging.getLogger(__name__)


def _env(name: str, legacy: str | None = None, default: str | None = None) -> str | None:
    value = os.environ.get(name)
    if not value and legacy:
        value = os.environ.get(legacy)
    return value or default


PROVIDER = (_env("STORAGE_PROVIDER", default="s3") or "s3").lower()
BUCKET = _env("STORAGE_BUCKET", "S3_BUCKET") or ""
PREFIX = (_env("STORAGE_PREFIX", "S3_PREFIX") or "").strip("/")
STAGING_PREFIX = f"staging/{PREFIX}"
MAX_FILE_BYTES = int(_env("STORAGE_MAX_FILE_BYTES", "S3_MAX_FILE_BYTES", str(10 * 1024 * 1024)))
ENDPOINT_URL = _env("STORAGE_ENDPOINT_URL")
REGION = _env("AWS_REGION", default="eu-central-1")
AZURE_ACCOUNT = _env("AZURE_STORAGE_ACCOUNT")

UPLOAD_URL_TTL = timedelta(minutes=15)
SERVE_URL_TTL = timedelta(hours=1)
STAGING_MAX_AGE = timedelta(hours=24)
STAGING_GC_BATCH = 100
STAGING_GC_SCAN = 1000
MAX_SERVE_TTL = timedelta(days=7)
LIST_LIMIT = 1000
MAX_KEY_BYTES = 1024
SNIFF_BYTES = 512
COPY_CHUNK_BYTES = 8 * 1024 * 1024

IMAGE_TYPES = frozenset({"image/png", "image/jpeg", "image/gif", "image/webp", "image/avif"})
# Served inline (no script capability). Everything else is served as an attachment.
INLINE_TYPES = IMAGE_TYPES | {"video/mp4", "audio/mpeg"}

_OWNER_RE = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
_UPLOAD_ID_RE = re.compile(r"^[0-9a-f]{32}$")

_OCTET_STREAM = "application/octet-stream"
_UPLOAD_CHANGED = "Upload changed during finalize"


class FileTooLargeError(ValueError):
    """The declared or stored size exceeds MAX_FILE_BYTES."""


class InvalidFileKeyError(ValueError):
    """The key / owner / prefix is malformed or does not belong to the caller."""


class UnsupportedFileTypeError(ValueError):
    """The uploaded bytes are empty or not one of the allowed types."""


# obstore MUST be imported lazily (inside _store), never at module level, so a
# cold start that never touches storage does not pay for it.
_store_instance = None


def _store():
    global _store_instance
    if _store_instance is None:
        if not BUCKET or not PREFIX:
            raise RuntimeError("File storage is not configured (bucket/prefix missing)")
        if PROVIDER == "s3":
            from obstore.store import S3Store

            kwargs = {"region": REGION}
            if ENDPOINT_URL:
                kwargs["endpoint"] = ENDPOINT_URL
            _store_instance = S3Store(BUCKET, **kwargs)
        elif PROVIDER == "azure":
            from obstore.store import AzureStore

            _store_instance = AzureStore(BUCKET, account_name=AZURE_ACCOUNT)
        elif PROVIDER == "gcs":
            from obstore.store import GCSStore

            _store_instance = GCSStore(BUCKET)
        else:
            raise RuntimeError(f"Unsupported STORAGE_PROVIDER: {PROVIDER}")
    return _store_instance


# --- keys -------------------------------------------------------------------------


def _owner_segment(owner_id: str | None) -> str:
    # Key segment that isolates one user's files. Empty when the app has no login.
    if owner_id is None:
        return ""
    if not isinstance(owner_id, str) or not _OWNER_RE.match(owner_id):
        raise InvalidFileKeyError("Invalid owner id")
    return f"users/{owner_id}/"


def _staging_root(owner_id: str | None) -> str:
    return f"{STAGING_PREFIX}/{_owner_segment(owner_id)}"


def _folder_segment(folder: str) -> str:
    parts = [p for p in (folder or "").split("/") if p and p not in (".", "..")]
    if any(_has_control_chars(p) for p in parts):
        raise InvalidFileKeyError("Invalid folder")
    return "/".join(parts) + "/" if parts else ""


def _safe_name(filename: str) -> str:
    name = PurePosixPath((filename or "").replace("\\", "/")).name
    name = re.sub(r"[^A-Za-z0-9._-]", "_", name).strip("._") or "file"
    return f"{uuid.uuid4().hex[:16]}_{name[:120]}"


def _has_control_chars(value: str) -> bool:
    return any(ord(c) < 32 or ord(c) == 127 for c in value)


def _check_key(file_key: str, root: str | None = None) -> str:
    root = root or PREFIX
    if (
        not isinstance(file_key, str)
        or len(file_key.encode("utf-8")) > MAX_KEY_BYTES
        or _has_control_chars(file_key)
        or not file_key.startswith(f"{root}/")
        or any(p in ("", ".", "..") for p in file_key[len(root) + 1 :].split("/"))
    ):
        raise InvalidFileKeyError("Invalid file key")
    return file_key


def _check_final_key(file_key: str) -> str:
    _check_key(file_key)
    if file_key.startswith(f"{PREFIX}/staging/"):
        raise InvalidFileKeyError("Invalid file key")
    return file_key


# --- type detection -----------------------------------------------------------------


def _sniff(head: bytes) -> str:
    """Content type from the file's first bytes — the browser's claim is ignored."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if head.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if head.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return "image/webp"
    if head[4:8] == b"ftyp":
        return "image/avif" if head[8:12] in (b"avif", b"avis") else "video/mp4"
    if head.startswith(b"%PDF-"):
        return "application/pdf"
    if head.startswith(b"PK\x03\x04"):
        return "application/zip"
    if head.startswith(b"ID3") or head[:2] in (b"\xff\xfb", b"\xff\xf3", b"\xff\xf2"):
        return "audio/mpeg"
    if b"\x00" not in head:
        try:
            head.decode("utf-8")
            return "text/plain"  # incl. HTML/SVG: stored as plain text + attachment
        except UnicodeDecodeError:
            pass
    return _OCTET_STREAM


# --- operations -----------------------------------------------------------------------


def get_upload_url(
    size: int,
    content_type: str = _OCTET_STREAM,
    owner_id: str | None = None,
) -> dict:
    """Signed PUT URL for a direct browser upload into a staging key.

    The browser must send exactly `headers` with the PUT, then the app must call
    finalize_upload(upload_key, ...) on the server before it stores anything.
    """
    if not isinstance(size, int) or size <= 0:
        raise UnsupportedFileTypeError("Empty file")
    if size > MAX_FILE_BYTES:
        raise FileTooLargeError(f"File exceeds the {MAX_FILE_BYTES} byte limit")
    import obstore

    root = _staging_root(owner_id)
    _gc_staging(root)
    upload_key = f"{root}{uuid.uuid4().hex}"
    url = obstore.sign(_store(), "PUT", upload_key, UPLOAD_URL_TTL)
    headers = {"Content-Type": content_type or _OCTET_STREAM}
    if PROVIDER == "azure":
        headers["x-ms-blob-type"] = "BlockBlob"
    return {
        "upload_key": upload_key,
        "method": "PUT",
        "url": url,
        "headers": headers,
        "max_bytes": MAX_FILE_BYTES,
    }


def finalize_upload(
    upload_key: str,
    filename: str,
    owner_id: str | None = None,
    folder: str = "",
    is_public: bool = False,
    allowed_types: frozenset[str] | set[str] | None = None,
) -> dict:
    """Turn a staging upload into a stored file. Server-side only.

    Raises FileNotFoundError (nothing uploaded), FileTooLargeError,
    UnsupportedFileTypeError (empty / type not allowed), InvalidFileKeyError
    (malformed key or not the caller's upload). The staging copy is always
    deleted once checked.
    """
    import obstore

    _check_upload_key(upload_key, owner_id)
    store = _store()
    meta = obstore.head(store, upload_key)  # FileNotFoundError when missing
    size = int(meta["size"])
    try:
        if size > MAX_FILE_BYTES:
            raise FileTooLargeError(f"File exceeds the {MAX_FILE_BYTES} byte limit")
        if size == 0:
            raise UnsupportedFileTypeError("Empty file")
        # One read pinned to the version we sized: a re-PUT to the staging key
        # during finalize fails the read instead of swapping bytes after the sniff.
        try:
            result = obstore.get(store, upload_key, options={"if_match": meta["e_tag"]})
        except obstore.exceptions.PreconditionError as e:
            raise InvalidFileKeyError(_UPLOAD_CHANGED) from e
        chunks = iter(result.stream(min_chunk_size=COPY_CHUNK_BYTES))
        first = _read_head(chunks)
        content_type = _sniff(first[:SNIFF_BYTES])
        if allowed_types is not None and content_type not in allowed_types:
            raise UnsupportedFileTypeError(f"File type {content_type} is not allowed")

        file_key, safe = _final_key(filename, owner_id, folder, is_public)
        disposition = "inline" if content_type in INLINE_TYPES else f'attachment; filename="{safe}"'
        _ensure_absent(store, file_key)
        # Stream staging -> final in chunks (bounded memory), with headers set by us.
        # An exception inside the writer aborts it, so nothing partial is stored.
        with obstore.open_writer(
            store,
            file_key,
            attributes={"Content-Type": content_type, "Content-Disposition": disposition},
        ) as writer:
            _copy_exact(writer, first, chunks, size)
    finally:
        obstore.delete(store, upload_key)
    return {"file_key": file_key, "size": size, "content_type": content_type}


def _check_upload_key(upload_key: str, owner_id: str | None) -> None:
    """The key must be a staging upload id inside the caller's own staging root."""
    _check_key(upload_key, STAGING_PREFIX)
    root = _staging_root(owner_id)
    if not upload_key.startswith(root) or not _UPLOAD_ID_RE.match(upload_key[len(root) :]):
        raise InvalidFileKeyError("Invalid upload key")


def _read_head(chunks) -> bytes:
    """Consume chunks until at least SNIFF_BYTES are buffered (or the stream ends)."""
    first = b""
    for chunk in chunks:
        first += bytes(chunk)
        if len(first) >= SNIFF_BYTES:
            break
    return first


def _final_key(
    filename: str, owner_id: str | None, folder: str, is_public: bool
) -> tuple[str, str]:
    """The stored file's key and its sanitised name."""
    visibility = "public" if is_public else "private"
    folder_seg = _folder_segment(folder)
    if owner_id is None and folder_seg.split("/", 1)[0] == "users":
        raise InvalidFileKeyError("Invalid folder")
    safe = _safe_name(filename)
    file_key = f"{PREFIX}/{visibility}/{_owner_segment(owner_id)}{folder_seg}{safe}"
    _check_final_key(file_key)
    return file_key, safe


def _ensure_absent(store, file_key: str) -> None:
    """Never replace an existing file (the 64-bit random name makes a clash
    practically impossible; this makes it impossible)."""
    import obstore

    try:
        obstore.head(store, file_key)
        raise InvalidFileKeyError("File already exists")
    except FileNotFoundError:
        pass


def _copy_exact(writer, first: bytes, chunks, size: int) -> None:
    """Write the buffered head plus the remaining chunks; the total must be exactly
    the size we checked, or the upload changed underneath us."""
    written = len(first)
    writer.write(first)
    for chunk in chunks:
        written += len(chunk)
        if written > size:
            raise InvalidFileKeyError(_UPLOAD_CHANGED)
        writer.write(bytes(chunk))
    if written != size:
        raise InvalidFileKeyError(_UPLOAD_CHANGED)


def _gc_staging(root: str) -> None:
    """Delete this app's abandoned staging uploads (older than STAGING_MAX_AGE)."""
    import obstore

    cutoff = datetime.now(timezone.utc) - STAGING_MAX_AGE
    removed = scanned = 0
    try:
        for batch in obstore.list(_store(), prefix=root):
            for obj in batch:
                scanned += 1
                if scanned > STAGING_GC_SCAN:
                    return  # bounded work per upload request
                if obj["last_modified"] < cutoff:
                    obstore.delete(_store(), obj["path"])
                    removed += 1
                    if removed >= STAGING_GC_BATCH:
                        return
    except Exception:
        # Housekeeping only: never block the user's upload, but do not hide it.
        logger.exception("Staging cleanup failed")


def get_serve_url(file_key: str, expires_in: int = 3600) -> str:
    import obstore

    _check_final_key(file_key)
    ttl = timedelta(seconds=expires_in) if expires_in else SERVE_URL_TTL
    if not timedelta(0) < ttl <= MAX_SERVE_TTL:
        raise InvalidFileKeyError("Invalid expiry")
    return obstore.sign(_store(), "GET", file_key, ttl)


def delete_file(file_key: str) -> bool:
    import obstore

    _check_final_key(file_key)
    obstore.delete(_store(), file_key)
    return True


def list_files(
    prefix: str = "", visibility: str = "private", owner_id: str | None = None
) -> list[dict]:
    import obstore

    if (
        visibility not in ("public", "private")
        or ".." in (prefix or "").split("/")
        or _has_control_chars(prefix or "")
    ):
        raise InvalidFileKeyError("Invalid listing prefix")
    full_prefix = f"{PREFIX}/{visibility}/{_owner_segment(owner_id)}{prefix or ''}"
    files: list[dict] = []
    for batch in obstore.list(_store(), prefix=full_prefix):
        for obj in batch:
            files.append({"key": obj["path"], "size": obj["size"]})
            if len(files) >= LIST_LIMIT:
                return files
    return files


def _is_final_key(file_key: str) -> bool:
    try:
        _check_final_key(file_key)
        return True
    except InvalidFileKeyError:
        return False


def is_shared_key(file_key: str) -> bool:
    # True for keys finalized with is_public=True — readable by any signed-in user.
    return _is_final_key(file_key) and file_key.startswith(f"{PREFIX}/public/")


def owns_key(file_key: str, owner_id: str) -> bool:
    # True when file_key is one of owner_id's own finalized files (either visibility).
    # Fails closed for an empty or malformed owner id.
    if not isinstance(owner_id, str) or not _OWNER_RE.match(owner_id):
        return False
    if not _is_final_key(file_key):
        return False
    seg = f"users/{owner_id}/"
    return file_key.startswith((f"{PREFIX}/public/{seg}", f"{PREFIX}/private/{seg}"))
