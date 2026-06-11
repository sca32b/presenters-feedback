"""Amazon Bedrock (Claude) integration for speech analysis.

In LOCAL_DEV mode, returns mock analysis results without calling AWS.
Uses the InvokeModel API for direct Claude invocation.
"""

import json
import logging
import random
import re

import boto3

from app.config.settings import settings

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are an expert presentation coach who has trained hundreds of "
    "TED speakers. You analyze presentations with precision and provide "
    "actionable, specific feedback. You always respond in valid JSON format."
)

ANALYSIS_PROMPT = """Analyze this presentation and provide detailed scoring and feedback.

## Transcript Data
- **Full transcript**: {transcript_text}
- **Total words**: {total_words}
- **Duration**: {total_duration_sec} seconds
- **Words per minute**: {words_per_minute}
- **Filler word count**: {filler_word_count} (ratio: {filler_word_ratio})
- **Pauses over 1.5s**: {pauses}
- **Transcription confidence**: {average_confidence}

## Audio Features (extracted from audio signal)
- **Pitch**: mean={pitch_mean_hz}Hz, std={pitch_std_hz}Hz, range={pitch_range_hz}Hz
- **Is monotone**: {is_monotone}
- **Energy**: mean={energy_mean}, std={energy_std}, dynamic_range={energy_dynamic_range_db}dB
- **Has good energy variation**: {has_good_energy_variation}
- **Voice clarity (spectral centroid)**: mean={spectral_centroid_mean_hz}Hz
- **Silence ratio**: {silence_ratio} ({silence_percentage}%)

## TED Talk Benchmarks for Reference
- Ideal speaking rate: 130-170 WPM (TED average is ~150 WPM)
- Filler word ratio: <2% is excellent, 2-5% is acceptable, >5% needs work
- Pitch variation (std): >25Hz indicates good expressiveness
- Pause usage: Strategic pauses of 1-3 seconds are effective; >5 seconds is too long
- Dynamic range: >20dB indicates good vocal emphasis variation

## Executive Presence Coaching
Also evaluate the speaker's executive presence -- the ability to project confidence, authority, and credibility. Consider these dimensions:
- **Decisive language**: Does the speaker use authoritative, direct language rather than tentative or weak phrasing?
- **Vocal confidence**: Does the speaker project confidence through vocal delivery -- pace, pauses, and tone?
- **Executive brevity**: Does the speaker structure messages with a bottom-line-up-front (BLUF) approach rather than burying key points?
- **Power language**: Does the speaker avoid hedging words like "I think", "maybe", "sort of", "kind of", "just", "actually"?
- **Strategic silence**: Does the speaker use silence deliberately to command attention and emphasize key points?
- **Conviction and specificity**: Does the speaker communicate with conviction and specificity rather than vagueness?

Provide four specific, actionable tips for improving executive presence based on what you observe in the transcript and delivery metrics.

## Instructions
Provide your analysis as a JSON object with this exact structure:
{{
  "voice_tone": {{
    "score": <0-100>,
    "confidence_level": "<low|moderate|high>",
    "warmth": "<low|moderate|high>",
    "monotone_detected": <true|false>,
    "summary": "<2-3 sentence assessment>"
  }},
  "vocabulary": {{
    "score": <0-100>,
    "filler_word_count": <integer>,
    "unique_word_ratio": <0.0-1.0>,
    "readability_level": "<academic|professional|conversational|simple>",
    "summary": "<2-3 sentence assessment>"
  }},
  "pacing": {{
    "score": <0-100>,
    "words_per_minute": <integer>,
    "variation": "<low|moderate|high>",
    "pause_usage": "<insufficient|adequate|excellent>",
    "summary": "<2-3 sentence assessment>"
  }},
  "executive_presence": {{
    "tips": [
        "<specific tip for appearing effective and executive 1>",
        "<specific tip for appearing effective and executive 2>",
        "<specific tip for appearing effective and executive 3>",
        "<specific tip for appearing effective and executive 4>"
    ]
  }},
  "overall_score": <0-100>,
  "overall_summary": "<3-4 sentence overall assessment, referencing TED-level delivery standards>",
  "recommendations": [
    "<actionable recommendation 1>",
    "<actionable recommendation 2>",
    "<actionable recommendation 3>"
  ]
}}

Respond with ONLY the JSON object, no additional text."""


