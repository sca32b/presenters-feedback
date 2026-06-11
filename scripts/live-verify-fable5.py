"""Live verification for Claude Fable 5 through the backend Bedrock path.

This script makes real AWS Bedrock calls. It is intentionally separate from
the normal unit suite so local tests stay fast and offline.
"""

import asyncio
import json
import os
import statistics
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

os.environ["LOCAL_DEV"] = "false"
os.environ.setdefault("AWS_REGION", "us-east-1")
os.environ.setdefault("BEDROCK_MODEL_ID", "us.anthropic.claude-fable-5")

from app.services.bedrock import analyze_presentation  # noqa: E402


BASE_AUDIO = {
    "pitch": {"mean_hz": 180.0, "std_hz": 32.0, "range_hz": 160.0},
    "energy": {"mean": 0.045, "std": 0.018, "dynamic_range_db": 24.0},
    "clarity": {"spectral_centroid_mean_hz": 1850.0},
    "silence_ratio": 0.16,
    "summary": {
        "is_monotone": False,
        "has_good_energy_variation": True,
        "silence_percentage": 16.0,
    },
}


def transcript(text, words, duration, wpm, fillers, pauses=None, confidence=0.97):
    return {
        "transcript_text": text,
        "total_words": words,
        "total_duration_sec": duration,
        "words_per_minute": wpm,
        "filler_word_count": fillers,
        "filler_word_ratio": round(fillers / words, 4) if words else 0,
        "pauses_over_1_5_sec": pauses or [],
        "average_confidence": confidence,
    }


def audio(**overrides):
    value = deepcopy(BASE_AUDIO)
    for dotted_key, new_value in overrides.items():
        target = value
        parts = dotted_key.split("__")
        for part in parts[:-1]:
            target = target[part]
        target[parts[-1]] = new_value
    return value


CASES = [
    {
        "id": "executive_bluf",
        "description": "Clear executive recommendation with strategic pause.",
        "transcript": transcript(
            "We should standardize deployment pipelines this quarter. Today, each team ships differently, which creates audit gaps and slows incident response. My recommendation is one paved road with reusable templates, clear ownership, and automated security checks. This reduces delivery risk while helping teams move faster with confidence.",
            47,
            29.0,
            97.2,
            0,
            [{"after_word": "response", "before_word": "My", "duration_sec": 2.0, "at_time_sec": 14.1}],
        ),
        "audio": audio(),
    },
    {
        "id": "filler_heavy",
        "description": "High filler word ratio and hesitant phrasing.",
        "transcript": transcript(
            "So um I kind of want to talk about our cloud migration. Like, it is basically going okay, but you know there are some things that maybe we should probably improve. I think the team could maybe align more on standards and actually document the process better.",
            46,
            31.0,
            89.0,
            10,
            [],
            0.91,
        ),
        "audio": audio(pitch__std_hz=18.0, energy__dynamic_range_db=14.0),
    },
    {
        "id": "too_fast",
        "description": "Fast technical delivery with low pause usage.",
        "transcript": transcript(
            "The deployment architecture uses event driven promotion gates, immutable build artifacts, environment scoped approvals, automated rollback policies, and observability hooks across every service boundary, so the main decision today is whether we enforce the template across all teams immediately or phase it by platform maturity.",
            45,
            13.5,
            200.0,
            0,
            [],
        ),
        "audio": audio(silence_ratio=0.04, summary__silence_percentage=4.0),
    },
    {
        "id": "slow_measured",
        "description": "Slow delivery with strong pauses and simple language.",
        "transcript": transcript(
            "Our customers wait too long. They need faster answers. We can fix this by simplifying intake, routing urgent work first, and measuring response time every day. The change is small, but the benefit is immediate.",
            34,
            24.0,
            85.0,
            0,
            [
                {"after_word": "long", "before_word": "They", "duration_sec": 1.9, "at_time_sec": 5.2},
                {"after_word": "day", "before_word": "The", "duration_sec": 2.4, "at_time_sec": 17.8},
            ],
        ),
        "audio": audio(),
    },
    {
        "id": "monotone_low_energy",
        "description": "Good content but monotone, low energy metrics.",
        "transcript": transcript(
            "The quarterly platform review shows that reliability has improved, deployment frequency is stable, and developer satisfaction is slightly higher. The next focus area is reducing handoffs between application teams and infrastructure teams.",
            31,
            19.0,
            97.9,
            0,
            [],
        ),
        "audio": audio(
            pitch__std_hz=7.0,
            pitch__range_hz=32.0,
            energy__std=0.004,
            energy__dynamic_range_db=8.0,
            summary__is_monotone=True,
            summary__has_good_energy_variation=False,
        ),
    },
    {
        "id": "storytelling",
        "description": "Narrative style with audience-friendly language.",
        "transcript": transcript(
            "Three months ago, a product team missed a release window because nobody knew which approval was blocking them. That moment exposed a bigger problem. Our process was not visible. By creating one deployment dashboard and one escalation path, we turned confusion into clarity.",
            42,
            26.0,
            96.9,
            0,
            [{"after_word": "problem", "before_word": "Our", "duration_sec": 1.8, "at_time_sec": 13.4}],
        ),
        "audio": audio(pitch__std_hz=41.0, energy__dynamic_range_db=29.0),
    },
    {
        "id": "vague_jargon",
        "description": "Jargon-heavy wording with vague business impact.",
        "transcript": transcript(
            "We are leveraging synergies across cross functional enablement streams to optimize stakeholder alignment and unlock transformational outcomes. The initiative should create scalable value by operationalizing best practices across the ecosystem.",
            28,
            18.0,
            93.3,
            0,
            [],
        ),
        "audio": audio(),
    },
    {
        "id": "low_confidence_transcript",
        "description": "Lower transcription confidence and uneven pause profile.",
        "transcript": transcript(
            "I want to share the release plan. The first milestone is automation. The second milestone is training. The third milestone is adoption reporting. If we stay focused, we can complete the transition before the holiday freeze.",
            36,
            22.0,
            98.2,
            1,
            [{"after_word": "automation", "before_word": "The", "duration_sec": 3.2, "at_time_sec": 8.0}],
            0.78,
        ),
        "audio": audio(pitch__std_hz=24.0, energy__dynamic_range_db=18.0),
    },
]


