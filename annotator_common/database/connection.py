"""
MongoDB connection management.
"""

import os
from typing import Optional
from urllib.parse import urlparse
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.write_concern import WriteConcern
from pymongo.read_concern import ReadConcern
from pymongo.read_preferences import ReadPreference
from annotator_common.config import Config


_client: Optional[MongoClient] = None
_database: Optional[Database] = None


def get_database() -> Database:
    """Get MongoDB database instance."""
    global _database

    if _database is None:
        init_database()

    return _database


def init_database() -> None:
    """Initialize MongoDB connection and create collections."""
    global _client, _database

    uri = Config.get_mongodb_uri()

    # Handle SSL certificate verification for MongoDB Atlas
    # In LOCAL_MODE, allow invalid certificates for testing
    local_mode = os.getenv("LOCAL_MODE", "false").lower() == "true"

    # Check if URI is a MongoDB Atlas connection (mongodb+srv://)
    is_atlas = uri.startswith("mongodb+srv://")

    if is_atlas and local_mode:
        # For local testing with Atlas, allow invalid certificates
        # This is safe for testing but should not be used in production
        from annotator_common.logging import log_warning

        log_warning(
            "LOCAL_MODE enabled: Allowing invalid SSL certificates for MongoDB Atlas connection. "
            "This should only be used for local testing.",
            correlation_id="",
        )
        # Add tlsAllowInvalidCertificates to the URI
        if "?" in uri:
            # URI already has query parameters
            if "tlsAllowInvalidCertificates" not in uri:
                uri += "&tlsAllowInvalidCertificates=true"
        else:
            # No query parameters yet
            uri += "?tlsAllowInvalidCertificates=true"

    # Configure MongoDB client with write and read concerns for consistency
    # Write Concern "majority" requires a replica set - will fail on standalone MongoDB
    # Make it opt-in via environment variable to avoid deployment failures
    use_strong_consistency = (
        os.getenv("MONGODB_STRONG_CONSISTENCY", "false").lower() == "true"
    )

    # Read preference configuration: controls which nodes handle read operations
    # Options: PRIMARY (default), PRIMARY_PREFERRED, SECONDARY, SECONDARY_PREFERRED, NEAREST
    # PRIMARY: Always read from primary (strongest consistency, ensures read-after-write consistency)
    # This is the default to prevent read-after-write consistency issues
    read_pref_mode = os.getenv("MONGODB_READ_PREFERENCE", "PRIMARY").upper()
    read_preference_map = {
        "PRIMARY": ReadPreference.PRIMARY,
        "PRIMARY_PREFERRED": ReadPreference.PRIMARY_PREFERRED,
        "SECONDARY": ReadPreference.SECONDARY,
        "SECONDARY_PREFERRED": ReadPreference.SECONDARY_PREFERRED,
        "NEAREST": ReadPreference.NEAREST,
    }
    read_preference = read_preference_map.get(read_pref_mode, ReadPreference.PRIMARY)

    if use_strong_consistency:
        from annotator_common.logging import log_info

        log_info(
            f"MONGODB_STRONG_CONSISTENCY enabled - using write/read concern 'majority' for replica sets, "
            f"read preference: {read_pref_mode}",
            correlation_id="",
        )
        # Write Concern "majority": Ensures write is acknowledged by majority of replica set members
        # This guarantees the write is durable and replicated before the operation returns
        # Read Concern "majority": Ensures reads only return data that has been acknowledged by majority
        # This provides read-after-write consistency when combined with write concern majority
        # Read Preference: Configurable via MONGODB_READ_PREFERENCE env var
        #   - PRIMARY (default): All reads go to primary (strongest consistency, ensures read-after-write consistency)
        #   - SECONDARY_PREFERRED: Distributes reads to secondaries, falls back to primary (load distribution)
        # wtimeout: Maximum time to wait for write concern acknowledgment (5 seconds)
        write_concern = WriteConcern(w="majority", wtimeout=5000)
        read_concern = ReadConcern(level="majority")

        _client = MongoClient(
            uri,
            write_concern=write_concern,
            read_concern=read_concern,
            read_preference=read_preference,
        )
    else:
        # Use default settings for standalone MongoDB or when not explicitly enabled
        # This ensures services can start even with standalone MongoDB instances
        # Still apply read_preference (defaults to PRIMARY for consistency)
        _client = MongoClient(uri, read_preference=read_preference)

    # Determine database name with priority:
    # 1. MONGODB_DATABASE environment variable (explicit override)
    # 2. Database name from MONGODB_URI path
    # 3. Config.MONGODB_DATABASE (default: "annotator")
    if "MONGODB_DATABASE" in os.environ:
        # Explicit database name override (highest priority)
        db_name = os.getenv("MONGODB_DATABASE")
        _database = _client[db_name]
    elif "MONGODB_URI" in os.environ:
        # Parse database name from URI
        from urllib.parse import urlparse

        parsed = urlparse(uri)
        # Get database from path (strip leading /)
        db_name = (
            parsed.path.lstrip("/").split("?")[0]
            if parsed.path
            else Config.MONGODB_DATABASE
        )
        if not db_name or db_name == "":
            db_name = Config.MONGODB_DATABASE
        _database = _client[db_name]
    else:
        # Use config database name (Docker Compose mode)
        _database = _client[Config.MONGODB_DATABASE]

    # Verify connection and authentication before creating indexes
    try:
        # Test the connection by running a simple command
        _client.admin.command("ping")
    except Exception as e:
        import logging

        logger = logging.getLogger(__name__)
        error_msg = str(e)
        if "Authentication failed" in error_msg or "bad auth" in error_msg.lower():
            log_error(
                "MongoDB authentication failed. Please check your MONGODB_URI credentials. "
                "Verify that the username and password are correct, and that special characters "
                "in the password are URL-encoded (e.g., @ becomes %40, # becomes %23).",
                correlation_id="",
                exc_info=True,
            )
        else:
            log_error(f"MongoDB connection failed: {e}", exc_info=True)
        # Don't raise - let the service start, but it will fail when trying to use the database
        # This allows the service to start and show a clear error message

    # Create collections with indexes (will fail gracefully if auth failed)
    _create_collections()


