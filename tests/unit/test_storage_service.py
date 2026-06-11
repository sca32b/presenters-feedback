"""
Unit tests for the S3 storage service (app.services.storage).

Tests cover:
- Presigned URL generation
- Object key format (uploads/{user_id}/{uuid}.{ext})
- Content type passthrough
- File extension extraction
- Error handling for S3 failures
"""
import pytest
from unittest.mock import patch, MagicMock
from botocore.exceptions import ClientError


class TestGeneratePresignedUploadUrl:
    """Tests for generate_presigned_upload_url()."""

    @pytest.fixture(autouse=True)
    def aws_mode(self, monkeypatch):
        """These tests validate AWS presigned URL generation, not LOCAL_DEV URLs."""
        monkeypatch.setenv("LOCAL_DEV", "false")
        import importlib
        import app.config.settings
        import app.services.storage
        importlib.reload(app.config.settings)
        importlib.reload(app.services.storage)

    def test_returns_url_and_object_key(self, mock_s3_client):
        """Should return a tuple of (upload_url, object_key)."""
        with patch("app.services.storage.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_s3_client
            from app.services.storage import generate_presigned_upload_url

            url, key = generate_presigned_upload_url(
                user_id="user-123",
                filename="recording.webm",
                content_type="audio/webm",
            )

        assert isinstance(url, str)
        assert url.startswith("https://")
        assert isinstance(key, str)

    def test_object_key_contains_user_id(self, mock_s3_client):
        """Object key should include the user ID."""
        with patch("app.services.storage.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_s3_client
            from app.services.storage import generate_presigned_upload_url

            _, key = generate_presigned_upload_url(
                user_id="user-abc",
                filename="test.webm",
                content_type="audio/webm",
            )

        assert "user-abc" in key
        assert key.startswith("uploads/user-abc/")

    def test_object_key_preserves_extension(self, mock_s3_client):
        """Object key should use the same extension as the filename."""
        with patch("app.services.storage.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_s3_client
            from app.services.storage import generate_presigned_upload_url

            _, key_webm = generate_presigned_upload_url("u1", "rec.webm", "audio/webm")
            _, key_wav = generate_presigned_upload_url("u1", "rec.wav", "audio/wav")

        assert key_webm.endswith(".webm")
        assert key_wav.endswith(".wav")

    def test_object_key_defaults_to_webm_no_extension(self, mock_s3_client):
        """Filename without extension should default to .webm."""
        with patch("app.services.storage.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_s3_client
            from app.services.storage import generate_presigned_upload_url

            _, key = generate_presigned_upload_url("u1", "recording", "audio/webm")

        assert key.endswith(".webm")

    def test_presigned_url_uses_correct_bucket(self, mock_s3_client):
        """Should use the configured S3 bucket."""
        with patch("app.services.storage.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_s3_client
            from app.services.storage import generate_presigned_upload_url

            generate_presigned_upload_url("u1", "rec.webm", "audio/webm")

        call_kwargs = mock_s3_client.generate_presigned_url.call_args
        params = call_kwargs[1]["Params"] if "Params" in call_kwargs[1] else call_kwargs[0][1]
        assert params["Bucket"] == "test-presenter-feedback-bucket"

    def test_presigned_url_sets_content_type(self, mock_s3_client):
        """Should pass content_type to the presigned URL parameters."""
        with patch("app.services.storage.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_s3_client
            from app.services.storage import generate_presigned_upload_url

            generate_presigned_upload_url("u1", "rec.webm", "audio/webm")

        call_kwargs = mock_s3_client.generate_presigned_url.call_args
        params = call_kwargs[1]["Params"] if "Params" in call_kwargs[1] else call_kwargs[0][1]
        assert params["ContentType"] == "audio/webm"

    def test_presigned_url_uses_put_object(self, mock_s3_client):
        """Should generate a presigned URL for put_object operation."""
        with patch("app.services.storage.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_s3_client
            from app.services.storage import generate_presigned_upload_url

            generate_presigned_upload_url("u1", "rec.webm", "audio/webm")

        call_args = mock_s3_client.generate_presigned_url.call_args
        # First positional arg should be "put_object"
        assert call_args[0][0] == "put_object"

    def test_s3_error_propagates(self, mock_s3_client):
        """Should propagate S3 client errors."""
        mock_s3_client.generate_presigned_url.side_effect = ClientError(
            {"Error": {"Code": "InternalError", "Message": "S3 error"}},
            "GeneratePresignedUrl"
        )

        with patch("app.services.storage.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_s3_client
            from app.services.storage import generate_presigned_upload_url

            with pytest.raises(ClientError):
                generate_presigned_upload_url("u1", "rec.webm", "audio/webm")

    def test_object_key_uses_uuid(self, mock_s3_client):
        """Object key filename should be a UUID (not the original filename)."""
        with patch("app.services.storage.boto3") as mock_boto3:
            mock_boto3.client.return_value = mock_s3_client
            from app.services.storage import generate_presigned_upload_url

            _, key1 = generate_presigned_upload_url("u1", "rec.webm", "audio/webm")
            _, key2 = generate_presigned_upload_url("u1", "rec.webm", "audio/webm")

        # Keys should be different due to UUID
        assert key1 != key2
