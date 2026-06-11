"""Audio feature extraction using librosa.

Extracts pitch (F0), energy (RMS), spectral clarity, and silence ratio
from audio files. These features supplement the transcript data from
AWS Transcribe to give a complete picture of vocal delivery.

In LOCAL_DEV mode, returns mock audio features without processing audio.
"""

import logging
import os
import tempfile

import boto3
import numpy as np

from app.config.settings import settings
from app.services.storage import get_local_upload_path

logger = logging.getLogger(__name__)


def extract_audio_features(audio_path: str) -> dict:
    """Extract acoustic features from an audio file using librosa.

    Args:
        audio_path: Local filesystem path to the audio file.

    Returns:
        Dictionary with pitch, energy, clarity, and silence analysis.
        Returns mock features if the audio format cannot be decoded.
    """
    if settings.local_dev:
        logger.info("LOCAL_DEV: Returning mock audio features for %s", audio_path)
        return _generate_mock_audio_features()

    import librosa

    # Load audio (librosa resamples to 22050 Hz by default)
    try:
        y, sr = librosa.load(audio_path, sr=22050)
    except Exception as e:
        logger.warning(
            "Cannot decode audio file %s (%s). Using default audio features. "
            "Analysis will rely on transcript data.",
            audio_path, e,
        )
        return _generate_mock_audio_features()
    duration = librosa.get_duration(y=y, sr=sr)

    pitch = _extract_pitch(y, sr)
    energy = _extract_energy(y)
    clarity = _extract_clarity(y, sr)
    silence_ratio = _extract_silence_ratio(y)

    return {
        "duration_sec": round(duration, 2),
        "sample_rate": sr,
        "pitch": pitch,
        "energy": energy,
        "clarity": clarity,
        "silence_ratio": round(silence_ratio, 4),
        "summary": {
            "is_monotone": pitch["std_hz"] < 15,
            "has_good_energy_variation": energy["std"] > 0.01,
            "silence_percentage": round(silence_ratio * 100, 1),
        },
    }


def extract_audio_features_from_s3(bucket: str, key: str) -> dict:
    """Download an audio file from S3 and extract features.

    Args:
        bucket: S3 bucket name.
        key: S3 object key.

    Returns:
        Dictionary with audio features.
    """
    if settings.local_dev:
        local_path = get_local_upload_path(key)
        return extract_audio_features(local_path)

    s3 = boto3.client("s3", region_name=settings.aws_region)
    ext = key.rsplit(".", 1)[-1] if "." in key else "webm"
    tmp_path = os.path.join(tempfile.gettempdir(), f"audio_input.{ext}")

    try:
        s3.download_file(bucket, key, tmp_path)
        return extract_audio_features(tmp_path)
    finally:
        if os.path.exists(tmp_path):
            os.remove(tmp_path)


def _extract_pitch(y: np.ndarray, sr: int) -> dict:
    """Extract pitch (fundamental frequency) statistics using PYIN."""
    import librosa

    f0, voiced_flag, _ = librosa.pyin(
        y, fmin=librosa.note_to_hz("C2"), fmax=librosa.note_to_hz("C7")
    )
    f0_valid = f0[~np.isnan(f0)]

    if len(f0_valid) == 0:
        return {
            "mean_hz": 0, "std_hz": 0, "min_hz": 0,
            "max_hz": 0, "range_hz": 0, "voiced_ratio": 0,
        }

    return {
        "mean_hz": round(float(np.mean(f0_valid)), 2),
        "std_hz": round(float(np.std(f0_valid)), 2),
        "min_hz": round(float(np.min(f0_valid)), 2),
        "max_hz": round(float(np.max(f0_valid)), 2),
        "range_hz": round(float(np.max(f0_valid) - np.min(f0_valid)), 2),
        "voiced_ratio": round(float(np.mean(voiced_flag)), 4),
    }


def _extract_energy(y: np.ndarray) -> dict:
    """Extract energy (RMS loudness) statistics."""
    import librosa

    rms = librosa.feature.rms(y=y)[0]

    rms_positive = rms[rms > 0]
    if len(rms_positive) == 0:
        return {"mean": 0, "std": 0, "max": 0, "dynamic_range_db": 0}

    dynamic_range_db = 20 * np.log10(
        np.max(rms) / (np.min(rms_positive) + 1e-10)
    )

    return {
        "mean": round(float(np.mean(rms)), 6),
        "std": round(float(np.std(rms)), 6),
        "max": round(float(np.max(rms)), 6),
        "dynamic_range_db": round(float(dynamic_range_db), 2),
    }


def _extract_clarity(y: np.ndarray, sr: int) -> dict:
    """Extract spectral centroid as a proxy for voice clarity/brightness."""
    import librosa

    spectral_centroid = librosa.feature.spectral_centroid(y=y, sr=sr)[0]

    return {
        "spectral_centroid_mean_hz": round(float(np.mean(spectral_centroid)), 2),
        "spectral_centroid_std_hz": round(float(np.std(spectral_centroid)), 2),
    }


def _extract_silence_ratio(y: np.ndarray) -> float:
    """Calculate the proportion of the audio that is silence."""
    import librosa

    rms = librosa.feature.rms(y=y)[0]
    if len(rms) == 0 or np.max(rms) == 0:
        return 1.0

    silence_threshold = 0.02 * np.max(rms)
    silence_frames = np.sum(rms < silence_threshold)
    return float(silence_frames / len(rms))


def _generate_mock_audio_features() -> dict:
    """Generate realistic mock audio features for local development."""
    return {
        "duration_sec": 128.5,
        "sample_rate": 22050,
        "pitch": {
            "mean_hz": 185.3,
            "std_hz": 32.7,
            "min_hz": 95.2,
            "max_hz": 310.8,
            "range_hz": 215.6,
            "voiced_ratio": 0.72,
        },
        "energy": {
            "mean": 0.045,
            "std": 0.018,
            "max": 0.12,
            "dynamic_range_db": 28.5,
        },
        "clarity": {
            "spectral_centroid_mean_hz": 1850.4,
            "spectral_centroid_std_hz": 620.3,
        },
        "silence_ratio": 0.18,
        "summary": {
            "is_monotone": False,
            "has_good_energy_variation": True,
            "silence_percentage": 18.0,
        },
    }