async def analyze_presentation(
    transcript_features: dict, audio_features: dict
) -> dict:
    """Send transcript and audio features to Bedrock Claude for analysis."""
    if settings.local_dev:
        logger.info("LOCAL_DEV: Returning mock analysis results")
        return _generate_mock_analysis(transcript_features)

    client = boto3.client("bedrock-runtime", region_name=settings.aws_region)

    prompt = ANALYSIS_PROMPT.format(
        transcript_text=transcript_features["transcript_text"],
        total_words=transcript_features["total_words"],
        total_duration_sec=transcript_features["total_duration_sec"],
        words_per_minute=transcript_features["words_per_minute"],
        filler_word_count=transcript_features["filler_word_count"],
        filler_word_ratio=transcript_features["filler_word_ratio"],
        pauses=json.dumps(transcript_features["pauses_over_1_5_sec"]),
        average_confidence=transcript_features["average_confidence"],
        pitch_mean_hz=audio_features["pitch"]["mean_hz"],
        pitch_std_hz=audio_features["pitch"]["std_hz"],
        pitch_range_hz=audio_features["pitch"]["range_hz"],
        is_monotone=audio_features["summary"]["is_monotone"],
        energy_mean=audio_features["energy"]["mean"],
        energy_std=audio_features["energy"]["std"],
        energy_dynamic_range_db=audio_features["energy"]["dynamic_range_db"],
        has_good_energy_variation=audio_features["summary"]["has_good_energy_variation"],
        spectral_centroid_mean_hz=audio_features["clarity"]["spectral_centroid_mean_hz"],
        silence_ratio=audio_features["silence_ratio"],
        silence_percentage=audio_features["summary"]["silence_percentage"],
    )

    model_id = settings.bedrock_model_id
    logger.info("Calling Bedrock invoke_model with model_id=%s", model_id)

    try:
        body = json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens": 2048,
            "temperature": 0.3,
            "system": SYSTEM_PROMPT,
            "messages": [
                {"role": "user", "content": prompt}
            ],
        })

        response = client.invoke_model(
            modelId=model_id,
            contentType="application/json",
            accept="application/json",
            body=body,
        )

        response_body = json.loads(response["body"].read())
        result_text = response_body["content"][0]["text"]
        logger.info("Bedrock response received, length=%d", len(result_text))
        return _parse_json_response(result_text)

    except Exception as e:
        logger.error("Bedrock API call failed: %s: %s", type(e).__name__, str(e))
        raise


def _parse_json_response(text: str) -> dict:
    """Parse JSON from Claude's response, handling markdown code blocks."""
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Claude sometimes wraps JSON in markdown code blocks
        json_match = re.search(r"```json?\s*(.*?)\s*```", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(1))
        # Try to find any JSON object in the text
        json_match = re.search(r"\{.*\}", text, re.DOTALL)
        if json_match:
            return json.loads(json_match.group(0))
        raise ValueError(f"Could not parse JSON from response: {text[:200]}")


def _generate_mock_analysis(transcript_features: dict) -> dict:
    """Generate realistic mock analysis results for local development."""
    wpm = transcript_features.get("words_per_minute", 150)
    filler_count = transcript_features.get("filler_word_count", 3)
    total_words = transcript_features.get("total_words", 200)

    # Calculate unique word ratio from actual transcript
    words = transcript_features.get("transcript_text", "").lower().split()
    unique_ratio = round(len(set(words)) / len(words), 2) if words else 0.65

    # Score pacing based on how close WPM is to ideal (150)
    pace_score = max(30, 100 - abs(wpm - 150) * 2)

    return {
        "voice_tone": {
            "score": random.randint(60, 88),
            "confidence_level": "moderate",
            "warmth": "high",
            "monotone_detected": False,
            "summary": (
                "Your voice conveys warmth and genuine enthusiasm for the topic. "
                "The tonal variation is good, especially when transitioning between "
                "key points. Consider adding more deliberate pauses after important "
                "statements to let them resonate with the audience."
            ),
        },
        "vocabulary": {
            "score": random.randint(55, 85),
            "filler_word_count": filler_count,
            "unique_word_ratio": unique_ratio,
            "readability_level": "conversational",
            "summary": (
                f"You use a diverse range of words (unique word ratio: {unique_ratio:.0%}) "
                f"that are accessible without being oversimplified. "
                f"{'Minimal filler words detected - good discipline.' if filler_count < 5 else f'Detected {filler_count} filler words - try replacing these with brief pauses.'} "
                "Technical terms are introduced with clear context."
            ),
        },
        "pacing": {
            "score": min(100, max(30, int(pace_score))),
            "words_per_minute": int(wpm),
            "variation": "moderate",
            "pause_usage": "adequate" if len(transcript_features.get("pauses_over_1_5_sec", [])) >= 2 else "insufficient",
            "summary": (
                f"Your speaking rate of {int(wpm)} WPM is "
                f"{'within the ideal range (130-170 WPM) for presentations' if 130 <= wpm <= 170 else 'outside the ideal range of 130-170 WPM'}. "
                "The rhythm feels natural and conversational. "
                "Consider varying your pace more - slow down for key insights and "
                "speed up slightly for supporting details."
            ),
        },
        "overall_score": random.randint(55, 82),
        "overall_summary": (
            "Your presentation demonstrates solid structure and engaging delivery. "
            "The use of storytelling techniques is effective, and your vocabulary is "
            "well-suited for the audience. To reach TED-level delivery, focus on "
            "strategic pausing, reducing filler words, and varying your vocal dynamics "
            "to create more emotional impact during key moments."
        ),
        "executive_presence": {
            "tips": [
                "Lead with your conclusion before providing supporting details - use a bottom-line-up-front structure to sound more decisive.",
                "Replace hedging phrases like 'I think' and 'maybe' with direct statements - say 'We should' instead of 'I think we could maybe'.",
                "Insert a deliberate 2-second pause before your most critical points to command attention and signal importance.",
                "Use specific numbers and concrete examples instead of vague qualifiers like 'a lot' or 'pretty good' to project authority.",
            ],
        },
        "recommendations": [
            "Add 2-3 second pauses after your most important statements to let them resonate with the audience.",
            "Replace filler words with deliberate pauses - brief silence is more powerful than 'um' or 'like'.",
            "Vary your speaking pace more deliberately: slow down for key insights, speed up for supporting details.",
        ],
    }
