import asyncio
import logging
import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.api import health, uploads, analyses
from app.config.settings import settings

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.local_dev else logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)

logger = logging.getLogger(__name__)

app = FastAPI(
    title="Presenter Feedback API",
    version="0.1.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_allowed_origins.split(","),
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(health.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")
app.include_router(analyses.router, prefix="/api")

# In LOCAL_DEV mode, register the local file upload endpoint.
# This handles PUT requests that the frontend sends to the "presigned URL"
# which in local dev points to http://localhost:8000/api/local-upload/{key}.
if settings.local_dev:
    from app.api.local_upload import router as local_upload_router
    app.include_router(local_upload_router, prefix="/api")

# Lambda handler via Mangum
# Strip the API Gateway stage prefix (e.g. "/dev") from the path
_stage = settings.environment
_mangum = Mangum(app, lifespan="off", api_gateway_base_path=f"/{_stage}" if _stage else "/")


def handler(event, context):
    """Lambda entry point. Routes between API Gateway events and async analysis events."""
    # Check if this is an async analysis invocation (not an API Gateway event)
    if event.get("action") == "run_analysis":
        logger.info("Running async analysis pipeline for %s", event.get("analysis_id"))
        asyncio.get_event_loop().run_until_complete(
            analyses.run_analysis_pipeline(
                analysis_id=event["analysis_id"],
                user_id=event["user_id"],
                object_key=event["object_key"],
            )
        )
        return {"status": "done"}

    # Otherwise, handle as API Gateway HTTP event
    return _mangum(event, context)
