"""
Unit tests for the analysis pipeline (app.api.analyses._run_analysis_pipeline).

Tests cover:
- Full LOCAL_DEV pipeline: create record -> mock transcribe -> mock audio -> mock bedrock -> store
- Pipeline creates initial DB record with 'processing' status
- Pipeline runs transcription and audio extraction concurrently
- Pipeline stores completed results with analysis scores
- Pipeline handles transcription failure gracefully
- Pipeline handles Bedrock failure gracefully
- Pipeline returns valid analysis_id
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_audio_features():
    """Mock audio features matching extract_audio_features_from_s3 output."""
    return {
        "duration_sec": 128.5,
        "sample_rate": 22050,
        "pitch": {
            "mean_hz": 185.3, "std_hz": 32.7, "min_hz": 95.2,
            "max_hz": 310.8, "range_hz": 215.6, "voiced_ratio": 0.72,
        },
        "energy": {"mean": 0.045, "std": 0.018, "max": 0.12, "dynamic_range_db": 28.5},
        "clarity": {"spectral_centroid_mean_hz": 1850.4, "spectral_centroid_std_hz": 620.3},
        "silence_ratio": 0.18,
        "summary": {
            "is_monotone": False, "has_good_energy_variation": True,
            "silence_percentage": 18.0,
        },
    }


# ---------------------------------------------------------------------------
# LOCAL_DEV pipeline tests (all services return mocks)
# ---------------------------------------------------------------------------

class TestLocalDevPipeline:
    """Tests for the full pipeline in LOCAL_DEV mode using mock data."""

    @pytest.mark.asyncio
    async def test_full_pipeline_completes(self):
        """Full LOCAL_DEV pipeline should run without errors."""
        from app.api.analyses import _run_analysis_pipeline
        from app.models.database import _local_store

        _local_store.clear()
        # Create initial record as the endpoint would
        from app.models.database import create_analysis
        create_analysis("test-id-1", "local-dev-user", "uploads/u1/file.webm")

        await _run_analysis_pipeline("test-id-1", "local-dev-user", "uploads/u1/file.webm")

        assert "test-id-1" in _local_store
        assert _local_store["test-id-1"]["status"] == "completed"
        assert _local_store["test-id-1"]["results"] is not None

    @pytest.mark.asyncio
    async def test_pipeline_stores_analysis_results(self):
        """Pipeline should store results with the expected schema keys."""
        from app.api.analyses import _run_analysis_pipeline
        from app.models.database import _local_store, create_analysis

        _local_store.clear()
        create_analysis("test-id-2", "local-dev-user", "uploads/u1/file.webm")

        await _run_analysis_pipeline("test-id-2", "local-dev-user", "uploads/u1/file.webm")

        results = _local_store["test-id-2"]["results"]
        assert "voice_tone" in results
        assert "vocabulary" in results
        assert "pacing" in results
        assert "overall_score" in results
        assert "overall_summary" in results
        assert "recommendations" in results

    @pytest.mark.asyncio
    async def test_pipeline_results_have_valid_scores(self):
        """All scores in the result should be between 0 and 100."""
        from app.api.analyses import _run_analysis_pipeline
        from app.models.database import _local_store, create_analysis

        _local_store.clear()
        create_analysis("test-id-3", "local-dev-user", "uploads/u1/file.webm")

        await _run_analysis_pipeline("test-id-3", "local-dev-user", "uploads/u1/file.webm")

        results = _local_store["test-id-3"]["results"]
        assert 0 <= results["voice_tone"]["score"] <= 100
        assert 0 <= results["vocabulary"]["score"] <= 100
        assert 0 <= results["pacing"]["score"] <= 100
        assert 0 <= results["overall_score"] <= 100


# ---------------------------------------------------------------------------
# API endpoint integration tests (using FastAPI TestClient)
# ---------------------------------------------------------------------------

class TestAnalysisEndpoints:
    """Tests for the analysis API endpoints."""

    def test_create_analysis_returns_202(self, client, sample_analysis_request):
        """POST /api/analyses should return 202 with analysis_id."""
        response = client.post("/api/analyses", json=sample_analysis_request)
        assert response.status_code == 202
        body = response.json()
        assert "analysis_id" in body
        assert body["status"] == "processing"

    def test_create_analysis_validates_body(self, client):
        """POST /api/analyses with missing object_key should return 422."""
        response = client.post("/api/analyses", json={})
        assert response.status_code == 422

    def test_get_analysis_not_found(self, client):
        """GET /api/analyses/nonexistent should return 404."""
        response = client.get("/api/analyses/nonexistent-id")
        assert response.status_code == 404

    def test_get_analysis_returns_processing(self, client, sample_analysis_request):
        """GET immediately after POST should return 'processing' status."""
        # Create analysis
        create_resp = client.post("/api/analyses", json=sample_analysis_request)
        assert create_resp.status_code == 202
        analysis_id = create_resp.json()["analysis_id"]

        # Fetch it -- background task may or may not have completed
        get_resp = client.get(f"/api/analyses/{analysis_id}")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["analysis_id"] == analysis_id
        assert body["status"] in ("processing", "completed")

    def test_list_analyses_returns_paginated(self, client):
        """GET /api/analyses should return paginated list."""
        response = client.get("/api/analyses?page=1&page_size=10")
        assert response.status_code == 200
        body = response.json()
        assert "items" in body
        assert "total" in body
        assert body["page"] == 1
        assert body["page_size"] == 10

    def test_list_analyses_validates_pagination(self, client):
        """Invalid pagination params should return 422."""
        assert client.get("/api/analyses?page=0").status_code == 422
        assert client.get("/api/analyses?page_size=0").status_code == 422
        assert client.get("/api/analyses?page_size=100").status_code == 422


# ---------------------------------------------------------------------------
# Failure handling tests
# ---------------------------------------------------------------------------

class TestPipelineFailureHandling:
    """Tests for error handling in the pipeline."""

    @pytest.mark.asyncio
    async def test_transcription_failure_marks_failed(self):
        """When transcription fails, status should be set to 'failed'."""
        from app.models.database import _local_store, create_analysis

        _local_store.clear()
        create_analysis("fail-id-1", "local-dev-user", "uploads/u1/file.webm")

        with patch("app.api.analyses._transcribe", new_callable=AsyncMock) as mock_t:
            mock_t.side_effect = RuntimeError("Transcription failed: Audio too noisy")

            # Also need to mock audio features since they run concurrently
            with patch(
                "app.api.analyses.extract_audio_features_from_s3",
                return_value={"pitch": {}, "energy": {}, "clarity": {}, "silence_ratio": 0, "summary": {}},
            ):
                from app.api.analyses import _run_analysis_pipeline
                await _run_analysis_pipeline("fail-id-1", "local-dev-user", "uploads/u1/file.webm")

        assert _local_store["fail-id-1"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_bedrock_failure_marks_failed(self):
        """When Bedrock analysis fails, status should be set to 'failed'."""
        from app.models.database import _local_store, create_analysis

        _local_store.clear()
        create_analysis("fail-id-2", "local-dev-user", "uploads/u1/file.webm")

        with patch("app.api.analyses.analyze_presentation", new_callable=AsyncMock) as mock_b:
            mock_b.side_effect = RuntimeError("Bedrock service unavailable")

            from app.api.analyses import _run_analysis_pipeline
            await _run_analysis_pipeline("fail-id-2", "local-dev-user", "uploads/u1/file.webm")

        assert _local_store["fail-id-2"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_audio_extraction_failure_marks_failed(self):
        """When audio feature extraction fails, status should be set to 'failed'."""
        from app.models.database import _local_store, create_analysis

        _local_store.clear()
        create_analysis("fail-id-3", "local-dev-user", "uploads/u1/file.webm")

        with patch(
            "app.api.analyses.extract_audio_features_from_s3",
            side_effect=RuntimeError("librosa failed"),
        ):
            from app.api.analyses import _run_analysis_pipeline
            await _run_analysis_pipeline("fail-id-3", "local-dev-user", "uploads/u1/file.webm")

        assert _local_store["fail-id-3"]["status"] == "failed"
