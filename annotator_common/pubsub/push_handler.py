"""
Utilities for handling Google Cloud Pub/Sub push subscription requests.
"""

import json
import base64
from typing import Dict, Any, Optional
from annotator_common.logging import get_logger

logger = get_logger(__name__)


def parse_pubsub_push_message(request_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Parse a Pub/Sub push subscription message from the request body.

    Supports two formats:
    1. Pub/Sub push format (from real Pub/Sub):
       {
           "message": {
               "data": "base64-encoded-json-string",
               "messageId": "message-id",
               "publishTime": "2023-01-01T00:00:00.000Z",
               "attributes": {...}
           },
           "subscription": "projects/.../subscriptions/..."
       }
    
    2. Direct format (from LOCAL_MODE HTTP calls):
       {
           "project_iteration_id": "...",
           "image_url": "...",
           ...
       }

    Args:
        request_data: The request body from Pub/Sub push or direct HTTP call

    Returns:
        Parsed message payload as dictionary

    Raises:
        ValueError: If message format is invalid
    """
    try:
        # Check if this is a direct message (LOCAL_MODE format)
        # Direct messages have business fields like project_iteration_id, image_url, etc.
        # Pub/Sub format has a "message" field with "data" inside
        if "message" not in request_data:
            # This is a direct message format (LOCAL_MODE)
            logger.debug("Received direct message format (LOCAL_MODE), using as-is")
            return request_data

        # This is Pub/Sub push format
        message = request_data.get("message", {})
        if not message:
            raise ValueError("Missing 'message' field in Pub/Sub push request")

        # Get base64-encoded data
        encoded_data = message.get("data")
        if not encoded_data:
            raise ValueError("Missing 'data' field in Pub/Sub message")

        # Decode base64
        try:
            decoded_bytes = base64.b64decode(encoded_data)
        except Exception as e:
            raise ValueError(f"Failed to decode base64 data: {e}")

        # Parse JSON
        try:
            payload = json.loads(decoded_bytes.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"Failed to parse JSON from message data: {e}")

        # Extract metadata
        message_id = message.get("messageId")
        publish_time = message.get("publishTime")
        attributes = message.get("attributes", {})

        logger.debug(
            f"Parsed Pub/Sub message: message_id={message_id}, "
            f"publish_time={publish_time}, attributes={attributes}"
        )

        return payload

    except Exception as e:
        logger.error(
            f"Error parsing Pub/Sub push message: {e}, request_data: {request_data}"
        )
        raise


def validate_pubsub_signature(
    request_body: bytes, signature: Optional[str] = None
) -> bool:
    """
    Validate Pub/Sub push request signature.

    Note: For production, you should validate the JWT token from the
    'Authorization' header. For now, we'll rely on Cloud Run IAM
    or allow unauthenticated access with proper security measures.

    Args:
        request_body: Raw request body bytes
        signature: Optional signature from headers (not used in basic implementation)

    Returns:
        True if validation passes (or skipped), False otherwise
    """
    # Basic implementation - in production, validate JWT token
    # For Cloud Run with IAM, Pub/Sub service account will have proper permissions
    # and requests will be authenticated via Google's infrastructure
    return True