def validate(case_id, result):
    required = [
        "voice_tone",
        "vocabulary",
        "pacing",
        "executive_presence",
        "overall_score",
        "overall_summary",
        "recommendations",
    ]
    missing = [key for key in required if key not in result]
    if missing:
        raise ValueError(f"{case_id}: missing keys {missing}")

    for path in [
        ("voice_tone", "score"),
        ("vocabulary", "score"),
        ("pacing", "score"),
        ("overall_score",),
    ]:
        value = result
        for part in path:
            value = value[part]
        if not isinstance(value, int) or not 0 <= value <= 100:
            raise ValueError(f"{case_id}: invalid score at {'.'.join(path)}: {value!r}")

    if len(result["recommendations"]) != 3:
        raise ValueError(f"{case_id}: expected 3 recommendations")
    if len(result["executive_presence"].get("tips", [])) != 4:
        raise ValueError(f"{case_id}: expected 4 executive presence tips")


async def main():
    summaries = []
    started_at = datetime.now(timezone.utc).isoformat()

    for index, case in enumerate(CASES, start=1):
        print(f"[{index}/{len(CASES)}] live Fable 5: {case['id']} - {case['description']}")
        result = await analyze_presentation(case["transcript"], case["audio"])
        validate(case["id"], result)
        summary = {
            "id": case["id"],
            "description": case["description"],
            "overall_score": result["overall_score"],
            "voice_score": result["voice_tone"]["score"],
            "vocabulary_score": result["vocabulary"]["score"],
            "pacing_score": result["pacing"]["score"],
            "filler_word_count": result["vocabulary"]["filler_word_count"],
            "wpm": result["pacing"]["words_per_minute"],
            "executive_tip_count": len(result["executive_presence"]["tips"]),
            "recommendation_count": len(result["recommendations"]),
            "overall_summary": result["overall_summary"],
            "first_recommendation": result["recommendations"][0],
        }
        summaries.append(summary)
        print(
            "  scores: overall={overall_score}, voice={voice_score}, "
            "vocab={vocabulary_score}, pacing={pacing_score}".format(**summary)
        )

    scores = [item["overall_score"] for item in summaries]
    report = {
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "model_id": os.environ["BEDROCK_MODEL_ID"],
        "case_count": len(summaries),
        "overall_score_min": min(scores),
        "overall_score_max": max(scores),
        "overall_score_mean": round(statistics.mean(scores), 2),
        "cases": summaries,
    }
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
