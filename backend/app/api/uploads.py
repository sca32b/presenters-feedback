from fastapi import APIRouter, Depends

from app.auth import get_current_user
from app.models.schemas import UploadRequest, UploadResponse
from app.services.storage import generate_presigned_upload_url

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
