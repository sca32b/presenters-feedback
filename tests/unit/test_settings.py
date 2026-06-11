"""
Unit tests for application settings (app.config.settings).

Tests cover:
- Default values
- Environment variable overrides
- Settings fields and types
"""
import pytest


class TestSettings:
    """Tests for the Settings configuration model."""

    def test_default_values(self):
        """Settings should have sensible defaults."""
        from app.config.settings import Settings

        s = Settings(
            _env_file=None,  # Don't read .env in tests
        )
        assert s.local_dev is False  # defaults to False unless env var set
        assert s.aws_region == "us-east-1"
        assert s.s3_bucket == "presenters-feedback-dev"
        assert s.dynamodb_table == "presenters-feedback-dev"
        assert s.upload_url_expiry == 300
        assert s.max_audio_size_mb == 50

    def test_bedrock_model_default(self):
        """Default Bedrock model should be Claude Fable 5."""
        from app.config.settings import Settings

        s = Settings(_env_file=None)
        assert s.bedrock_model_id == "us.anthropic.claude-fable-5"

    def test_cors_default(self):
        """Default CORS origin should be localhost."""
        from app.config.settings import Settings

        s = Settings(_env_file=None)
        assert "localhost" in s.cors_allowed_origins

    def test_env_override(self, monkeypatch):
        """Environment variables should override defaults."""
        monkeypatch.setenv("S3_BUCKET", "my-custom-bucket")
        monkeypatch.setenv("AWS_REGION", "eu-west-1")

        from app.config.settings import Settings
        s = Settings(_env_file=None)
        assert s.s3_bucket == "my-custom-bucket"
        assert s.aws_region == "eu-west-1"

    def test_local_dev_flag(self, monkeypatch):
        """LOCAL_DEV=true should enable local dev mode."""
        monkeypatch.setenv("LOCAL_DEV", "true")

        from app.config.settings import Settings
        s = Settings(_env_file=None)
        assert s.local_dev is True

    def test_upload_url_expiry_is_integer(self):
        """Upload URL expiry should be an integer (seconds)."""
        from app.config.settings import Settings

        s = Settings(_env_file=None)
        assert isinstance(s.upload_url_expiry, int)
        assert s.upload_url_expiry > 0
