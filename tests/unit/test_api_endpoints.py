"""
Unit tests for FastAPI API endpoints.

Tests the actual FastAPI routes defined in:
- app.api.health (GET /api/health)
- app.api.uploads (POST /api/uploads)
- app.api.analyses (POST /api/analyses, GET /api/analyses/{id}, GET /api/analyses)

Uses FastAPI TestClient for synchronous testing of async endpoints.
All tests run in LOCAL_DEV mode (set by conftest.py) so auth is bypassed
and the local-dev-user identity is injected automatically.
"""
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ---------------------------------------------------------------------------
# Health endpoint tests
# ---------------------------------------------------------------------------

class TestHealthEndpoint:
    """Tests for GET /api/health."""

    def test_health_returns_200(self, client):
        """Health check should return 200 with status ok."""
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_health_no_auth_required(self, client):
        """Health check should not require authentication."""
        response = client.get("/api/health")
        assert response.status_code == 200


# ---------------------------------------------------------------------------
# Upload endpoint tests
# ---------------------------------------------------------------------------

class TestUploadEndpoint:
    """Tests for POST /api/uploads (presigned URL generation)."""

    def test_upload_returns_presigned_url(self, client):
        """Should return a presigned URL and object key in LOCAL_DEV mode."""
        response = client.post("/api/uploads", json={
            "filename": "recording.webm",
            "content_type": "audio/webm",
        })
        assert response.status_code == 200
        body = response.json()
        assert "upload_url" in body
        assert "object_key" in body
        assert body["object_key"].startswith("uploads/local-dev-user/")
        assert body["object_key"].endswith(".webm")

    def test_upload_url_points_to_local_endpoint(self, client):
        """In LOCAL_DEV, the upload URL should point to localhost."""
        response = client.post("/api/uploads", json={
            "filename": "test.webm",
            "content_type": "audio/webm",
        })
        body = response.json()
        assert "localhost:8000" in body["upload_url"]
        assert "/api/local-upload/" in body["upload_url"]

    def test_upload_validates_request_body(self, client):
        """Should reject request missing required fields."""
        response = client.post("/api/uploads", json={})
        assert response.status_code == 422

    def test_upload_default_content_type(self, client):
        """Should default to audio/webm if content_type is omitted."""
        response = client.post("/api/uploads", json={"filename": "recording.webm"})
        # Should not get a 422 because content_type has a default
        assert response.status_code == 200

    def test_upload_preserves_file_extension(self, client):
        """Object key should use the extension from the filename."""
        response = client.post("/api/uploads", json={
            "filename": "speech.wav",
            "content_type": "audio/wav",
        })
        assert response.status_code == 200
        assert response.json()["object_key"].endswith(".wav")


# ---------------------------------------------------------------------------
# Analysis creation endpoint tests
# ---------------------------------------------------------------------------

class TestAnalysisCreateEndpoint:
    """Tests for POST /api/analyses (start analysis)."""

    def test_create_analysis_returns_202(self, client):
        """Should return 202 with analysis_id and status 'processing'."""
        response = client.post("/api/analyses", json={
            "object_key": "uploads/local-dev-user/abc123.webm",
        })
        assert response.status_code == 202
        body = response.json()
        assert "analysis_id" in body
        assert body["status"] == "processing"
        assert len(body["analysis_id"]) > 0

    def test_create_analysis_validates_object_key(self, client):
        """Should reject request without object_key."""
        response = client.post("/api/analyses", json={})
        assert response.status_code == 422

    def test_create_analysis_rejects_other_users_key(self, client):
        """Should return 403 when object_key belongs to a different user."""
        response = client.post("/api/analyses", json={
            "object_key": "uploads/other-user-id/file.webm",
        })
        assert response.status_code == 403
        assert "Access denied" in response.json()["detail"]

    def test_create_analysis_rejects_invalid_key_prefix(self, client):
        """Should return 403 for object_key not starting with uploads/{user}/."""
        response = client.post("/api/analyses", json={
            "object_key": "random/path/file.webm",
        })
        assert response.status_code == 403

    def test_create_analysis_creates_db_record(self, client):
        """The created analysis should be retrievable via GET."""
        # Create an analysis
        create_resp = client.post("/api/analyses", json={
            "object_key": "uploads/local-dev-user/test-file.webm",
        })
        assert create_resp.status_code == 202
        analysis_id = create_resp.json()["analysis_id"]

        # Retrieve it
        get_resp = client.get(f"/api/analyses/{analysis_id}")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["analysis_id"] == analysis_id
        # Status might be "processing" or "completed" (mock runs fast)
        assert body["status"] in ("processing", "completed")


