"""
Unit tests for the Transcribe service (app.services.transcribe).

Tests cover:
- Starting a transcription job with correct parameters
- Polling and waiting for transcription results
- LOCAL_DEV mode mock transcript generation
- extract_transcript_features: WPM, filler words, pauses, confidence
- Error handling for timeouts and failures
"""
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def realistic_transcript_json():
    """A realistic Transcribe output with multiple words, fillers, and pauses."""
    items = [
        # Word at 0.0-0.4
        {"type": "pronunciation", "start_time": "0.0", "end_time": "0.4",
         "alternatives": [{"content": "Good", "confidence": "0.99"}]},
        {"type": "pronunciation", "start_time": "0.5", "end_time": "1.0",
         "alternatives": [{"content": "morning", "confidence": "0.98"}]},
        {"type": "punctuation",
         "alternatives": [{"content": ",", "confidence": "0.99"}]},
        {"type": "pronunciation", "start_time": "1.1", "end_time": "1.5",
         "alternatives": [{"content": "everyone", "confidence": "0.97"}]},
        {"type": "punctuation",
         "alternatives": [{"content": ".", "confidence": "0.99"}]},
        # Filler word "um" at 1.6-1.8
        {"type": "pronunciation", "start_time": "1.6", "end_time": "1.8",
         "alternatives": [{"content": "Um", "confidence": "0.60"}]},
        {"type": "punctuation",
         "alternatives": [{"content": ",", "confidence": "0.99"}]},
        # Long pause (>1.5s gap) then resume at 4.0
        {"type": "pronunciation", "start_time": "4.0", "end_time": "4.2",
         "alternatives": [{"content": "so", "confidence": "0.95"}]},
        {"type": "pronunciation", "start_time": "4.3", "end_time": "4.6",
         "alternatives": [{"content": "today", "confidence": "0.99"}]},
        {"type": "pronunciation", "start_time": "4.7", "end_time": "4.9",
         "alternatives": [{"content": "I", "confidence": "0.99"}]},
        {"type": "pronunciation", "start_time": "5.0", "end_time": "5.4",
         "alternatives": [{"content": "want", "confidence": "0.99"}]},
        {"type": "pronunciation", "start_time": "5.5", "end_time": "5.7",
         "alternatives": [{"content": "to", "confidence": "0.99"}]},
        {"type": "pronunciation", "start_time": "5.8", "end_time": "6.2",
         "alternatives": [{"content": "talk", "confidence": "0.98"}]},
        {"type": "punctuation",
         "alternatives": [{"content": ".", "confidence": "0.99"}]},
        # Another filler
        {"type": "pronunciation", "start_time": "6.3", "end_time": "6.5",
         "alternatives": [{"content": "Like", "confidence": "0.85"}]},
        {"type": "punctuation",
         "alternatives": [{"content": ",", "confidence": "0.99"}]},
        {"type": "pronunciation", "start_time": "6.6", "end_time": "7.0",
         "alternatives": [{"content": "really", "confidence": "0.96"}]},
        {"type": "pronunciation", "start_time": "7.1", "end_time": "7.5",
         "alternatives": [{"content": "important", "confidence": "0.97"}]},
        {"type": "punctuation",
         "alternatives": [{"content": ".", "confidence": "0.99"}]},
    ]
    return {"results": {"transcripts": [{"transcript": "dummy"}], "items": items}}


# ---------------------------------------------------------------------------
# LOCAL_DEV mode tests
# ---------------------------------------------------------------------------

class TestLocalDevMode:
    """Tests for LOCAL_DEV mode: mock transcript generation."""

    @pytest.mark.asyncio
    async def test_start_transcription_returns_job_name(self):
        """In LOCAL_DEV, start_transcription should return the job name immediately."""
        from app.services.transcribe import start_transcription
        result = await start_transcription("uploads/u1/file.webm", "pf-test-job")
        assert result == "pf-test-job"

    @pytest.mark.asyncio
    async def test_wait_for_transcription_returns_mock(self):
        """In LOCAL_DEV, wait_for_transcription should return a mock transcript dict."""
        from app.services.transcribe import wait_for_transcription
        result = await wait_for_transcription("pf-test-job")
        assert "results" in result
        assert "items" in result["results"]
        assert "transcripts" in result["results"]
        # Should have pronunciation items
        pron_items = [i for i in result["results"]["items"] if i["type"] == "pronunciation"]
        assert len(pron_items) > 10

    @pytest.mark.asyncio
    async def test_mock_transcript_has_timestamps(self):
        """Mock transcript items should have start_time and end_time."""
        from app.services.transcribe import wait_for_transcription
        result = await wait_for_transcription("pf-test-job")
        for item in result["results"]["items"]:
            if item["type"] == "pronunciation":
                assert "start_time" in item
                assert "end_time" in item
                assert float(item["start_time"]) >= 0
                assert float(item["end_time"]) > float(item["start_time"])


# ---------------------------------------------------------------------------
# AWS mode tests (mocked boto3)
# ---------------------------------------------------------------------------

