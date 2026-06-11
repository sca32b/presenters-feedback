"""Amazon Transcribe integration for speech-to-text.

In LOCAL_DEV mode, returns mock transcript data.
"""

import json
import logging
import time

import boto3

from app.config.settings import settings

logger = logging.getLogger(__name__)

# Filler words to detect in transcripts
FILLER_WORDS = {
    "um", "uh", "like", "you know", "so", "basically", "actually",
    "literally", "right", "okay", "er", "ah", "hmm", "well",
}


async def start_transcription(object_key: str, job_name: str) -> str:
    """Start an Amazon Transcribe job for the given S3 object.

    Returns the job name.
    """
    if settings.local_dev:
        logger.info("LOCAL_DEV: Mock transcription started for %s", object_key)
        return job_name

    client = boto3.client("transcribe", region_name=settings.aws_region)
    media_uri = f"s3://{settings.s3_bucket}/{object_key}"

    client.start_transcription_job(
        TranscriptionJobName=job_name,
        Media={"MediaFileUri": media_uri},
        LanguageCode="en-US",
        OutputBucketName=settings.s3_bucket,
        OutputKey=f"transcripts/{job_name}.json",
    )
    return job_name


async def wait_for_transcription(job_name: str, poll_interval: int = 5, max_wait: int = 300) -> dict:
    """Poll for transcription job completion and return the raw Transcribe output.

    Returns the full transcript JSON from S3 on success.
    Raises RuntimeError on failure or timeout.
    """
    if settings.local_dev:
        logger.info("LOCAL_DEV: Returning mock transcription for %s", job_name)
        return _generate_mock_transcript()

    client = boto3.client("transcribe", region_name=settings.aws_region)
    s3 = boto3.client("s3", region_name=settings.aws_region)
    elapsed = 0

    while elapsed < max_wait:
        response = client.get_transcription_job(TranscriptionJobName=job_name)
        job = response["TranscriptionJob"]
        status = job["TranscriptionJobStatus"]

        if status == "COMPLETED":
            # Fetch the transcript JSON from S3
            transcript_key = f"transcripts/{job_name}.json"
            obj = s3.get_object(Bucket=settings.s3_bucket, Key=transcript_key)
            return json.loads(obj["Body"].read())

        if status == "FAILED":
            reason = job.get("FailureReason", "Unknown")
            raise RuntimeError(f"Transcription failed: {reason}")

        time.sleep(poll_interval)
        elapsed += poll_interval

    raise RuntimeError(f"Transcription timed out after {max_wait}s")


def extract_transcript_features(transcript_json: dict) -> dict:
    """Extract useful features from the Transcribe output JSON.

    Returns a dict with transcript text, word count, WPM, filler words, pauses, etc.
    """
    items = transcript_json.get("results", {}).get("items", [])

    words = []
    filler_count = 0
    total_words = 0
    word_timestamps = []

    for item in items:
        if item["type"] == "pronunciation":
            word = item["alternatives"][0]["content"].lower()
            confidence = float(item["alternatives"][0].get("confidence", 0))
            start_time = float(item.get("start_time", 0))
            end_time = float(item.get("end_time", 0))

            words.append(word)
            word_timestamps.append({
                "word": word,
                "start": start_time,
                "end": end_time,
                "confidence": confidence,
            })
            total_words += 1

            if word in FILLER_WORDS:
                filler_count += 1

    # Calculate speaking rate
    if word_timestamps and len(word_timestamps) > 1:
        total_duration_sec = word_timestamps[-1]["end"] - word_timestamps[0]["start"]
        total_duration_min = total_duration_sec / 60.0
        wpm = total_words / total_duration_min if total_duration_min > 0 else 0
    else:
        wpm = 0
        total_duration_sec = 0

    # Detect pauses (gaps > 1.5 seconds between words)
    pauses = []
    for i in range(1, len(word_timestamps)):
        gap = word_timestamps[i]["start"] - word_timestamps[i - 1]["end"]
        if gap > 1.5:
            pauses.append({
                "after_word": word_timestamps[i - 1]["word"],
                "before_word": word_timestamps[i]["word"],
                "duration_sec": round(gap, 2),
                "at_time_sec": round(word_timestamps[i - 1]["end"], 2),
            })

    return {
        "transcript_text": " ".join(words),
        "total_words": total_words,
        "total_duration_sec": round(total_duration_sec, 2),
        "words_per_minute": round(wpm, 1),
        "filler_word_count": filler_count,
        "filler_word_ratio": round(filler_count / total_words, 4) if total_words > 0 else 0,
        "pauses_over_1_5_sec": pauses,
        "average_confidence": round(
            sum(w["confidence"] for w in word_timestamps) / len(word_timestamps), 4
        ) if word_timestamps else 0,
    }


def _generate_mock_transcript() -> dict:
    """Generate a realistic mock Transcribe output for local development."""
    # Simulates a ~2 minute presentation excerpt
    mock_words = (
        "Thank you so much for having me here today. I want to talk about "
        "something that I think is really important. The power of storytelling "
        "in technology. You know, when we think about great presentations, "
        "we often focus on the data, the charts, the technical details. "
        "But actually, the most memorable talks are the ones that tell a story. "
        "Think about the best TED talks you have ever seen. What do you remember? "
        "You remember the story. You remember how it made you feel. "
        "So today I want to share three principles that can transform "
        "your technical presentations into compelling stories. "
        "First, start with why. Not what you built, but why it matters. "
        "Second, use concrete examples. Abstract concepts are hard to grasp, "
        "but specific stories stick with people. "
        "And third, end with a call to action. Give your audience something "
        "to do with what they have learned. "
        "Let me illustrate with um a quick example. "
        "Last year I was presenting our new machine learning platform "
        "to a group of executives. I could have started with the architecture "
        "diagram and the performance benchmarks. Instead, I started with a story "
        "about a customer who was struggling to make sense of their data. "
        "I described their frustration, their failed attempts, and then "
        "how our platform helped them find the insight that saved their business. "
        "By the time I showed the technical details, the audience was already invested. "
        "They understood the why before the what. "
        "So remember, data informs but stories inspire. "
        "Thank you."
    )
    words_list = mock_words.split()
    items = []
    current_time = 0.5

    for word in words_list:
        duration = 0.3 + (len(word) * 0.05)
        # Add occasional pauses
        if word.endswith("."):
            gap = 1.0
        elif word.endswith(","):
            gap = 0.4
        else:
            gap = 0.15

        items.append({
            "type": "pronunciation",
            "alternatives": [{"content": word.strip(".,!?"), "confidence": "0.98"}],
            "start_time": str(round(current_time, 3)),
            "end_time": str(round(current_time + duration, 3)),
        })
        current_time += duration + gap

        # Add punctuation as separate items (matches Transcribe format)
        for punct in ".,!?":
            if word.endswith(punct):
                items.append({
                    "type": "punctuation",
                    "alternatives": [{"content": punct, "confidence": "0.99"}],
                })

    return {
        "results": {
            "transcripts": [{"transcript": mock_words}],
            "items": items,
        }
    }
