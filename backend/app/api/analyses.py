import asyncio
import json
import logging
import os
import subprocess
import tempfile
import uuid
from concurrent.futures import ThreadPoolExecutor

import boto3
from fastapi import APIRouter, Depends, HTTPException, Query

from app.auth import get_current_user
from app.config.settings import settings
from app.models.database import (
    create_analysis as db_create_analysis,
    delete_analysis as db_delete_analysis,
    get_analysis as db_get_analysis,
    list_analyses_for_user,
    update_analysis_status,
)
from app.models.schemas import (
    AnalysisCreateRequest,
    AnalysisCreateResponse,
    AnalysisResponse,
    AnalysisListResponse,
)
from app.services.audio_features import extract_audio_features_from_s3
from app.services.transcribe import (
    start_transcription,
    wait_for_transcription,
    extract_transcript_features,
)
from app.services.bedrock import analyze_presentation

logger = logging.getLogger(__name__)

router = APIRouter(tags=["analyses"])

# Thread pool for CPU-bound librosa audio extraction
_executor = ThreadPoolExecutor(max_workers=2)


def _convert_to_wav(bucket: str, object_key: str) -> str:
    """Download audio from S3, convert to WAV via ffmpeg, upload WAV back to S3.

    Returns the S3 key of the converted WAV file.
    Transcribe handles WAV reliably across all browsers.
    """
    s3 = boto3.client("s3", region_name=settings.aws_region)
    ext = object_key.rsplit(".", 1)[-1] if "." in object_key else "webm"
    tmp_in = os.path.join(tempfile.gettempdir(), f"input.{ext}")
    tmp_out = os.path.join(tempfile.gettempdir(), "output.wav")

    try:
        s3.download_file(bucket, object_key, tmp_in)
        subprocess.run(
            ["ffmpeg", "-y", "-i", tmp_in, "-ar", "16000", "-ac", "1", tmp_out],
            check=True,
            capture_output=True,
            timeout=60,
        )
        wav_key = object_key.rsplit(".", 1)[0] + ".wav"
        s3.upload_file(tmp_out, bucket, wav_key, ExtraArgs={"ContentType": "audio/wav"})
        logger.info("Converted %s -> %s", object_key, wav_key)
        return wav_key
    finally:
        for f in (tmp_in, tmp_out):
            if os.path.exists(f):
                os.remove(f)


async def run_analysis_pipeline(analysis_id: str, user_id: str, object_key: str):
    """Run the full analysis pipeline. Called from the Lambda handler for async invocations."""
    try:
        job_name = f"pf-{analysis_id}"

        # Step 0: Convert audio to WAV for reliable Transcribe processing
        loop = asyncio.get_event_loop()
        if settings.local_dev or object_key.endswith(".wav"):
            transcribe_key = object_key
        else:
            transcribe_key = await loop.run_in_executor(
                _executor, lambda: _convert_to_wav(settings.s3_bucket, object_key)
            )

        # Step 1 & 2 run concurrently: transcription (I/O) and audio feature extraction (CPU)
        transcribe_task = asyncio.ensure_future(
            _transcribe(transcribe_key, job_name)
        )

        loop = asyncio.get_event_loop()
        audio_task = loop.run_in_executor(
            _executor,
            lambda: extract_audio_features_from_s3(settings.s3_bucket, object_key),
        )

        transcript_json, audio_features = await asyncio.gather(
            transcribe_task, audio_task
        )

        # Step 3: Extract structured features from the raw Transcribe output
        transcript_features = extract_transcript_features(transcript_json)
        logger.info(
            "Analysis %s: %d words, %.1f WPM, %d fillers",
            analysis_id,
            transcript_features["total_words"],
            transcript_features["words_per_minute"],
            transcript_features["filler_word_count"],
        )

        # Step 4: Comprehensive analysis via Bedrock Claude
        analysis_results = await analyze_presentation(
            transcript_features, audio_features
        )

        # Step 5: Store results
        update_analysis_status(analysis_id, "completed", analysis_results)
        logger.info("Analysis %s completed successfully", analysis_id)

    except Exception:
        logger.exception("Analysis %s failed", analysis_id)
        update_analysis_status(analysis_id, "failed")


