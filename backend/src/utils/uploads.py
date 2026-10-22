"""Upload validation helpers for file-upload endpoints.

Use from any route that accepts an UploadFile:

    from fastapi import File, UploadFile
    from utils.uploads import validate_upload, IMAGE_MIMES

    @router.post("/avatar")
    async def upload_avatar(file: UploadFile = File(...)):
        data = await validate_upload(
            file, max_mb=5, allowed_mimes=IMAGE_MIMES
        )
        # data is bytes; file pointer is rewound for re-reads.
        ...

NEVER accept UploadFile without calling this — unchecked uploads are
a classic DoS / malware-injection vector.
"""

from fastapi import HTTPException, UploadFile

# Reusable MIME whitelists — prefer these over ad-hoc sets in routes
# so upload policies don't drift across endpoints.
IMAGE_MIMES: set[str] = {
    "image/jpeg",
    "image/png",
    "image/webp",
    "image/gif",
}
DOCUMENT_MIMES: set[str] = {
    "application/pdf",
    "text/plain",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
}


async def validate_upload(
    file: UploadFile,
    *,
    max_mb: int = 5,
    allowed_mimes: set[str] | None = None,
) -> bytes:
    """Validate an UploadFile and return its raw bytes.

    Checks run in this order (fail-fast):
      1. MIME type against `allowed_mimes` (if provided) → 415
      2. Size against `max_mb` limit → 413

    Both errors raise HTTPException with a structured `detail` dict that
    the global exception handler wraps into the standard error envelope.
    After validation the file pointer is rewound via `seek(0)` so the
    caller can re-read (e.g., pass to an S3 SDK) or use the returned
    bytes directly.

    NOTE on MIME trust: `file.content_type` comes from the HTTP Content-Type
    header, which the client sets — it is NOT authoritative. For defense
    in depth, callers that process images should additionally verify with
    a library like python-magic or Pillow.open() before persisting.
    """
    if allowed_mimes is not None and file.content_type not in allowed_mimes:
        raise HTTPException(
            status_code=415,
            detail={
                "code": "UNSUPPORTED_MEDIA_TYPE",
                "message": f"Content-type {file.content_type!r} not allowed",
                "field": "file",
                "details": {"allowed": sorted(allowed_mimes)},
            },
        )
    max_bytes = max_mb * 1024 * 1024
    data = await file.read()
    if len(data) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail={
                "code": "PAYLOAD_TOO_LARGE",
                "message": f"File exceeds {max_mb}MB limit",
                "field": "file",
                "details": {"size_bytes": len(data), "max_bytes": max_bytes},
            },
        )
    await file.seek(0)
    return data
