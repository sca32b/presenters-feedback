"""
Root conftest.py - shared fixtures for the entire test suite.

Provides common fixtures for:
- FastAPI TestClient setup
- AWS service mocking (S3, Transcribe, Bedrock, DynamoDB)
- Sample data matching the actual Pydantic schemas
- Application settings override
"""
import json
import os
import sys
import pytest
from unittest.mock import MagicMock, patch
from pathlib import Path

# Ensure backend app is importable
PROJECT_ROOT = Path(__file__).parent.parent
BACKEND_DIR = PROJECT_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))


# ---------------------------------------------------------------------------
# Settings override - force local dev mode for tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def override_settings(monkeypatch):
    """Override settings for all tests to use test values."""
    monkeypatch.setenv("LOCAL_DEV", "true")
    monkeypatch.setenv("S3_BUCKET", "test-presenter-feedback-bucket")
    monkeypatch.setenv("DYNAMODB_TABLE", "test-presenter-feedback-table")
    monkeypatch.setenv("BEDROCK_MODEL_ID", "anthropic.claude-3-sonnet-20240229-v1:0")
    monkeypatch.setenv("COGNITO_USER_POOL_ID", "us-east-1_testpool")
    monkeypatch.setenv("COGNITO_APP_CLIENT_ID", "test-client-id")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:3000")


# ---------------------------------------------------------------------------
# FastAPI TestClient
# ---------------------------------------------------------------------------

@pytest.fixture
def client():
    """FastAPI TestClient for integration testing of API endpoints."""
    from fastapi.testclient import TestClient
    from app.main import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Sample data fixtures aligned with actual Pydantic schemas
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_analysis_results():
    """Sample analysis results matching the AnalysisResults schema."""
    return {
        "voice_tone": {
            "score": 72,
            "confidence_level": "moderate",
            "warmth": "high",
            "monotone_detected": False,
            "summary": "Good vocal variety with warm delivery. Confidence level is moderate, with some hesitation."
        },
        "vocabulary": {
            "score": 65,
            "filler_word_count": 12,
            "unique_word_ratio": 0.74,
            "readability_level": "conversational",
            "summary": "Conversational vocabulary with some filler words. Good unique word ratio."
        },
        "pacing": {
            "score": 58,
            "words_per_minute": 162,
            "variation": "low",
            "pause_usage": "insufficient",
            "summary": "Speaking pace is slightly fast. More pauses needed for emphasis."
        },
        "overall_score": 64,
        "overall_summary": "A solid presentation with room for improvement. The delivery shows warmth but needs more confidence and pacing control to reach TedX-level quality.",
        "recommendations": [
            "Slow down during key points and use 2-3 second pauses for emphasis",
            "Reduce filler words ('um', 'like') -- detected 12 instances",
            "Vary vocal pitch more to avoid monotone stretches"
        ]
    }


@pytest.fixture
def sample_transcript_data():
    """Sample Transcribe output as stored in S3."""
    return {
        "results": {
            "transcripts": [
                {
                    "transcript": (
                        "Good morning everyone. Today I want to talk about "
                        "the importance of clear communication in presentations. "
                        "Um, first let me start by saying that, you know, "
                        "effective presentations require practice. Uh, and "
                        "preparation is key to delivering a compelling message."
                    )
                }
            ],
            "items": [
                {"start_time": "0.0", "end_time": "0.5",
                 "alternatives": [{"content": "Good", "confidence": "0.99"}],
                 "type": "pronunciation"},
                {"start_time": "0.5", "end_time": "1.0",
                 "alternatives": [{"content": "morning", "confidence": "0.99"}],
                 "type": "pronunciation"},
            ]
        }
    }


@pytest.fixture
def sample_upload_request():
    """Sample request body for POST /api/uploads."""
    return {
        "filename": "recording-2026-02-08.webm",
        "content_type": "audio/webm"
    }


@pytest.fixture
def sample_analysis_request():
    """Sample request body for POST /api/analyses.

    Uses 'local-dev-user' to match the LOCAL_DEV auth bypass identity,
    so the object_key authorization check passes.
    """
    return {
        "object_key": "uploads/local-dev-user/abc123.webm"
    }


# ---------------------------------------------------------------------------
# AWS mock fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_s3_client():
    """Mocked boto3 S3 client."""
    client = MagicMock()
    client.generate_presigned_url.return_value = "https://test-bucket.s3.amazonaws.com/uploads/test/file.webm?signed=true"
    client.put_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
    client.get_object.return_value = {
        "Body": MagicMock(read=lambda: b'{"results":{"transcripts":[{"transcript":"test"}]}}'),
        "ContentLength": 1024,
    }
    client.delete_object.return_value = {"ResponseMetadata": {"HTTPStatusCode": 204}}
    return client


@pytest.fixture
def mock_transcribe_client():
    """Mocked boto3 Transcribe client."""
    client = MagicMock()
    client.start_transcription_job.return_value = {
        "TranscriptionJob": {
            "TranscriptionJobName": "pf-test-job-123",
            "TranscriptionJobStatus": "IN_PROGRESS"
        }
    }
    client.get_transcription_job.return_value = {
        "TranscriptionJob": {
            "TranscriptionJobName": "pf-test-job-123",
            "TranscriptionJobStatus": "COMPLETED",
            "Transcript": {
                "TranscriptFileUri": "s3://bucket/transcripts/pf-test-job-123.json"
            }
        }
    }
    return client