async def _run_analysis_pipeline(analysis_id: str, user_id: str, object_key: str):
    """Backward-compatible test/helper alias for the analysis pipeline."""
    await run_analysis_pipeline(analysis_id, user_id, object_key)


async def _transcribe(object_key: str, job_name: str) -> dict:
    """Start transcription and wait for results."""
    await start_transcription(object_key, job_name)
    return await wait_for_transcription(job_name)


def _invoke_analysis_async(analysis_id: str, user_id: str, object_key: str):
    """Invoke this Lambda function asynchronously to run the analysis pipeline."""
    function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME", "")
    if not function_name:
        logger.error("AWS_LAMBDA_FUNCTION_NAME not set, cannot invoke async analysis")
        update_analysis_status(analysis_id, "failed")
        return

    client = boto3.client("lambda", region_name=settings.aws_region)
    payload = {
        "action": "run_analysis",
        "analysis_id": analysis_id,
        "user_id": user_id,
        "object_key": object_key,
    }

    client.invoke(
        FunctionName=function_name,
        InvocationType="Event",  # Async invocation - returns immediately
        Payload=json.dumps(payload).encode(),
    )
    logger.info("Async analysis invocation sent for %s", analysis_id)


@router.post("/analyses", response_model=AnalysisCreateResponse, status_code=202)
async def create_analysis(
    request: AnalysisCreateRequest,
    user: dict = Depends(get_current_user),
):
    """Start analysis for an uploaded audio file.

    Creates a tracking record and launches the analysis pipeline asynchronously.
    Poll GET /analyses/{id} to check status.
    """
    user_id = user["user_id"]

    # Authorization: the object key must belong to this user
    if not request.object_key.startswith(f"uploads/{user_id}/"):
        raise HTTPException(
            status_code=403,
            detail="Access denied: object key does not belong to this user",
        )

    analysis_id = str(uuid.uuid4())

    db_create_analysis(
        analysis_id=analysis_id,
        user_id=user_id,
        object_key=request.object_key,
    )

    if settings.local_dev:
        # In local dev, run in background task since we don't have Lambda
        import asyncio
        asyncio.get_event_loop().create_task(
            run_analysis_pipeline(analysis_id, user_id, request.object_key)
        )
    else:
        # In Lambda, invoke self asynchronously so POST returns immediately
        _invoke_analysis_async(analysis_id, user_id, request.object_key)

    return AnalysisCreateResponse(analysis_id=analysis_id, status="processing")


@router.get("/analyses/{analysis_id}", response_model=AnalysisResponse)
async def get_analysis(
    analysis_id: str,
    user: dict = Depends(get_current_user),
):
    """Get analysis status and results."""
    item = db_get_analysis(analysis_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Analysis not found")

    # Authorization: only the owning user can view their analysis
    if item.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=404, detail="Analysis not found")

    return AnalysisResponse(
        analysis_id=item["analysis_id"],
        status=item["status"],
        created_at=item["created_at"],
        results=item.get("results"),
    )


@router.delete("/analyses/{analysis_id}", status_code=204)
async def delete_analysis(
    analysis_id: str,
    user: dict = Depends(get_current_user),
):
    """Delete an analysis and its associated audio file."""
    item = db_get_analysis(analysis_id)
    if item is None or item.get("user_id") != user["user_id"]:
        raise HTTPException(status_code=404, detail="Analysis not found")

    object_key = item.get("object_key")

    db_delete_analysis(analysis_id)

    # Delete the audio file from S3
    if object_key:
        try:
            s3 = boto3.client("s3", region_name=settings.aws_region)
            s3.delete_object(Bucket=settings.s3_bucket, Key=object_key)
        except Exception:
            logger.warning(
                "Failed to delete S3 object %s for analysis %s",
                object_key,
                analysis_id,
                exc_info=True,
            )

    return None


@router.get("/analyses", response_model=AnalysisListResponse)
async def list_analyses(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    user: dict = Depends(get_current_user),
):
    """List user's past analyses (paginated)."""
    items, total = list_analyses_for_user(
        user_id=user["user_id"],
        page=page,
        page_size=page_size,
    )

    return AnalysisListResponse(
        items=[
            AnalysisResponse(
                analysis_id=item["analysis_id"],
                status=item["status"],
                created_at=item["created_at"],
                results=item.get("results"),
            )
            for item in items
        ],
        total=total,
        page=page,
        page_size=page_size,
    )
