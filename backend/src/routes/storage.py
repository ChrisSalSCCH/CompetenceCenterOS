from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from services.auth import get_current_user_id
from services.storage import (
    FileTooLargeError, UnsupportedFileTypeError, delete_file, finalize_upload, get_serve_url,
    get_upload_url, is_shared_key, list_files, owns_key,
)

router = APIRouter(prefix="/api/storage", tags=["storage"])

FILE_NOT_FOUND = "File not found"
FILE_TOO_LARGE = "File is too large"
FILE_TYPE_NOT_ALLOWED = "File type is not allowed"
AUTH_RESPONSES = {401: {"description": "Not authenticated"}}
FILE_RESPONSES = {**AUTH_RESPONSES, 404: {"description": FILE_NOT_FOUND}}
UPLOAD_RESPONSES = {**AUTH_RESPONSES, 413: {"description": FILE_TOO_LARGE},
                    415: {"description": FILE_TYPE_NOT_ALLOWED}}

CurrentUser = Annotated[UUID, Depends(get_current_user_id)]


class UploadUrlRequest(BaseModel):
    size: int = Field(gt=0)
    content_type: str = "application/octet-stream"


class FinalizeRequest(BaseModel):
    upload_key: str
    filename: str
    folder: str = ""
    is_public: bool = False


@router.post("/upload-url", responses=UPLOAD_RESPONSES)
def create_upload_url(req: UploadUrlRequest, user_id: CurrentUser):
    try:
        return get_upload_url(req.size, req.content_type, owner_id=str(user_id))
    except FileTooLargeError:
        raise HTTPException(status_code=413, detail=FILE_TOO_LARGE)
    except UnsupportedFileTypeError:
        raise HTTPException(status_code=415, detail=FILE_TYPE_NOT_ALLOWED)


@router.post("/finalize", responses={**UPLOAD_RESPONSES, 404: {"description": FILE_NOT_FOUND}})
def finalize_file(req: FinalizeRequest, user_id: CurrentUser):
    try:
        return finalize_upload(req.upload_key, req.filename, owner_id=str(user_id),
                               folder=req.folder, is_public=req.is_public)
    except FileTooLargeError:
        raise HTTPException(status_code=413, detail=FILE_TOO_LARGE)
    except UnsupportedFileTypeError:
        raise HTTPException(status_code=415, detail=FILE_TYPE_NOT_ALLOWED)
    except (FileNotFoundError, ValueError):
        raise HTTPException(status_code=404, detail=FILE_NOT_FOUND)


@router.get("/url/{file_key:path}", responses=FILE_RESPONSES)
def get_file_url(file_key: str, user_id: CurrentUser):
    # is_public=True files are readable by any signed-in user, private ones only by the owner.
    if not (is_shared_key(file_key) or owns_key(file_key, str(user_id))):
        raise HTTPException(status_code=404, detail=FILE_NOT_FOUND)
    try:
        return {"url": get_serve_url(file_key)}
    except ValueError:
        raise HTTPException(status_code=404, detail=FILE_NOT_FOUND)


@router.get("/files", responses=AUTH_RESPONSES)
def get_files(user_id: CurrentUser, prefix: str = "", visibility: str = "private"):
    try:
        return list_files(prefix, visibility, owner_id=str(user_id))
    except ValueError:
        return []


@router.delete("/files/{file_key:path}", responses=FILE_RESPONSES)
def remove_file(file_key: str, user_id: CurrentUser):
    if not owns_key(file_key, str(user_id)):
        raise HTTPException(status_code=404, detail=FILE_NOT_FOUND)
    try:
        return {"success": delete_file(file_key)}
    except ValueError:
        raise HTTPException(status_code=404, detail=FILE_NOT_FOUND)
