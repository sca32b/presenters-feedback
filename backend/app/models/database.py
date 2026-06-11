"""DynamoDB table operations for analysis records.

In LOCAL_DEV mode, uses an in-memory dictionary instead of DynamoDB.
"""

import json
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from app.config.settings import settings

logger = logging.getLogger(__name__)

# In-memory store for LOCAL_DEV mode
_local_store: dict[str, dict] = {}


def _float_to_decimal(obj):
    """Recursively convert float values to Decimal for DynamoDB storage."""
    if isinstance(obj, float):
        return Decimal(str(obj))
    if isinstance(obj, dict):
        return {k: _float_to_decimal(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_float_to_decimal(v) for v in obj]
    return obj


def _decimal_to_float(obj):
    """Recursively convert Decimal values back to float/int for JSON serialization."""
    if isinstance(obj, Decimal):
        if obj == int(obj):
            return int(obj)
        return float(obj)
    if isinstance(obj, dict):
        return {k: _decimal_to_float(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_decimal_to_float(v) for v in obj]
    return obj


def get_table():
    """Get the DynamoDB table resource."""
    import boto3
    dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
    return dynamodb.Table(settings.dynamodb_table)


def create_analysis(analysis_id: str, user_id: str, object_key: str) -> dict:
    """Create a new analysis record with status 'processing'."""
    item = {
        "analysis_id": analysis_id,
        "user_id": user_id,
        "object_key": object_key,
        "status": "processing",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "results": None,
    }

    if settings.local_dev:
        _local_store[analysis_id] = item
        logger.info("LOCAL_DEV: Created analysis %s", analysis_id)
        return item

    table = get_table()
    table.put_item(Item={k: v for k, v in item.items() if v is not None})
    return item


def get_analysis(analysis_id: str) -> Optional[dict]:
    """Retrieve an analysis record by ID."""
    if settings.local_dev:
        return _local_store.get(analysis_id)

    table = get_table()
    response = table.get_item(Key={"analysis_id": analysis_id})
    item = response.get("Item")
    if item:
        return _decimal_to_float(item)
    return None


def update_analysis_status(analysis_id: str, status: str, results: Optional[dict] = None):
    """Update the status (and optionally results) of an analysis record."""
    if settings.local_dev:
        if analysis_id in _local_store:
            _local_store[analysis_id]["status"] = status
            if results is not None:
                _local_store[analysis_id]["results"] = results
            logger.info("LOCAL_DEV: Updated analysis %s -> %s", analysis_id, status)
        return

    table = get_table()
    update_expr = "SET #s = :s"
    attr_names = {"#s": "status"}
    attr_values = {":s": status}

    if results is not None:
        update_expr += ", results = :r"
        attr_values[":r"] = _float_to_decimal(results)

    table.update_item(
        Key={"analysis_id": analysis_id},
        UpdateExpression=update_expr,
        ExpressionAttributeNames=attr_names,
        ExpressionAttributeValues=attr_values,
    )


def delete_analysis(analysis_id: str) -> Optional[dict]:
    """Delete an analysis record by ID. Returns the deleted item, or None if not found."""
    if settings.local_dev:
        item = _local_store.pop(analysis_id, None)
        if item:
            logger.info("LOCAL_DEV: Deleted analysis %s", analysis_id)
        return item

    table = get_table()
    response = table.delete_item(
        Key={"analysis_id": analysis_id},
        ReturnValues="ALL_OLD",
    )
    item = response.get("Attributes")
    if item:
        return _decimal_to_float(item)
    return None


def list_analyses_for_user(user_id: str, page: int = 1, page_size: int = 10) -> tuple[list[dict], int]:
    """List analyses for a user, paginated. Returns (items, total_count)."""
    if settings.local_dev:
        all_items = sorted(
            [item for item in _local_store.values() if item["user_id"] == user_id],
            key=lambda x: x["created_at"],
            reverse=True,
        )
        total = len(all_items)
        start = (page - 1) * page_size
        items = all_items[start:start + page_size]
        return items, total

    table = get_table()
    # Use a GSI on user_id for efficient queries in production.
    # For simplicity, scan with filter (acceptable for low-volume personal use).
    response = table.scan(
        FilterExpression="user_id = :uid",
        ExpressionAttributeValues={":uid": user_id},
    )
    all_items = sorted(
        [_decimal_to_float(item) for item in response.get("Items", [])],
        key=lambda x: x.get("created_at", ""),
        reverse=True,
    )
    total = len(all_items)
    start = (page - 1) * page_size
    items = all_items[start:start + page_size]
    return items, total
