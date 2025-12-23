"""
Firestore connection management.
"""

import os
from typing import Optional
from google.cloud import firestore
from google.cloud.firestore_v1 import Client as FirestoreClient
from annotator_common.config import Config
from annotator_common.logging import get_logger, log_info, log_warning, log_error

logger = get_logger(__name__)

_client: Optional[FirestoreClient] = None


def init_firestore() -> None:
    """Initialize Firestore client connection."""
    global _client

    if _client is not None:
        return

    project_id = Config.GOOGLE_CLOUD_PROJECT
    emulator_host = Config.FIRESTORE_EMULATOR_HOST

    # Check if emulator is configured (local/CI mode)
    if emulator_host:
        log_info(f"Initializing Firestore Emulator connection: {emulator_host}")
        os.environ["FIRESTORE_EMULATOR_HOST"] = emulator_host
        # Emulator doesn't require credentials
        _client = firestore.Client(project=project_id)
        log_info(f"Firestore Emulator connected to project: {project_id}")
    else:
        # Production mode: use Application Default Credentials (ADC)
        # Cloud Run service account will be used automatically
        log_info(f"Initializing Firestore managed connection for project: {project_id}")
        try:
            _client = firestore.Client(project=project_id)
            log_info(
                f"Firestore client initialized successfully for project: {project_id}"
            )
        except Exception as e:
            log_error(f"Failed to initialize Firestore client: {e}")
            raise

    # Verify connection
    try:
        # Try a simple read operation to verify connection
        _client.collection("_health_check").limit(1).stream()
        log_info("Firestore connection verified")
    except Exception as e:
        log_warning(
            f"Firestore connection verification failed (may be expected in emulator): {e}"
        )


def get_firestore_client() -> FirestoreClient:
    """Get Firestore client instance."""
    global _client

    if _client is None:
        init_firestore()

    return _client


def close_firestore() -> None:
    """Close Firestore connection."""
    global _client
    # Firestore client doesn't have an explicit close method,
    # but we can reset the reference
    _client = None
    log_info("Firestore client reference reset")
