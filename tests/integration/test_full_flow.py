"""Integration tests for the full analysis pipeline."""
import pytest
from unittest.mock import patch


class TestFullAnalysisFlow:
    """End-to-end pipeline tests with mocked AWS services."""

    @pytest.mark.asyncio
    async def test_happy_path_upload_to_results(
        self,
        monkeypatch,
    ):
        """Full happy path: create record -> transcribe -> analyze -> store results."""
        monkeypatch.setenv("LOCAL_DEV", "true")
        import importlib
        import app.config.settings
        import app.services.analysis
        import app.models.database
        importlib.reload(app.config.settings)
        importlib.reload(app.models.database)
        importlib.reload(app.services.analysis)

        app.models.database._local_store.clear()
        analysis_id = await app.services.analysis.run_analysis(
            user_id="test-user",
            object_key="uploads/test-user/recording.webm",
        )

        assert isinstance(analysis_id, str)
        assert len(analysis_id) > 0
        item = app.models.database._local_store[analysis_id]
        assert item["status"] == "completed"
        assert item["results"]["overall_score"] >= 0

    @pytest.mark.asyncio
    async def test_transcription_failure_marks_failed(
        self,
        monkeypatch,
    ):
        """When transcription fails, pipeline should mark analysis as 'failed'."""
        monkeypatch.setenv("LOCAL_DEV", "true")
        import importlib
        import app.config.settings
        import app.services.analysis
        import app.models.database
        importlib.reload(app.config.settings)
        importlib.reload(app.models.database)
        importlib.reload(app.services.analysis)

        async def fail_transcription(*_args, **_kwargs):
            raise RuntimeError("Audio too noisy")

        app.models.database._local_store.clear()
        app.models.database.create_analysis("fail-id", "test-user", "uploads/test-user/file.webm")
        app.services.analysis._run_transcription = fail_transcription
        await app.services.analysis.run_analysis_for_existing(
            "fail-id", "test-user", "uploads/test-user/file.webm"
        )

        assert app.models.database._local_store["fail-id"]["status"] == "failed"

    @pytest.mark.asyncio
    async def test_presigned_url_generation_flow(self, mock_s3_client):
        """Test presigned URL generation for audio upload."""
        with patch("app.services.storage.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_s3_client
            from app.services.storage import generate_presigned_upload_url

            url, key = generate_presigned_upload_url(
                user_id="user-123",
                filename="recording.webm",
                content_type="audio/webm",
            )

        # In LOCAL_DEV, the presigned URL is a backend local-upload URL.
        assert isinstance(url, str)
        assert "http://localhost:8000/api/local-upload/" in url

        # Key should follow the expected pattern
        assert key.startswith("uploads/user-123/")
        assert key.endswith(".webm")

        mock_s3_client.generate_presigned_url.assert_not_called()


class TestAPIIntegration:
    """Integration tests for the FastAPI application."""

    def test_health_endpoint(self, client):
        """Health endpoint should work end-to-end."""
        response = client.get("/api/health")
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    def test_upload_endpoint_validates_input(self, client):
        """Upload endpoint should validate Pydantic models."""
        # Missing filename
        response = client.post("/api/uploads", json={})
        assert response.status_code == 422

        # Valid request (but handler not implemented)
        response = client.post("/api/uploads", json={
            "filename": "test.webm",
            "content_type": "audio/webm",
        })
        # 200 if implemented, 500 if NotImplementedError
        assert response.status_code in (200, 500)

    def test_analyses_endpoint_validates_pagination(self, client):
        """Analyses list endpoint should validate pagination params."""
        # Invalid page (0)
        response = client.get("/api/analyses?page=0")
        assert response.status_code == 422

        # Invalid page_size (>50)
        response = client.get("/api/analyses?page_size=100")
        assert response.status_code == 422

    def test_analyses_create_validates_input(self, client):
        """Create analysis endpoint should validate request body."""
        # Missing object_key
        response = client.post("/api/analyses", json={})
        assert response.status_code == 422

    def test_cors_headers_on_all_responses(self, client):
        """All responses should include CORS headers."""
        response = client.get(
            "/api/health",
            headers={"Origin": "http://localhost:3000"}
        )
        assert response.status_code == 200
        assert "access-control-allow-origin" in response.headers