# ---------------------------------------------------------------------------
# Analysis retrieval endpoint tests
# ---------------------------------------------------------------------------

class TestAnalysisGetEndpoint:
    """Tests for GET /api/analyses/{analysis_id}."""

    def test_get_analysis_not_found(self, client):
        """Should return 404 for nonexistent analysis."""
        response = client.get("/api/analyses/nonexistent-id-12345")
        assert response.status_code == 404
        assert response.json()["detail"] == "Analysis not found"

    def test_get_analysis_returns_processing(self, client):
        """Should return processing status for a new analysis."""
        # Create
        create_resp = client.post("/api/analyses", json={
            "object_key": "uploads/local-dev-user/file.webm",
        })
        analysis_id = create_resp.json()["analysis_id"]

        # Retrieve immediately (may still be processing)
        get_resp = client.get(f"/api/analyses/{analysis_id}")
        assert get_resp.status_code == 200
        body = get_resp.json()
        assert body["analysis_id"] == analysis_id
        assert body["status"] in ("processing", "completed")
        assert "created_at" in body

    def test_get_analysis_other_user_returns_404(self, client):
        """Should return 404 when accessing another user's analysis.

        In LOCAL_DEV, we manually inject a record with a different user_id
        to test authorization.
        """
        from app.models.database import _local_store

        # Manually insert a record for a different user
        _local_store["other-user-analysis"] = {
            "analysis_id": "other-user-analysis",
            "user_id": "someone-else",
            "object_key": "uploads/someone-else/file.webm",
            "status": "completed",
            "created_at": "2026-02-08T12:00:00Z",
            "results": None,
        }

        response = client.get("/api/analyses/other-user-analysis")
        assert response.status_code == 404

        # Clean up
        del _local_store["other-user-analysis"]

    def test_get_completed_analysis_has_results(self, client):
        """A completed analysis should include results."""
        from app.models.database import _local_store

        # Insert a completed analysis for the local-dev-user
        _local_store["completed-test"] = {
            "analysis_id": "completed-test",
            "user_id": "local-dev-user",
            "object_key": "uploads/local-dev-user/file.webm",
            "status": "completed",
            "created_at": "2026-02-08T12:00:00Z",
            "results": {
                "voice_tone": {
                    "score": 72, "confidence_level": "moderate",
                    "warmth": "high", "monotone_detected": False,
                    "summary": "Good vocal variety."
                },
                "vocabulary": {
                    "score": 65, "filler_word_count": 3,
                    "unique_word_ratio": 0.74,
                    "readability_level": "conversational",
                    "summary": "Good word choice."
                },
                "pacing": {
                    "score": 70, "words_per_minute": 150,
                    "variation": "moderate", "pause_usage": "adequate",
                    "summary": "Good pace."
                },
                "overall_score": 69,
                "overall_summary": "Solid presentation.",
                "recommendations": ["Tip 1", "Tip 2", "Tip 3"],
            },
        }

        response = client.get("/api/analyses/completed-test")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "completed"
        assert body["results"] is not None
        assert body["results"]["overall_score"] == 69
        assert body["results"]["voice_tone"]["score"] == 72
        assert len(body["results"]["recommendations"]) == 3

        # Clean up
        del _local_store["completed-test"]


# ---------------------------------------------------------------------------
# Analysis list endpoint tests
# ---------------------------------------------------------------------------