@pytest.fixture
def mock_bedrock_client(sample_analysis_results):
    """Mocked boto3 Bedrock Runtime client."""
    client = MagicMock()
    response_body = json.dumps({
        "content": [{"text": json.dumps(sample_analysis_results)}]
    })
    client.invoke_model.return_value = {
        "body": MagicMock(read=lambda: response_body.encode("utf-8")),
        "ResponseMetadata": {"HTTPStatusCode": 200}
    }
    return client


@pytest.fixture
def mock_dynamodb_table():
    """Mocked DynamoDB table resource."""
    table = MagicMock()
    table.put_item.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
    table.get_item.return_value = {
        "Item": {
            "analysis_id": "test-analysis-123",
            "user_id": "test-user-id",
            "status": "completed",
            "created_at": "2026-02-08T12:00:00Z",
            "results": {
                "voice_tone": {"score": 72, "confidence_level": "moderate",
                               "warmth": "high", "monotone_detected": False,
                               "summary": "Good."},
                "vocabulary": {"score": 65, "filler_word_count": 12,
                               "unique_word_ratio": 0.74,
                               "readability_level": "conversational",
                               "summary": "Decent."},
                "pacing": {"score": 58, "words_per_minute": 162,
                           "variation": "low", "pause_usage": "insufficient",
                           "summary": "Fast."},
                "overall_score": 64,
                "overall_summary": "Solid presentation.",
                "recommendations": ["Slow down", "Fewer fillers", "Vary pitch"],
            },
        }
    }
    table.update_item.return_value = {"ResponseMetadata": {"HTTPStatusCode": 200}}
    table.query.return_value = {
        "Items": [
            {
                "analysis_id": "test-analysis-123",
                "user_id": "test-user-id",
                "status": "completed",
                "created_at": "2026-02-08T12:00:00Z",
            }
        ],
        "Count": 1,
    }
    table.scan.return_value = {"Items": [], "Count": 0}
    return table


@pytest.fixture
def aws_credentials(monkeypatch):
    """Set dummy AWS credentials for moto/mocked tests."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_SECURITY_TOKEN", "testing")
    monkeypatch.setenv("AWS_SESSION_TOKEN", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")


# ---------------------------------------------------------------------------
# Moto-based AWS fixtures (real service emulation, not MagicMock)
# ---------------------------------------------------------------------------

@pytest.fixture
def moto_s3(aws_credentials):
    """Create a real moto S3 bucket for integration testing.

    Use this instead of mock_s3_client when you need actual S3 behavior
    (e.g., testing upload/download, presigned URL generation).
    """
    from moto import mock_aws
    import boto3

    with mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-presenter-feedback-bucket")
        yield s3


@pytest.fixture
def moto_dynamodb(aws_credentials):
    """Create a real moto DynamoDB table matching the SAM template schema.

    Use this instead of mock_dynamodb_table when you need actual DynamoDB
    behavior (e.g., testing queries, GSI, scan).
    """
    from moto import mock_aws
    import boto3

    with mock_aws():
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-presenter-feedback-table",
            AttributeDefinitions=[
                {"AttributeName": "analysis_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "analysis_id", "KeyType": "HASH"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "user-index",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "analysis_id", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.meta.client.get_waiter("table_exists").wait(
            TableName="test-presenter-feedback-table"
        )
        yield table


@pytest.fixture
def moto_transcribe(aws_credentials):
    """Create a moto Transcribe client for integration testing.

    Note: moto's Transcribe support is limited. Jobs will transition to
    COMPLETED but won't produce real transcripts. Use mock_transcribe_client
    for most tests; use this only for testing boto3 call patterns.
    """
    from moto import mock_aws
    import boto3

    with mock_aws():
        client = boto3.client("transcribe", region_name="us-east-1")
        yield client


@pytest.fixture
def moto_aws_all(aws_credentials):
    """Create all moto AWS services together in a single context.

    Useful for full integration tests that need S3 + DynamoDB + Transcribe
    in the same mock context.
    """
    from moto import mock_aws
    import boto3

    with mock_aws():
        # S3
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-presenter-feedback-bucket")

        # DynamoDB
        dynamodb = boto3.resource("dynamodb", region_name="us-east-1")
        table = dynamodb.create_table(
            TableName="test-presenter-feedback-table",
            AttributeDefinitions=[
                {"AttributeName": "analysis_id", "AttributeType": "S"},
                {"AttributeName": "user_id", "AttributeType": "S"},
            ],
            KeySchema=[
                {"AttributeName": "analysis_id", "KeyType": "HASH"},
            ],
            GlobalSecondaryIndexes=[
                {
                    "IndexName": "user-index",
                    "KeySchema": [
                        {"AttributeName": "user_id", "KeyType": "HASH"},
                        {"AttributeName": "analysis_id", "KeyType": "RANGE"},
                    ],
                    "Projection": {"ProjectionType": "ALL"},
                }
            ],
            BillingMode="PAY_PER_REQUEST",
        )
        table.meta.client.get_waiter("table_exists").wait(
            TableName="test-presenter-feedback-table"
        )

        # Transcribe
        transcribe = boto3.client("transcribe", region_name="us-east-1")

        yield {
            "s3": s3,
            "dynamodb_table": table,
            "transcribe": transcribe,
        }
