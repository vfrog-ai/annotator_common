"""
Firestore utility functions for document conversion and timestamp handling.
"""

from datetime import datetime
from typing import Any, Dict, Optional
from google.cloud.firestore import SERVER_TIMESTAMP


def to_firestore_timestamp(dt: Optional[datetime]) -> Any:
    """Convert Python datetime to Firestore Timestamp or SERVER_TIMESTAMP."""
    if dt is None:
        return SERVER_TIMESTAMP
    # Firestore client handles datetime conversion automatically
    return dt


def from_firestore_timestamp(timestamp: Any) -> Optional[datetime]:
    """Convert Firestore Timestamp to Python datetime."""
    if timestamp is None:
        return None
    # Check if it's a Firestore Timestamp (has to_datetime method)
    if hasattr(timestamp, 'to_datetime'):
        return timestamp.to_datetime()
    if isinstance(timestamp, datetime):
        return timestamp
    return None


def doc_to_dict(doc: Any, include_id: bool = True) -> Dict[str, Any]:
    """
    Convert Firestore document to dictionary.

    Args:
        doc: Firestore DocumentSnapshot
        include_id: Whether to include document ID in result

    Returns:
        Dictionary representation of document
    """
    if doc is None:
        return None

    data = doc.to_dict()
    if data is None:
        return None

    # Convert Firestore Timestamps to datetime
    for key, value in data.items():
        # Check if it's a Firestore Timestamp (has to_datetime method)
        if hasattr(value, 'to_datetime'):
            data[key] = value.to_datetime()
        elif isinstance(value, datetime):
            # Already datetime, keep as is
            pass

    if include_id:
        data["id"] = doc.id

    return data


def prepare_data_for_firestore(data: Dict[str, Any], use_server_timestamp: bool = True) -> Dict[str, Any]:
    """
    Prepare data dictionary for Firestore write operations.

    Args:
        data: Data dictionary
        use_server_timestamp: Whether to use SERVER_TIMESTAMP for timestamp fields

    Returns:
        Dictionary ready for Firestore write
    """
    prepared = data.copy()

    # Handle timestamp fields
    for key in ["created_at", "updated_at"]:
        if key in prepared:
            if use_server_timestamp and prepared[key] is None:
                prepared[key] = SERVER_TIMESTAMP
            elif isinstance(prepared[key], datetime):
                # Firestore handles datetime conversion
                pass

    return prepared

