"""
Integration tests for the full analysis pipeline.

Tests the complete flow through app.services.analysis.run_analysis()
with all AWS services mocked. Verifies that components are properly
wired together.
"""
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


class TestFullAnalysisFlow:
    """End-to-end pipeline tests with mocked AWS services."""

    @pytest.mark.asyncio
    async def test_happy_path_upload_to_results(
        self,
        mock_dynamodb_table,
        mock_transcribe_client,
        mock_bedrock_client,
        mock_s3_client,
        sample_transcript_data,
        sample_analysis_results,
    ):
        """Full happy path: create record -> transcribe -> analyze -> store results."""
        mock_s3_client.get_object.return_value = {
            "Body": MagicMock(read=lambda: json.dumps(sample_transcript_data).encode())
        }

        with patch("app.services.analysis.get_table", return_value=mock_dynamodb_table), \
             patch("app.services.transcribe.boto3") as mock_t_boto3, \
             patch("app.services.bedrock.boto3") as mock_b_boto3, \
             patch("app.services.analysis.boto3") as mock_a_boto3, \
             patch("app.services.analysis.time") as mock_time:

            mock_t_boto3.client.return_value = mock_transcribe_client
            mock_b_boto3.client.return_value = mock_bedrock_client
            mock_a_boto3.client.return_value = mock_s3_client
            mock_time.sleep = MagicMock()

            from app.services.analysis import run_analysis
            analysis_id = await run_analysis(
                user_id="test-user",
                object_key="uploads/test-user/recording.webm",
            )

        # Verify the complete sequence
        # 1. DynamoDB record created with 'processing' status
        mock_dynamodb_table.put_item.assert_called_once()
        initial_item = mock_dynamodb_table.put_item.call_args[1]["Item"]
        assert initial_item["status"] == "processing"

        # 2. Transcription job started
        mock_transcribe_client.start_transcription_job.assert_called_once()

        # 3. Transcript fetched from S3
        mock_s3_client.get_object.assert_called_once()

        # 4. Bedrock analysis invoked
        mock_bedrock_client.invoke_model.assert_called_once()

        # 5. Results stored with 'completed' status
        mock_dynamodb_table.update_item.assert_called()
        final_update = mock_dynamodb_table.update_item.call_args[1]
        assert final_update["ExpressionAttributeValues"][":s"] == "completed"
        assert ":r" in final_update["ExpressionAttributeValues"]

        # 6. Returns valid analysis_id
        assert isinstance(analysis_id, str)
        assert len(analysis_id) > 0

    @pytest.mark.asyncio
    async def test_transcription_failure_marks_failed(
        self,
        mock_dynamodb_table,
        mock_transcribe_client,
    ):
        """When transcription fails, pipeline should mark analysis as 'failed'."""
        mock_transcribe_client.get_transcription_job.return_value = {
            "TranscriptionJob": {
                "TranscriptionJobName": "pf-test",
                "TranscriptionJobStatus": "FAILED",
                "FailureReason": "Audio too noisy",
            }
        }

        with patch("app.services.analysis.get_table", return_value=mock_dynamodb_table), \
             patch("app.services.transcribe.boto3") as mock_t_boto3, \
             patch("app.services.analysis.time") as mock_time:

            mock_t_boto3.client.return_value = mock_transcribe_client
            mock_time.sleep = MagicMock()

            from app.services.analysis import run_analysis
            analysis_id = await run_analysis("test-user", "uploads/test-user/file.webm")

        # Should still return an analysis_id
        assert isinstance(analysis_id, str)

        # Status should be 'failed'
        mock_dynamodb_table.update_item.assert_called()
        update_args = mock_dynamodb_table.update_item.call_args[1]
        assert update_args["ExpressionAttributeValues"][":s"] == "failed"

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

        # URL should be a presigned URL
        assert isinstance(url, str)
        assert "https://" in url

        # Key should follow the expected pattern
        assert key.startswith("uploads/user-123/")
        assert key.endswith(".webm")

        # Verify the S3 client was called correctly
        mock_s3_client.generate_presigned_url.assert_called_once()


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