class TestAnalysisListEndpoint:
    """Tests for GET /api/analyses (list user's analyses, paginated)."""

    def test_list_analyses_empty(self, client):
        """Should return empty list when user has no analyses."""
        from app.models.database import _local_store
        _local_store.clear()

        response = client.get("/api/analyses")
        assert response.status_code == 200
        body = response.json()
        assert body["items"] == []
        assert body["total"] == 0
        assert body["page"] == 1
        assert body["page_size"] == 10

    def test_list_analyses_returns_own_only(self, client):
        """Should only return analyses belonging to the authenticated user."""
        from app.models.database import _local_store
        _local_store.clear()

        # Add analyses for two different users
        _local_store["mine"] = {
            "analysis_id": "mine",
            "user_id": "local-dev-user",
            "object_key": "uploads/local-dev-user/a.webm",
            "status": "completed",
            "created_at": "2026-02-08T12:00:00Z",
            "results": None,
        }
        _local_store["theirs"] = {
            "analysis_id": "theirs",
            "user_id": "other-user",
            "object_key": "uploads/other-user/b.webm",
            "status": "completed",
            "created_at": "2026-02-08T11:00:00Z",
            "results": None,
        }

        response = client.get("/api/analyses")
        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 1
        assert len(body["items"]) == 1
        assert body["items"][0]["analysis_id"] == "mine"

        _local_store.clear()

    def test_list_analyses_default_pagination(self, client):
        """Should default to page=1, page_size=10."""
        response = client.get("/api/analyses")
        assert response.status_code == 200
        body = response.json()
        assert body["page"] == 1
        assert body["page_size"] == 10

    def test_list_analyses_custom_pagination(self, client):
        """Should respect custom page and page_size params."""
        response = client.get("/api/analyses?page=2&page_size=5")
        assert response.status_code == 200
        body = response.json()
        assert body["page"] == 2
        assert body["page_size"] == 5

    def test_list_analyses_validates_page_params(self, client):
        """Should reject invalid pagination parameters."""
        # page must be >= 1
        response = client.get("/api/analyses?page=0")
        assert response.status_code == 422

        # page_size must be >= 1
        response = client.get("/api/analyses?page_size=0")
        assert response.status_code == 422

        # page_size must be <= 50
        response = client.get("/api/analyses?page_size=100")
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# CORS tests
# ---------------------------------------------------------------------------

class TestCORS:
    """Tests for CORS middleware configuration."""

    def test_cors_headers_present(self, client):
        """Responses should include CORS headers."""
        response = client.get(
            "/api/health",
            headers={"Origin": "http://localhost:3000"},
        )
        assert "access-control-allow-origin" in response.headers

    def test_options_preflight(self, client):
        """OPTIONS requests should return CORS preflight headers."""
        response = client.options(
            "/api/uploads",
            headers={
                "Origin": "http://localhost:3000",
                "Access-Control-Request-Method": "POST",
            }
        )
        assert response.status_code == 200
        assert "access-control-allow-methods" in response.headers


# ---------------------------------------------------------------------------
# Pydantic schema validation tests
# ---------------------------------------------------------------------------

class TestSchemaValidation:
    """Tests for Pydantic request/response model validation."""

    def test_upload_request_requires_filename(self):
        """UploadRequest requires filename field."""
        from app.models.schemas import UploadRequest
        with pytest.raises(Exception):
            UploadRequest()

    def test_upload_request_defaults_content_type(self):
        """UploadRequest defaults content_type to audio/webm."""
        from app.models.schemas import UploadRequest
        req = UploadRequest(filename="test.webm")
        assert req.content_type == "audio/webm"

    def test_analysis_results_score_bounds(self):
        """Score fields must be 0-100."""
        from app.models.schemas import VoiceToneResult
        with pytest.raises(Exception):
            VoiceToneResult(
                score=101,
                confidence_level="high",
                warmth="high",
                monotone_detected=False,
                summary="Test"
            )

    def test_analysis_results_negative_score(self):
        """Negative scores should fail validation."""
        from app.models.schemas import VoiceToneResult
        with pytest.raises(Exception):
            VoiceToneResult(
                score=-1,
                confidence_level="high",
                warmth="high",
                monotone_detected=False,
                summary="Test"
            )

    def test_analysis_results_valid(self, sample_analysis_results):
        """Valid analysis results should pass validation."""
        from app.models.schemas import AnalysisResults
        results = AnalysisResults(**sample_analysis_results)
        assert results.overall_score == 64
        assert results.voice_tone.score == 72
        assert results.vocabulary.filler_word_count == 12
        assert results.pacing.words_per_minute == 162
        assert len(results.recommendations) == 3

    def test_analysis_list_response_structure(self):
        """AnalysisListResponse should have items, total, page, page_size."""
        from app.models.schemas import AnalysisListResponse
        resp = AnalysisListResponse(items=[], total=0, page=1, page_size=10)
        assert resp.items == []
        assert resp.total == 0