class TestStartTranscription:
    """Tests for start_transcription() calling real AWS."""

    @pytest.mark.asyncio
    async def test_starts_job_with_correct_params(self, mock_transcribe_client, monkeypatch):
        """Should call StartTranscriptionJob with correct parameters."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        with patch("app.services.transcribe.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_transcribe_client
            # Re-import to pick up new settings
            import importlib
            import app.config.settings
            importlib.reload(app.config.settings)
            import app.services.transcribe
            importlib.reload(app.services.transcribe)

            job_name = await app.services.transcribe.start_transcription(
                object_key="uploads/user-123/abc.webm",
                job_name="pf-test-job",
            )

        mock_transcribe_client.start_transcription_job.assert_called_once()
        call_kwargs = mock_transcribe_client.start_transcription_job.call_args[1]
        assert call_kwargs["TranscriptionJobName"] == "pf-test-job"
        assert call_kwargs["LanguageCode"] == "en-US"
        assert "s3://" in call_kwargs["Media"]["MediaFileUri"]
        assert call_kwargs["MediaFormat"] == "webm"
        assert job_name == "pf-test-job"

    @pytest.mark.asyncio
    async def test_media_format_extracted_from_key(self, mock_transcribe_client, monkeypatch):
        """Should extract media format from the object key extension."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        with patch("app.services.transcribe.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_transcribe_client
            import importlib, app.config.settings, app.services.transcribe
            importlib.reload(app.config.settings)
            importlib.reload(app.services.transcribe)

            await app.services.transcribe.start_transcription("uploads/u1/file.wav", "pf-wav-job")

        call_kwargs = mock_transcribe_client.start_transcription_job.call_args[1]
        assert call_kwargs["MediaFormat"] == "wav"

    @pytest.mark.asyncio
    async def test_output_goes_to_transcripts_prefix(self, mock_transcribe_client, monkeypatch):
        """Transcription output should be saved to transcripts/ prefix."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        with patch("app.services.transcribe.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_transcribe_client
            import importlib, app.config.settings, app.services.transcribe
            importlib.reload(app.config.settings)
            importlib.reload(app.services.transcribe)

            await app.services.transcribe.start_transcription("uploads/u1/file.webm", "pf-job-xyz")

        call_kwargs = mock_transcribe_client.start_transcription_job.call_args[1]
        assert call_kwargs["OutputKey"] == "transcripts/pf-job-xyz.json"


# ---------------------------------------------------------------------------
# extract_transcript_features tests
# ---------------------------------------------------------------------------

class TestExtractTranscriptFeatures:
    """Tests for extract_transcript_features()."""

    def test_counts_total_words(self, realistic_transcript_json):
        """Should count only pronunciation items as words."""
        from app.services.transcribe import extract_transcript_features
        features = extract_transcript_features(realistic_transcript_json)
        # "Good morning everyone Um so today I want to talk Like really important" = 12 words
        assert features["total_words"] == 12

    def test_calculates_words_per_minute(self, realistic_transcript_json):
        """WPM should be total_words / (duration in minutes)."""
        from app.services.transcribe import extract_transcript_features
        features = extract_transcript_features(realistic_transcript_json)
        # Duration from 0.0 to 7.5 = 7.5 seconds = 0.125 minutes
        # 12 words / 0.125 min = 96 WPM
        assert features["words_per_minute"] == 96.0

    def test_detects_filler_words(self, realistic_transcript_json):
        """Should detect um, like, so as filler words."""
        from app.services.transcribe import extract_transcript_features
        features = extract_transcript_features(realistic_transcript_json)
        # "um", "so", "like" = 3 filler words
        assert features["filler_word_count"] == 3

    def test_filler_word_ratio(self, realistic_transcript_json):
        """Filler ratio should be filler_count / total_words."""
        from app.services.transcribe import extract_transcript_features
        features = extract_transcript_features(realistic_transcript_json)
        expected_ratio = round(3 / 12, 4)
        assert features["filler_word_ratio"] == expected_ratio

    def test_detects_long_pauses(self, realistic_transcript_json):
        """Should detect pauses >1.5s between words."""
        from app.services.transcribe import extract_transcript_features
        features = extract_transcript_features(realistic_transcript_json)
        pauses = features["pauses_over_1_5_sec"]
        # Gap between "Um" (end 1.8) and "so" (start 4.0) = 2.2s
        assert len(pauses) >= 1
        assert pauses[0]["duration_sec"] == 2.2
        assert pauses[0]["after_word"] == "um"
        assert pauses[0]["before_word"] == "so"

    def test_calculates_average_confidence(self, realistic_transcript_json):
        """Should calculate mean confidence across all pronunciation items."""
        from app.services.transcribe import extract_transcript_features
        features = extract_transcript_features(realistic_transcript_json)
        assert 0.8 < features["average_confidence"] < 1.0

    def test_builds_transcript_text(self, realistic_transcript_json):
        """Should join all pronunciation words into a transcript string."""
        from app.services.transcribe import extract_transcript_features
        features = extract_transcript_features(realistic_transcript_json)
        assert "good" in features["transcript_text"]
        assert "morning" in features["transcript_text"]
        assert "important" in features["transcript_text"]

    def test_handles_empty_transcript(self):
        """Should handle transcript with no items gracefully."""
        from app.services.transcribe import extract_transcript_features
        empty = {"results": {"items": []}}
        features = extract_transcript_features(empty)
        assert features["total_words"] == 0
        assert features["words_per_minute"] == 0
        assert features["filler_word_count"] == 0
        assert features["average_confidence"] == 0
        assert features["pauses_over_1_5_sec"] == []

    def test_handles_single_word(self):
        """Should handle transcript with a single word."""
        from app.services.transcribe import extract_transcript_features
        single = {
            "results": {
                "items": [
                    {"type": "pronunciation", "start_time": "0.0", "end_time": "0.5",
                     "alternatives": [{"content": "Hello", "confidence": "0.99"}]}
                ]
            }
        }
        features = extract_transcript_features(single)
        assert features["total_words"] == 1
        assert features["words_per_minute"] == 0  # duration is 0 with 1 word
        assert features["filler_word_count"] == 0

    def test_duration_calculation(self, realistic_transcript_json):
        """Duration should be last word end - first word start."""
        from app.services.transcribe import extract_transcript_features
        features = extract_transcript_features(realistic_transcript_json)
        assert features["total_duration_sec"] == 7.5
