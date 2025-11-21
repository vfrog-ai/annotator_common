"""
MongoDB connection management.
"""

import os
from typing import Optional
from urllib.parse import urlparse
from pymongo import MongoClient
from pymongo.database import Database
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
    _client = MongoClient(uri)

    # Determine database name with priority:
    # 1. MONGODB_DATABASE environment variable (explicit override)
    # 2. Database name from MONGODB_URI path
    # 3. Config.MONGODB_DATABASE (default: "annotation_system")
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

    # Create collections with indexes
    _create_collections()


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
            project_iterations.create_index(
                "project_iteration_id", unique=True, background=True
            )
            project_iterations.create_index("status", background=True)
            project_iterations.create_index("created_at", background=True)
        except Exception as e:
            logger.warning(
                f"Could not create indexes for project_iterations collection: {e}"
            )

        # Product images collection
        product_images = db.product_images
        try:
            # Compound unique index: same product_image_id can exist in different projects
            product_images.create_index(
                [("product_image_id", 1), ("project_iteration_id", 1)],
                unique=True,
                background=True,
            )
            product_images.create_index("project_iteration_id", background=True)
        except Exception as e:
            logger.warning(
                f"Could not create indexes for product_images collection: {e}"
            )

        # Dataset images collection
        dataset_images = db.dataset_images
        try:
            # Compound unique index: same dataset_image_id can exist in different projects
            dataset_images.create_index(
                [("dataset_image_id", 1), ("project_iteration_id", 1)],
                unique=True,
                background=True,
            )
            dataset_images.create_index("project_iteration_id", background=True)
        except Exception as e:
            logger.warning(
                f"Could not create indexes for dataset_images collection: {e}"
            )

        # Cutouts collection
        cutouts = db.cutouts
        try:
            # Compound unique index: same cutout_id can exist in different projects
            cutouts.create_index(
                [("cutout_id", 1), ("project_iteration_id", 1)],
                unique=True,
                background=True,
            )
            cutouts.create_index("project_iteration_id", background=True)
            cutouts.create_index("dataset_image_id", background=True)
        except Exception as e:
            logger.warning(f"Could not create indexes for cutouts collection: {e}")

        # Cutout analysis collection
        cutout_analysis = db.cutout_analysis
        try:
            # Compound unique index: one analysis per cutout per project per analysis_type
            # This allows multiple analysis types (e.g., "initial", "detailed") per cutout
            # but prevents duplicate analyses of the same type for the same cutout
            cutout_analysis.create_index(
                [("cutout_id", 1), ("project_iteration_id", 1), ("analysis_type", 1)],
                unique=True,
                background=True,
            )
            # Also keep index on cutout_analysis_id for lookups
            cutout_analysis.create_index(
                [("cutout_analysis_id", 1), ("project_iteration_id", 1)],
                unique=True,
                background=True,
            )
            cutout_analysis.create_index("cutout_id", background=True)
            cutout_analysis.create_index("analysis_type", background=True)
        except Exception as e:
            logger.warning(
                f"Could not create indexes for cutout_analysis collection: {e}"
            )

        # Annotations collection
        annotations = db.annotations
        try:
            # Compound unique index: one annotation per cutout per project
            annotations.create_index(
                [("cutout_id", 1), ("project_iteration_id", 1)],
                unique=True,
                background=True,
            )
            annotations.create_index("project_iteration_id", background=True)
            annotations.create_index("cutout_id", background=True)
            annotations.create_index("product_image_id", background=True)
            annotations.create_index("annotation_id", background=True)
        except Exception as e:
            logger.warning(f"Could not create indexes for annotations collection: {e}")

        # Analysis config collection
        analysis_config = db.analysis_config
        try:
            analysis_config.create_index("config_id", unique=True, background=True)
            analysis_config.create_index("active", background=True)
        except Exception as e:
            logger.warning(
                f"Could not create indexes for analysis_config collection: {e}"
            )

        # Processed events collection - tracks idempotency for Pub/Sub messages
        processed_events = db.processed_events
        try:
            # Index for image_downloaded events (product)
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
            # General indexes for querying
            processed_events.create_index("event_type", background=True)
            processed_events.create_index("project_iteration_id", background=True)
            processed_events.create_index("processed_at", background=True)
        except Exception as e:
            logger.warning(
                f"Could not create indexes for processed_events collection: {e}"
            )

    except Exception as e:
        logger.warning(
            f"Error creating collections/indexes: {e}. Indexes may already exist or need manual creation."
        )


def close_database():
    """Close MongoDB connection."""
    global _client
    if _client:
        _client.close()
        _client = None