def _index_exists(collection, index_key):
    """Check if an index with the given key pattern exists.

    Args:
        collection: MongoDB collection object
        index_key: Index key pattern (can be string for single field or list of tuples for compound)

    Returns:
        bool: True if index exists, False otherwise
    """
    try:
        # Normalize index key to list of tuples for comparison
        if isinstance(index_key, str):
            # Single field index
            normalized_key = [(index_key, 1)]
        else:
            # Compound index - already a list of tuples
            normalized_key = (
                index_key if isinstance(index_key[0], tuple) else [(index_key, 1)]
            )

        # Get all existing indexes
        existing_indexes = list(collection.list_indexes())

        # Check if any index matches the key pattern
        for idx in existing_indexes:
            idx_key = idx.get("key", {})
            # Convert index key dict to list of tuples for comparison
            idx_key_list = [(k, v) for k, v in idx_key.items()]

            # Check if keys match (order matters for compound indexes)
            if idx_key_list == normalized_key:
                return True

        return False
    except Exception:
        # If we can't check, assume it doesn't exist and let create_index handle it
        return False


def _create_collections():
    """Create all required collections and indexes.

    Note: Indexes are created with background=True to avoid blocking.
    If the user doesn't have permission to create indexes, we'll log a warning
    and continue (indexes may already exist or will be created manually).
    """
    import logging

    logger = logging.getLogger(__name__)

    db = get_database()

    try:
        # Project iterations collection
        project_iterations = db.project_iterations
        try:
            if not _index_exists(project_iterations, "project_iteration_id"):
                project_iterations.create_index(
                    "project_iteration_id", unique=True, background=True
                )
            if not _index_exists(project_iterations, "status"):
                project_iterations.create_index("status", background=True)
            if not _index_exists(project_iterations, "created_at"):
                project_iterations.create_index("created_at", background=True)
        except Exception as e:
            log_warning(
                f"Could not create indexes for project_iterations collection: {e}"
            )

        # Product images collection
        product_images = db.product_images
        try:
            # Compound unique index: same product_image_id can exist in different projects
            if not _index_exists(
                product_images, [("product_image_id", 1), ("project_iteration_id", 1)]
            ):
                product_images.create_index(
                    [("product_image_id", 1), ("project_iteration_id", 1)],
                    unique=True,
                    background=True,
                )
            if not _index_exists(product_images, "project_iteration_id"):
                product_images.create_index("project_iteration_id", background=True)
        except Exception as e:
            log_warning(f"Could not create indexes for product_images collection: {e}")

        # Dataset images collection
        dataset_images = db.dataset_images
        try:
            # Compound unique index: same dataset_image_id can exist in different projects
            if not _index_exists(
                dataset_images, [("dataset_image_id", 1), ("project_iteration_id", 1)]
            ):
                dataset_images.create_index(
                    [("dataset_image_id", 1), ("project_iteration_id", 1)],
                    unique=True,
                    background=True,
                )
            if not _index_exists(dataset_images, "project_iteration_id"):
                dataset_images.create_index("project_iteration_id", background=True)
        except Exception as e:
            log_warning(f"Could not create indexes for dataset_images collection: {e}")

        # Cutouts collection
        cutouts = db.cutouts
        try:
            # Compound unique index: same cutout_id can exist in different projects
            if not _index_exists(
                cutouts, [("cutout_id", 1), ("project_iteration_id", 1)]
            ):
                cutouts.create_index(
                    [("cutout_id", 1), ("project_iteration_id", 1)],
                    unique=True,
                    background=True,
                )
            if not _index_exists(cutouts, "project_iteration_id"):
                cutouts.create_index("project_iteration_id", background=True)
            if not _index_exists(cutouts, "dataset_image_id"):
                cutouts.create_index("dataset_image_id", background=True)
            # Compound index for efficient querying by dataset_image_id and project_iteration_id
            if not _index_exists(
                cutouts, [("dataset_image_id", 1), ("project_iteration_id", 1)]
            ):
                cutouts.create_index(
                    [("dataset_image_id", 1), ("project_iteration_id", 1)],
                    background=True,
                )
        except Exception as e:
            log_warning(f"Could not create indexes for cutouts collection: {e}")

        # Cutout analysis collection
        cutout_analysis = db.cutout_analysis
        try:
            # Compound unique index: one analysis per cutout per project per analysis_type
            # This allows multiple analysis types (e.g., "initial", "detailed") per cutout
            # but prevents duplicate analyses of the same type for the same cutout
            if not _index_exists(
                cutout_analysis,
                [("cutout_id", 1), ("project_iteration_id", 1), ("analysis_type", 1)],
            ):
                cutout_analysis.create_index(
                    [
                        ("cutout_id", 1),
                        ("project_iteration_id", 1),
                        ("analysis_type", 1),
                    ],
                    unique=True,
                    background=True,
                )
            # Also keep index on cutout_analysis_id for lookups
            if not _index_exists(
                cutout_analysis,
                [("cutout_analysis_id", 1), ("project_iteration_id", 1)],
            ):
                cutout_analysis.create_index(
                    [("cutout_analysis_id", 1), ("project_iteration_id", 1)],
                    unique=True,
                    background=True,
                )
            if not _index_exists(cutout_analysis, "cutout_id"):
                cutout_analysis.create_index("cutout_id", background=True)
            if not _index_exists(cutout_analysis, "analysis_type"):
                cutout_analysis.create_index("analysis_type", background=True)
            if not _index_exists(cutout_analysis, "project_iteration_id"):
                cutout_analysis.create_index("project_iteration_id", background=True)
        except Exception as e:
            log_warning(f"Could not create indexes for cutout_analysis collection: {e}")

        # Annotations collection
        annotations = db.annotations
        try:
            # Compound unique index: one annotation per cutout per project
            if not _index_exists(
                annotations, [("cutout_id", 1), ("project_iteration_id", 1)]
            ):
                annotations.create_index(
                    [("cutout_id", 1), ("project_iteration_id", 1)],
                    unique=True,
                    background=True,
                )
            if not _index_exists(annotations, "project_iteration_id"):
                annotations.create_index("project_iteration_id", background=True)
            if not _index_exists(annotations, "cutout_id"):
                annotations.create_index("cutout_id", background=True)
            if not _index_exists(annotations, "product_image_id"):
                annotations.create_index("product_image_id", background=True)
            if not _index_exists(annotations, "annotation_id"):
                annotations.create_index("annotation_id", background=True)
            # Compound index for efficient querying by dataset_image_id and project_iteration_id
            if not _index_exists(
                annotations, [("dataset_image_id", 1), ("project_iteration_id", 1)]
            ):
                annotations.create_index(
                    [("dataset_image_id", 1), ("project_iteration_id", 1)],
                    background=True,
                )
        except Exception as e:
            log_warning(f"Could not create indexes for annotations collection: {e}")

        # Analysis config collection
        analysis_config = db.analysis_config
        try:
            if not _index_exists(analysis_config, "config_id"):
                analysis_config.create_index("config_id", unique=True, background=True)
            if not _index_exists(analysis_config, "active"):
                analysis_config.create_index("active", background=True)
        except Exception as e:
            log_warning(f"Could not create indexes for analysis_config collection: {e}")

        # Processed events collection - tracks idempotency for Pub/Sub messages
        processed_events = db.processed_events
        try:
            # Index for image_downloaded events (product)
            if not _index_exists(
                processed_events,
                [
                    ("event_type", 1),
                    ("project_iteration_id", 1),
                    ("image_type", 1),
                    ("product_image_id", 1),
                ],
            ):
                processed_events.create_index(
                    [
                        ("event_type", 1),
                        ("project_iteration_id", 1),
                        ("image_type", 1),
                        ("product_image_id", 1),
                    ],
                    unique=True,
                    partialFilterExpression={
                        "event_type": "image_downloaded",
                        "image_type": "product",
                    },
                    background=True,
                )
            # Index for image_downloaded events (dataset)
            if not _index_exists(
                processed_events,
                [
                    ("event_type", 1),
                    ("project_iteration_id", 1),
                    ("image_type", 1),
                    ("dataset_image_id", 1),
                ],
            ):
                processed_events.create_index(
                    [
                        ("event_type", 1),
                        ("project_iteration_id", 1),
                        ("image_type", 1),
                        ("dataset_image_id", 1),
                    ],
                    unique=True,
                    partialFilterExpression={
                        "event_type": "image_downloaded",
                        "image_type": "dataset",
                    },
                    background=True,
                )
            # Index for cutouts_ready events
            if not _index_exists(
                processed_events,
                [
                    ("event_type", 1),
                    ("project_iteration_id", 1),
                    ("dataset_image_id", 1),
                ],
            ):
                processed_events.create_index(
                    [
                        ("event_type", 1),
                        ("project_iteration_id", 1),
                        ("dataset_image_id", 1),
                    ],
                    unique=True,
                    partialFilterExpression={"event_type": "cutouts_ready"},
                    background=True,
                )
            # Index for image_analyzed events (product)
            if not _index_exists(
                processed_events,
                [
                    ("event_type", 1),
                    ("project_iteration_id", 1),
                    ("image_type", 1),
                    ("product_image_id", 1),
                    ("analysis_type", 1),
                ],
            ):
                processed_events.create_index(
                    [
                        ("event_type", 1),
                        ("project_iteration_id", 1),
                        ("image_type", 1),
                        ("product_image_id", 1),
                        ("analysis_type", 1),
                    ],
                    unique=True,
                    partialFilterExpression={
                        "event_type": "image_analyzed",
                        "image_type": "product",
                    },
                    background=True,
                )
            # Index for image_analyzed events (cutout)
            if not _index_exists(
                processed_events,
                [
                    ("event_type", 1),
                    ("project_iteration_id", 1),
                    ("image_type", 1),
                    ("cutout_id", 1),
                    ("analysis_type", 1),
                ],
            ):
                processed_events.create_index(
                    [
                        ("event_type", 1),
                        ("project_iteration_id", 1),
                        ("image_type", 1),
                        ("cutout_id", 1),
                        ("analysis_type", 1),
                    ],
                    unique=True,
                    partialFilterExpression={
                        "event_type": "image_analyzed",
                        "image_type": "cutout",
                    },
                    background=True,
                )
            # Index for annotation_created events
            if not _index_exists(
                processed_events,
                [
                    ("event_type", 1),
                    ("project_iteration_id", 1),
                    ("dataset_image_id", 1),
                ],
            ):
                processed_events.create_index(
                    [
                        ("event_type", 1),
                        ("project_iteration_id", 1),
                        ("dataset_image_id", 1),
                    ],
                    unique=True,
                    partialFilterExpression={"event_type": "annotation_created"},
                    background=True,
                )
            # Index for start_project_iteration events
            if not _index_exists(
                processed_events, [("event_type", 1), ("project_iteration_id", 1)]
            ):
                processed_events.create_index(
                    [
                        ("event_type", 1),
                        ("project_iteration_id", 1),
                    ],
                    unique=True,
                    partialFilterExpression={"event_type": "start_project_iteration"},
                    background=True,
                )
            # Index for annotate_dataset events
            if not _index_exists(
                processed_events,
                [
                    ("event_type", 1),
                    ("project_iteration_id", 1),
                    ("dataset_image_id", 1),
                ],
            ):
                processed_events.create_index(
                    [
                        ("event_type", 1),
                        ("project_iteration_id", 1),
                        ("dataset_image_id", 1),
                    ],
                    unique=True,
                    partialFilterExpression={"event_type": "annotate_dataset"},
                    background=True,
                )
            # Index for dataset_image_analyzed events (cutout analysis)
            if not _index_exists(
                processed_events,
                [
                    ("event_type", 1),
                    ("project_iteration_id", 1),
                    ("cutout_id", 1),
                    ("analysis_type", 1),
                ],
            ):
                processed_events.create_index(
                    [
                        ("event_type", 1),
                        ("project_iteration_id", 1),
                        ("cutout_id", 1),
                        ("analysis_type", 1),
                    ],
                    unique=True,
                    partialFilterExpression={"event_type": "dataset_image_analyzed"},
                    background=True,
                )
            # Index for product_image_analyzed events
            if not _index_exists(
                processed_events,
                [
                    ("event_type", 1),
                    ("project_iteration_id", 1),
                    ("product_image_id", 1),
                    ("analysis_type", 1),
                ],
            ):
                processed_events.create_index(
                    [
                        ("event_type", 1),
                        ("project_iteration_id", 1),
                        ("product_image_id", 1),
                        ("analysis_type", 1),
                    ],
                    unique=True,
                    partialFilterExpression={"event_type": "product_image_analyzed"},
                    background=True,
                )
            # General indexes for querying
            if not _index_exists(processed_events, "event_type"):
                processed_events.create_index("event_type", background=True)
            if not _index_exists(processed_events, "project_iteration_id"):
                processed_events.create_index("project_iteration_id", background=True)
            if not _index_exists(processed_events, "processed_at"):
                processed_events.create_index("processed_at", background=True)
            # Additional compound indexes for efficient querying
            if not _index_exists(
                processed_events,
                [
                    ("analysis_type", 1),
                    ("cutout_id", 1),
                    ("event_type", 1),
                    ("project_iteration_id", 1),
                ],
            ):
                processed_events.create_index(
                    [
                        ("analysis_type", 1),
                        ("cutout_id", 1),
                        ("event_type", 1),
                        ("project_iteration_id", 1),
                    ],
                    background=True,
                )
            if not _index_exists(
                processed_events,
                [
                    ("analysis_type", 1),
                    ("event_type", 1),
                    ("product_image_id", 1),
                    ("project_iteration_id", 1),
                ],
            ):
                processed_events.create_index(
                    [
                        ("analysis_type", 1),
                        ("event_type", 1),
                        ("product_image_id", 1),
                        ("project_iteration_id", 1),
                    ],
                    background=True,
                )
        except Exception as e:
            log_warning(
                f"Could not create indexes for processed_events collection: {e}"
            )

        # Modal billing collection - stores Modal.com billing/usage data
        modal_billing = db.modal_billing
        try:
            # Compound unique index: prevent duplicate entries for same date/function
            if not _index_exists(
                modal_billing, [("date", 1), ("function_name", 1), ("environment", 1)]
            ):
                modal_billing.create_index(
                    [("date", 1), ("function_name", 1), ("environment", 1)],
                    unique=True,
                    background=True,
                )
            # Indexes for efficient querying
            if not _index_exists(modal_billing, "date"):
                modal_billing.create_index("date", background=True)
            if not _index_exists(modal_billing, "environment"):
                modal_billing.create_index("environment", background=True)
            if not _index_exists(modal_billing, "function_name"):
                modal_billing.create_index("function_name", background=True)
            if not _index_exists(modal_billing, "created_at"):
                modal_billing.create_index("created_at", background=True)
        except Exception as e:
            log_warning(f"Could not create indexes for modal_billing collection: {e}")

        # Detections collection - stores detection results from inference
        detections = db.detections
        try:
            if not _index_exists(detections, "project_iteration_id"):
                detections.create_index("project_iteration_id", background=True)
            # Compound index for efficient querying by dataset_images_id and project_iteration_id
            if not _index_exists(
                detections, [("dataset_images_id", 1), ("project_iteration_id", 1)]
            ):
                detections.create_index(
                    [("dataset_images_id", 1), ("project_iteration_id", 1)],
                    background=True,
                )
        except Exception as e:
            log_warning(f"Could not create indexes for detections collection: {e}")

    except Exception as e:
        log_warning(
            f"Error creating collections/indexes: {e}. Indexes may already exist or need manual creation."
        )


def close_database():
    """Close MongoDB connection."""
    global _client
    if _client:
        _client.close()
        _client = None
