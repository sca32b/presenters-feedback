"""Orchestrates the full analysis pipeline.

Pipeline: upload audio -> transcribe (STT) -> extract audio features (librosa)
-> Bedrock Claude analysis -> store results.

In LOCAL_DEV mode, all services return mock data so the pipeline can be
exercised without AWS credentials.
"""

import asyncio
import logging
import uuid
from concurrent.futures import ThreadPoolExecutor

from app.config.settings import settings
from app.models.database import create_analysis, update_analysis_status
from app.services.audio_features import extract_audio_features_from_s3
from app.services.bedrock import analyze_presentation
from app.services.transcribe import (
    start_transcription,
    wait_for_transcription,
    extract_transcript_features,
)

logger = logging.getLogger(__name__)

# Thread pool for running synchronous librosa code without blocking the event loop
_executor = ThreadPoolExecutor(max_workers=2)


async def run_analysis(user_id: str, object_key: str) -> str:
    """Run the full analysis pipeline for an audio recording.

    Creates a new DB record and runs the pipeline. Use run_analysis_for_existing
    when the DB record has already been created (e.g. by a route handler).

    Args:
        user_id: Authenticated user's ID.
        object_key: S3 key of the uploaded audio file.

    Returns:
        The analysis_id (UUID string) for polling status.
    """
    analysis_id = str(uuid.uuid4())

    # Create tracking record
    create_analysis(analysis_id, user_id, object_key)
    logger.info("Created analysis %s for user %s", analysis_id, user_id)

    await _execute_pipeline(analysis_id, object_key)
    return analysis_id


async def run_analysis_for_existing(
    analysis_id: str, user_id: str, object_key: str
) -> None:
    """Run the analysis pipeline for a pre-created DB record.

    Use this when the route handler has already created the analysis record
    via database.create_analysis() and needs to run the pipeline in the
    background.
    """
    logger.info("Starting pipeline for existing analysis %s (user %s)", analysis_id, user_id)
    await _execute_pipeline(analysis_id, object_key)


async def _execute_pipeline(analysis_id: str, object_key: str) -> None:
    """Core pipeline: transcribe + audio features -> Bedrock analysis -> store results."""
    job_name = f"pf-{analysis_id}"

    try:
        # Step 1: Start transcription and extract audio features concurrently.
        # Transcription is async (start then poll), audio extraction is CPU-bound.
        transcribe_task = asyncio.create_task(
            _run_transcription(object_key, job_name)
        )
        loop = asyncio.get_event_loop()
        audio_task = loop.run_in_executor(
            _executor,
            lambda: extract_audio_features_from_s3(settings.s3_bucket, object_key),
        )

        transcript_json, audio_features = await asyncio.gather(
            transcribe_task, audio_task
        )

        # Step 2: Extract structured features from the raw Transcribe output
        transcript_features = extract_transcript_features(transcript_json)
        logger.info(
            "Analysis %s: %d words, %.1f WPM, %d filler words",
            analysis_id,
            transcript_features["total_words"],
            transcript_features["words_per_minute"],
            transcript_features["filler_word_count"],
        )

        # Step 3: Comprehensive analysis via Bedrock Claude
        analysis_results = await analyze_presentation(
            transcript_features, audio_features
        )

        # Step 4: Store results
        update_analysis_status(analysis_id, "completed", results=analysis_results)
        logger.info("Analysis %s completed successfully", analysis_id)

    except Exception:
        logger.exception("Analysis %s failed", analysis_id)
        update_analysis_status(analysis_id, "failed")


async def _run_transcription(object_key: str, job_name: str) -> dict:
    """Start transcription and wait for results."""
    await start_transcription(object_key, job_name)
    return await wait_for_transcription(job_name)
