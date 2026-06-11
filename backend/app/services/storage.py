"""S3 operations for audio file storage.

In LOCAL_DEV mode, generates fake presigned URLs and stores files locally.
"""

import logging
import os
import uuid

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Local dev: directory for uploaded audio files
_LOCAL_UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "_local_uploads")


def generate_presigned_upload_url(user_id: str, filename: str, content_type: str) -> tuple[str, str]:
    """Generate a presigned S3 URL for uploading an audio file.

    Returns (upload_url, object_key).
    """
    ext = filename.rsplit(".", 1)[-1] if "." in filename else "webm"
    object_key = f"uploads/{user_id}/{uuid.uuid4()}.{ext}"

    if settings.local_dev:
        # In local dev, the "presigned URL" is a local endpoint on the backend
        upload_url = f"http://localhost:8000/api/local-upload/{object_key}"
        logger.info("LOCAL_DEV: Generated upload URL for %s", object_key)
        return upload_url, object_key

    import boto3
    s3_client = boto3.client("s3", region_name=settings.aws_region)
    upload_url = s3_client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": object_key,
            "ContentType": content_type,
        },
        ExpiresIn=settings.upload_url_expiry,
    )
    return upload_url, object_key


def save_local_upload(object_key: str, data: bytes):
    """Save uploaded file data locally (LOCAL_DEV only)."""
    file_path = os.path.join(_LOCAL_UPLOAD_DIR, object_key.replace("/", os.sep))
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "wb") as f:
        f.write(data)
    logger.info("LOCAL_DEV: Saved upload to %s (%d bytes)", file_path, len(data))


def get_local_upload_path(object_key: str) -> str:
    """Get the local filesystem path for an uploaded file (LOCAL_DEV only)."""
    return os.path.join(_LOCAL_UPLOAD_DIR, object_key.replace("/", os.sep))


def get_s3_object_body(object_key: str) -> bytes:
    """Download an object from S3 and return its body bytes."""
    import boto3
    s3 = boto3.client("s3", region_name=settings.aws_region)
    response = s3.get_object(Bucket=settings.s3_bucket, Key=object_key)
    return response["Body"].read()
