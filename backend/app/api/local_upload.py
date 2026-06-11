"""Local file upload endpoint for LOCAL_DEV mode.

In local development, presigned S3 URLs are replaced with URLs pointing to
this endpoint. The frontend PUTs audio data here instead of directly to S3.
"""

import logging

from fastapi import APIRouter, HTTPException, Request

from app.config.settings import settings
from app.services.storage import save_local_upload

logger = logging.getLogger(__name__)

router = APIRouter(tags=["local-upload"])


@router.put("/local-upload/{object_key:path}")
async def local_upload(object_key: str, request: Request):
    """Accept a file upload and save it locally (LOCAL_DEV only)."""
    if not settings.local_dev:
        raise HTTPException(status_code=404, detail="Not found")

    body = await request.body()
    if not body:
        raise HTTPException(status_code=400, detail="Empty request body")

    save_local_upload(object_key, body)
    logger.info("LOCAL_DEV: Received upload for %s (%d bytes)", object_key, len(body))

    return {"status": "ok", "object_key": object_key, "size": len(body)}
