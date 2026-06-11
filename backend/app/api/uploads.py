from fastapi import APIRouter, Depends, Request, Response, status

from app.auth import get_current_user
from app.config.settings import settings
from app.models.schemas import UploadRequest, UploadResponse
from app.services.storage import generate_presigned_upload_url, save_local_upload

router = APIRouter(tags=["uploads"])


@router.post("/uploads", response_model=UploadResponse)
async def create_upload_url(
    request: UploadRequest,
    user: dict = Depends(get_current_user),
):
    """Generate a presigned S3 URL for audio upload."""
    upload_url, object_key = generate_presigned_upload_url(
        user_id=user["user_id"],
        filename=request.filename,
        content_type=request.content_type,
    )
    return UploadResponse(upload_url=upload_url, object_key=object_key)


@router.put("/local-upload/{object_key:path}", include_in_schema=False)
async def local_upload(object_key: str, request: Request):
    """Receive file uploads in LOCAL_DEV mode.

    The presigned URL in local dev points to this endpoint.
    """
    if not settings.local_dev:
        return Response(status_code=status.HTTP_404_NOT_FOUND)

    body = await request.body()
    save_local_upload(object_key, body)
    return Response(status_code=status.HTTP_200_OK)
