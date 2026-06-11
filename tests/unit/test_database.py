"""
Unit tests for DynamoDB operations (app.models.database).

Tests cover:
- get_table() returns a valid DynamoDB Table resource
- Table name matches settings configuration
"""
import pytest
from unittest.mock import patch, MagicMock


class TestGetTable:
    """Tests for the get_table() function."""

    def test_returns_dynamodb_table(self):
        """Should return a DynamoDB Table resource."""
        mock_resource = MagicMock()
        mock_table = MagicMock()
        mock_resource.Table.return_value = mock_table

        with patch("app.models.database.boto3") as mock_boto3:
            mock_boto3.resource.return_value = mock_resource
            from app.models.database import get_table

            table = get_table()

        assert table == mock_table

    def test_uses_configured_table_name(self):
        """Should use the table name from settings."""
        mock_resource = MagicMock()

        with patch("app.models.database.boto3") as mock_boto3:
            mock_boto3.resource.return_value = mock_resource
            from app.models.database import get_table

            get_table()

        mock_resource.Table.assert_called_once_with("test-presenter-feedback-table")

    def test_uses_configured_region(self):
        """Should use the AWS region from settings."""
        with patch("app.models.database.boto3") as mock_boto3:
            mock_boto3.resource.return_value = MagicMock()
            from app.models.database import get_table

            get_table()

        mock_boto3.resource.assert_called_once_with("dynamodb", region_name="us-east-1")
