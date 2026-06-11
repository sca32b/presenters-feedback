"""
Unit tests for the Bedrock service (app.services.bedrock).

Tests cover:
- analyze_presentation() with both transcript and audio features
- LOCAL_DEV mode mock analysis results
- Converse API call structure (model ID, system prompt, temperature)
- Prompt template: includes transcript data, audio features, and TED benchmarks
- Response parsing: clean JSON, markdown-wrapped JSON, malformed responses
- Error handling for Bedrock API failures
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_transcript_features():
    """Transcript features as returned by extract_transcript_features()."""
    return {
        "transcript_text": "good morning everyone today i want to talk about presentations",
        "total_words": 9,
        "total_duration_sec": 6.0,
        "words_per_minute": 90.0,
        "filler_word_count": 0,
        "filler_word_ratio": 0.0,
        "pauses_over_1_5_sec": [],
        "average_confidence": 0.97,
    }


@pytest.fixture
def sample_audio_features():
    """Audio features as returned by extract_audio_features()."""
    return {
        "duration_sec": 6.0,
        "sample_rate": 22050,
        "pitch": {
            "mean_hz": 180.0,
            "std_hz": 30.0,
            "min_hz": 100.0,
            "max_hz": 280.0,
            "range_hz": 180.0,
            "voiced_ratio": 0.75,
        },
        "energy": {
            "mean": 0.04,
            "std": 0.015,
            "max": 0.1,
            "dynamic_range_db": 25.0,
        },
        "clarity": {
            "spectral_centroid_mean_hz": 1800.0,
            "spectral_centroid_std_hz": 500.0,
        },
        "silence_ratio": 0.15,
        "summary": {
            "is_monotone": False,
            "has_good_energy_variation": True,
            "silence_percentage": 15.0,
        },
    }


@pytest.fixture
def mock_converse_response(sample_analysis_results):
    """Mock response from Bedrock converse API."""
    return {
        "output": {
            "message": {
                "content": [{"text": json.dumps(sample_analysis_results)}]
            }
        },
        "ResponseMetadata": {"HTTPStatusCode": 200},
    }


@pytest.fixture
def mock_bedrock_converse_client(mock_converse_response):
    """Mocked boto3 Bedrock Runtime client using the Converse API."""
    client = MagicMock()
    client.converse.return_value = mock_converse_response
    return client


# ---------------------------------------------------------------------------
# LOCAL_DEV mode tests
# ---------------------------------------------------------------------------

class TestLocalDevMode:
    """Tests for LOCAL_DEV mock analysis."""

    @pytest.mark.asyncio
    async def test_returns_mock_analysis_structure(
        self, sample_transcript_features, sample_audio_features
    ):
        """In LOCAL_DEV, should return analysis matching the AnalysisResults schema."""
        from app.services.bedrock import analyze_presentation
        result = await analyze_presentation(sample_transcript_features, sample_audio_features)

        assert "voice_tone" in result
        assert "vocabulary" in result
        assert "pacing" in result
        assert "overall_score" in result
        assert "overall_summary" in result
        assert "recommendations" in result

    @pytest.mark.asyncio
    async def test_mock_scores_are_in_range(
        self, sample_transcript_features, sample_audio_features
    ):
        """Mock scores should be between 0 and 100."""
        from app.services.bedrock import analyze_presentation
        result = await analyze_presentation(sample_transcript_features, sample_audio_features)

        assert 0 <= result["voice_tone"]["score"] <= 100
        assert 0 <= result["vocabulary"]["score"] <= 100
        assert 0 <= result["pacing"]["score"] <= 100
        assert 0 <= result["overall_score"] <= 100

    @pytest.mark.asyncio
    async def test_mock_uses_actual_transcript_data(
        self, sample_transcript_features, sample_audio_features
    ):
        """Mock should use actual filler count and WPM from transcript."""
        sample_transcript_features["filler_word_count"] = 8
        sample_transcript_features["words_per_minute"] = 200.0
        from app.services.bedrock import analyze_presentation
        result = await analyze_presentation(sample_transcript_features, sample_audio_features)

        assert result["vocabulary"]["filler_word_count"] == 8
        assert result["pacing"]["words_per_minute"] == 200

    @pytest.mark.asyncio
    async def test_mock_has_three_recommendations(
        self, sample_transcript_features, sample_audio_features
    ):
        """Mock should return exactly 3 recommendations."""
        from app.services.bedrock import analyze_presentation
        result = await analyze_presentation(sample_transcript_features, sample_audio_features)
        assert isinstance(result["recommendations"], list)
        assert len(result["recommendations"]) == 3


# ---------------------------------------------------------------------------
# Converse API call structure tests (AWS mode)
# ---------------------------------------------------------------------------

class TestConverseApiCall:
    """Tests verifying the Bedrock Converse API is called correctly."""

    @pytest.mark.asyncio
    async def test_calls_converse_with_correct_model(
        self, mock_bedrock_converse_client, sample_transcript_features,
        sample_audio_features, monkeypatch
    ):
        """Should invoke the model configured in settings."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        import importlib, app.config.settings, app.services.bedrock
        importlib.reload(app.config.settings)
        importlib.reload(app.services.bedrock)

        with patch("app.services.bedrock.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_bedrock_converse_client

            await app.services.bedrock.analyze_presentation(
                sample_transcript_features, sample_audio_features
            )

        call_kwargs = mock_bedrock_converse_client.converse.call_args[1]
        assert call_kwargs["modelId"] == "us.anthropic.claude-fable-5"

    @pytest.mark.asyncio
    async def test_omits_deprecated_temperature(
        self, mock_bedrock_converse_client, sample_transcript_features,
        sample_audio_features, monkeypatch
    ):
        """Fable 5 rejects temperature, so the request must omit it."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        import importlib, app.config.settings, app.services.bedrock
        importlib.reload(app.config.settings)
        importlib.reload(app.services.bedrock)

        with patch("app.services.bedrock.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_bedrock_converse_client

            await app.services.bedrock.analyze_presentation(
                sample_transcript_features, sample_audio_features
            )

        call_kwargs = mock_bedrock_converse_client.converse.call_args[1]
        assert "temperature" not in call_kwargs.get("inferenceConfig", {})
        assert call_kwargs["inferenceConfig"]["maxTokens"] == 2048

    @pytest.mark.asyncio
    async def test_includes_system_prompt(
        self, mock_bedrock_converse_client, sample_transcript_features,
        sample_audio_features, monkeypatch
    ):
        """Should include a system prompt about being a presentation coach."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        import importlib, app.config.settings, app.services.bedrock
        importlib.reload(app.config.settings)
        importlib.reload(app.services.bedrock)

        with patch("app.services.bedrock.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_bedrock_converse_client

            await app.services.bedrock.analyze_presentation(
                sample_transcript_features, sample_audio_features
            )

        call_kwargs = mock_bedrock_converse_client.converse.call_args[1]
        system_text = call_kwargs["system"][0]["text"]
        assert "presentation coach" in system_text.lower()
        assert "JSON" in system_text


# ---------------------------------------------------------------------------
# Prompt content tests
# ---------------------------------------------------------------------------

class TestPromptContent:
    """Tests for the ANALYSIS_PROMPT template and its contents."""

    def test_prompt_template_exists(self):
        """The ANALYSIS_PROMPT constant should be defined and non-trivial."""
        from app.services.bedrock import ANALYSIS_PROMPT
        assert isinstance(ANALYSIS_PROMPT, str)
        assert len(ANALYSIS_PROMPT) > 200

    def test_prompt_has_transcript_placeholders(self):
        """Prompt should have placeholders for all transcript features."""
        from app.services.bedrock import ANALYSIS_PROMPT
        assert "{transcript_text}" in ANALYSIS_PROMPT
        assert "{total_words}" in ANALYSIS_PROMPT
        assert "{words_per_minute}" in ANALYSIS_PROMPT
        assert "{filler_word_count}" in ANALYSIS_PROMPT
        assert "{filler_word_ratio}" in ANALYSIS_PROMPT

    def test_prompt_has_audio_feature_placeholders(self):
        """Prompt should have placeholders for audio features."""
        from app.services.bedrock import ANALYSIS_PROMPT
        assert "{pitch_mean_hz}" in ANALYSIS_PROMPT
        assert "{pitch_std_hz}" in ANALYSIS_PROMPT
        assert "{pitch_range_hz}" in ANALYSIS_PROMPT
        assert "{is_monotone}" in ANALYSIS_PROMPT
        assert "{energy_mean}" in ANALYSIS_PROMPT
        assert "{energy_dynamic_range_db}" in ANALYSIS_PROMPT
        assert "{silence_ratio}" in ANALYSIS_PROMPT

    def test_prompt_includes_ted_benchmarks(self):
        """Prompt should reference TED talk benchmarks."""
        from app.services.bedrock import ANALYSIS_PROMPT
        assert "TED" in ANALYSIS_PROMPT
        assert "130-170 WPM" in ANALYSIS_PROMPT or "150 WPM" in ANALYSIS_PROMPT

    def test_prompt_requests_json_output(self):
        """Prompt should instruct the model to respond with only JSON."""
        from app.services.bedrock import ANALYSIS_PROMPT
        assert "JSON" in ANALYSIS_PROMPT

    def test_prompt_includes_scoring_schema(self):
        """Prompt should define the expected JSON structure with scoring."""
        from app.services.bedrock import ANALYSIS_PROMPT
        assert "voice_tone" in ANALYSIS_PROMPT
        assert "vocabulary" in ANALYSIS_PROMPT
        assert "pacing" in ANALYSIS_PROMPT
        assert "overall_score" in ANALYSIS_PROMPT
        assert "recommendations" in ANALYSIS_PROMPT

    @pytest.mark.asyncio
    async def test_prompt_populated_with_features(
        self, mock_bedrock_converse_client, sample_transcript_features,
        sample_audio_features, monkeypatch
    ):
        """The formatted prompt should contain actual feature values."""
        monkeypatch.setenv("LOCAL_DEV", "false")

        import importlib, app.config.settings, app.services.bedrock
        importlib.reload(app.config.settings)
        importlib.reload(app.services.bedrock)

        with patch("app.services.bedrock.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_bedrock_converse_client

            await app.services.bedrock.analyze_presentation(
                sample_transcript_features, sample_audio_features
            )

        call_kwargs = mock_bedrock_converse_client.converse.call_args[1]
        prompt_text = call_kwargs["messages"][0]["content"][0]["text"]

        # Transcript values
        assert "good morning everyone" in prompt_text
        assert "90.0" in prompt_text  # WPM
        assert "9" in prompt_text  # total_words

        # Audio feature values
        assert "180.0" in prompt_text  # pitch mean
        assert "30.0" in prompt_text  # pitch std
        assert "25.0" in prompt_text  # dynamic range


# ---------------------------------------------------------------------------
# Response parsing tests
# ---------------------------------------------------------------------------

class TestParseJsonResponse:
    """Tests for _parse_json_response()."""

    def test_parses_clean_json(self, sample_analysis_results):
        """Should parse a clean JSON string."""
        from app.services.bedrock import _parse_json_response
        raw = json.dumps(sample_analysis_results)
        result = _parse_json_response(raw)
        assert result["overall_score"] == 64

    def test_parses_markdown_wrapped_json(self, sample_analysis_results):
        """Should parse JSON wrapped in markdown code blocks."""
        from app.services.bedrock import _parse_json_response
        raw = "Here is the analysis:\n```json\n" + json.dumps(sample_analysis_results) + "\n```\n"
        result = _parse_json_response(raw)
        assert result["overall_score"] == 64

    def test_parses_json_without_lang_tag(self, sample_analysis_results):
        """Should parse JSON in code blocks without the 'json' language tag."""
        from app.services.bedrock import _parse_json_response
        raw = "```\n" + json.dumps(sample_analysis_results) + "\n```"
        result = _parse_json_response(raw)
        assert result["overall_score"] == 64

    def test_extracts_json_from_surrounding_text(self):
        """Should extract JSON object from surrounding text."""
        from app.services.bedrock import _parse_json_response
        raw = 'Here is the result: {"overall_score": 75} hope this helps!'
        result = _parse_json_response(raw)
        assert result["overall_score"] == 75

    def test_raises_on_completely_invalid_text(self):
        """Should raise ValueError when no JSON can be found."""
        from app.services.bedrock import _parse_json_response
        with pytest.raises((json.JSONDecodeError, ValueError)):
            _parse_json_response("This is just plain text with no JSON at all.")


# ---------------------------------------------------------------------------
# Error handling tests
# ---------------------------------------------------------------------------

class TestErrorHandling:
    """Tests for Bedrock API error handling."""

    @pytest.mark.asyncio
    async def test_throttling_error_propagates(
        self, sample_transcript_features, sample_audio_features, monkeypatch
    ):
        """Should propagate Bedrock throttling errors."""
        monkeypatch.setenv("LOCAL_DEV", "false")
        mock_client = MagicMock()
        mock_client.converse.side_effect = ClientError(
            {"Error": {"Code": "ThrottlingException", "Message": "Rate exceeded"}},
            "Converse"
        )

        import importlib, app.config.settings, app.services.bedrock
        importlib.reload(app.config.settings)
        importlib.reload(app.services.bedrock)

        with patch("app.services.bedrock.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_client

            with pytest.raises(ClientError):
                await app.services.bedrock.analyze_presentation(
                    sample_transcript_features, sample_audio_features
                )

    @pytest.mark.asyncio
    async def test_service_unavailable_error(
        self, sample_transcript_features, sample_audio_features, monkeypatch
    ):
        """Should propagate service unavailable errors."""
        monkeypatch.setenv("LOCAL_DEV", "false")
        mock_client = MagicMock()
        mock_client.converse.side_effect = ClientError(
            {"Error": {"Code": "ServiceUnavailableException", "Message": "Down"}},
            "Converse"
        )

        import importlib, app.config.settings, app.services.bedrock
        importlib.reload(app.config.settings)
        importlib.reload(app.services.bedrock)

        with patch("app.services.bedrock.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_client

            with pytest.raises(ClientError):
                await app.services.bedrock.analyze_presentation(
                    sample_transcript_features, sample_audio_features
                )
