"""
Firestore repository implementations for all collections.

This module provides repository classes that abstract Firestore operations,
matching the MongoDB API patterns used in the codebase to minimize code changes.
"""

import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional
from google.cloud.firestore_v1 import Client as FirestoreClient
from google.cloud.firestore_v1 import Transaction
from google.cloud.firestore_v1 import SERVER_TIMESTAMP
from google.cloud.firestore_v1.base_query import FieldFilter

from annotator_common.firestore.connection import get_firestore_client
from annotator_common.firestore.utils import (
    doc_to_dict,
    prepare_data_for_firestore,
    from_firestore_timestamp,
)
from google.cloud.firestore_v1 import Increment as firestore_Increment
from google.cloud.firestore_v1 import ArrayUnion as firestore_ArrayUnion
from annotator_common.logging import get_logger, log_warning, log_error

logger = get_logger(__name__)


def _calculate_expires_at() -> datetime:
    """
    Calculate expiration timestamp for project_iteration documents.
    
    Returns:
        datetime: Expiration timestamp (90 days for production, 30 days for other environments)
    """
    environment = os.getenv("ENVIRONMENT", "dev").lower()
    if environment == "production" or environment == "prod":
        days = 90
    else:
        days = 30
    
    return datetime.utcnow() + timedelta(days=days)


class BaseRepository:
    """Base repository with common Firestore operations."""

    def __init__(self, client: Optional[FirestoreClient] = None):
        """Initialize repository with Firestore client."""
        self.client = client or get_firestore_client()

    def _collection(self, *path_segments: str):
        """Get collection reference for given path segments."""
        collection = self.client.collection(path_segments[0])
        for segment in path_segments[1:]:
            collection = collection.document(segment).collection(segment)
        return collection

    def _document(self, *path_segments: str):
        """Get document reference for given path segments."""
        if len(path_segments) % 2 == 0:
            # Even number: ends with collection name
            collection = self._collection(*path_segments[:-1])
            return collection.document(path_segments[-1])
        else:
            # Odd number: ends with document ID
            doc_ref = self.client.document(path_segments[0])
            for i in range(1, len(path_segments) - 1, 2):
                doc_ref = doc_ref.collection(path_segments[i]).document(
                    path_segments[i + 1]
                )
            if len(path_segments) > 1:
                doc_ref = doc_ref.collection(path_segments[-2]).document(
                    path_segments[-1]
                )
            return doc_ref


class ProjectIterationRepository(BaseRepository):
    """Repository for project_iterations collection."""

    def get_by_id(self, project_iteration_id: str) -> Optional[Dict[str, Any]]:
        """Get project iteration by ID."""
        try:
            doc_ref = self.client.collection("project_iterations").document(
                project_iteration_id
            )
            doc = doc_ref.get()
            if doc.exists:
                return doc_to_dict(doc)
            return None
        except Exception as e:
            log_error(f"Error getting project iteration {project_iteration_id}: {e}")
            raise

    def create(self, project_iteration_id: str, data: Dict[str, Any]) -> None:
        """Create a new project iteration document."""
        try:
            data["project_iteration_id"] = project_iteration_id
            # Set expires_at if not already provided
            if "expires_at" not in data:
                data["expires_at"] = _calculate_expires_at()
            data = prepare_data_for_firestore(data)
            doc_ref = self.client.collection("project_iterations").document(
                project_iteration_id
            )
            doc_ref.set(data)
            logger.debug(f"Created project iteration: {project_iteration_id}")
        except Exception as e:
            log_error(f"Error creating project iteration {project_iteration_id}: {e}")
            raise

    def update(
        self,
        project_iteration_id: str,
        updates: Dict[str, Any],
        transaction: Optional[Transaction] = None,
    ) -> None:
        """Update project iteration document."""
        try:
            updates = prepare_data_for_firestore(updates, use_server_timestamp=False)
            if "updated_at" not in updates:
                updates["updated_at"] = SERVER_TIMESTAMP

            doc_ref = self.client.collection("project_iterations").document(
                project_iteration_id
            )
            if transaction:
                transaction.update(doc_ref, updates)
            else:
                doc_ref.update(updates)
            logger.debug(f"Updated project iteration: {project_iteration_id}")
        except Exception as e:
            log_error(f"Error updating project iteration {project_iteration_id}: {e}")
            raise

    def increment_fields(
        self,
        project_iteration_id: str,
        increments: Dict[str, int],
        transaction: Optional[Transaction] = None,
    ) -> None:
        """Increment numeric fields (replaces MongoDB $inc)."""
        try:
            updates = {}
            for field, value in increments.items():
                updates[field] = firestore_Increment(value)
            updates["updated_at"] = SERVER_TIMESTAMP

            doc_ref = self.client.collection("project_iterations").document(
                project_iteration_id
            )
            if transaction:
                transaction.update(doc_ref, updates)
            else:
                doc_ref.update(updates)
        except Exception as e:
            log_error(
                f"Error incrementing fields for project iteration {project_iteration_id}: {e}"
            )
            raise


class DatasetImageRepository(BaseRepository):
    """Repository for dataset_images subcollection."""

    def get_by_id(
        self, project_iteration_id: str, dataset_image_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get dataset image by ID."""
        try:
            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("dataset_images")
                .document(dataset_image_id)
            )
            doc = doc_ref.get()
            if doc.exists:
                return doc_to_dict(doc)
            return None
        except Exception as e:
            log_error(f"Error getting dataset image {dataset_image_id}: {e}")
            raise

    def list_by_project_iteration(
        self, project_iteration_id: str
    ) -> List[Dict[str, Any]]:
        """List all dataset images for a project iteration."""
        try:
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("dataset_images")
            )
            docs = collection_ref.stream()
            return [doc_to_dict(doc) for doc in docs]
        except Exception as e:
            log_error(
                f"Error listing dataset images for project {project_iteration_id}: {e}"
            )
            raise

    def create(
        self, project_iteration_id: str, dataset_image_id: str, data: Dict[str, Any]
    ) -> None:
        """Create a new dataset image document."""
        try:
            data["dataset_image_id"] = dataset_image_id
            data["project_iteration_id"] = project_iteration_id
            data = prepare_data_for_firestore(data)
            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("dataset_images")
                .document(dataset_image_id)
            )
            doc_ref.set(data)
            logger.debug(f"Created dataset image: {dataset_image_id}")
        except Exception as e:
            log_error(f"Error creating dataset image {dataset_image_id}: {e}")
            raise

    def update(
        self,
        project_iteration_id: str,
        dataset_image_id: str,
        updates: Dict[str, Any],
        transaction: Optional[Transaction] = None,
    ) -> None:
        """Update dataset image document."""
        try:
            updates = prepare_data_for_firestore(updates, use_server_timestamp=False)
            if "updated_at" not in updates:
                updates["updated_at"] = SERVER_TIMESTAMP

            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("dataset_images")
                .document(dataset_image_id)
            )
            if transaction:
                transaction.update(doc_ref, updates)
            else:
                doc_ref.update(updates)
            logger.debug(f"Updated dataset image: {dataset_image_id}")
        except Exception as e:
            log_error(f"Error updating dataset image {dataset_image_id}: {e}")
            raise

    def delete_by_project_iteration(self, project_iteration_id: str) -> int:
        """Delete all dataset images for a project iteration."""
        try:
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("dataset_images")
            )
            deleted_count = 0
            for doc in collection_ref.stream():
                doc.reference.delete()
                deleted_count += 1
            logger.debug(
                f"Deleted {deleted_count} dataset images for project {project_iteration_id}"
            )
            return deleted_count
        except Exception as e:
            log_error(
                f"Error deleting dataset images for project {project_iteration_id}: {e}"
            )
            raise


class ProductImageRepository(BaseRepository):
    """Repository for product_images subcollection."""

    def get_by_id(
        self, project_iteration_id: str, product_image_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get product image by ID."""
        try:
            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("product_images")
                .document(product_image_id)
            )
            doc = doc_ref.get()
            if doc.exists:
                return doc_to_dict(doc)
            return None
        except Exception as e:
            log_error(f"Error getting product image {product_image_id}: {e}")
            raise

    def list_by_project_iteration(
        self, project_iteration_id: str
    ) -> List[Dict[str, Any]]:
        """List all product images for a project iteration."""
        try:
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("product_images")
            )
            docs = collection_ref.stream()
            return [doc_to_dict(doc) for doc in docs]
        except Exception as e:
            log_error(
                f"Error listing product images for project {project_iteration_id}: {e}"
            )
            raise

    def create(
        self, project_iteration_id: str, product_image_id: str, data: Dict[str, Any]
    ) -> None:
        """Create a new product image document."""
        try:
            data["product_image_id"] = product_image_id
            data["project_iteration_id"] = project_iteration_id
            data = prepare_data_for_firestore(data)
            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("product_images")
                .document(product_image_id)
            )
            doc_ref.set(data)
            logger.debug(f"Created product image: {product_image_id}")
        except Exception as e:
            log_error(f"Error creating product image {product_image_id}: {e}")
            raise

    def update(
        self,
        project_iteration_id: str,
        product_image_id: str,
        updates: Dict[str, Any],
        transaction: Optional[Transaction] = None,
    ) -> None:
        """Update product image document."""
        try:
            updates = prepare_data_for_firestore(updates, use_server_timestamp=False)
            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("product_images")
                .document(product_image_id)
            )
            if transaction:
                transaction.update(doc_ref, updates)
            else:
                doc_ref.update(updates)
            logger.debug(f"Updated product image: {product_image_id}")
        except Exception as e:
            log_error(f"Error updating product image {product_image_id}: {e}")
            raise

    def delete_by_project_iteration(self, project_iteration_id: str) -> int:
        """Delete all product images for a project iteration."""
        try:
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("product_images")
            )
            deleted_count = 0
            for doc in collection_ref.stream():
                doc.reference.delete()
                deleted_count += 1
            logger.debug(
                f"Deleted {deleted_count} product images for project {project_iteration_id}"
            )
            return deleted_count
        except Exception as e:
            log_error(
                f"Error deleting product images for project {project_iteration_id}: {e}"
            )
            raise


class CutoutRepository(BaseRepository):
    """Repository for cutouts subcollection."""

    def get_by_id(
        self, project_iteration_id: str, cutout_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get cutout by ID."""
        try:
            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("cutouts")
                .document(cutout_id)
            )
            doc = doc_ref.get()
            if doc.exists:
                return doc_to_dict(doc)
            return None
        except Exception as e:
            log_error(f"Error getting cutout {cutout_id}: {e}")
            raise

    def list_by_dataset_image(
        self, project_iteration_id: str, dataset_image_id: str
    ) -> List[Dict[str, Any]]:
        """List all cutouts for a dataset image."""
        try:
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("cutouts")
            )
            query = collection_ref.where(
                filter=FieldFilter("dataset_image_id", "==", dataset_image_id)
            )
            docs = query.stream()
            return [doc_to_dict(doc) for doc in docs]
        except Exception as e:
            log_error(f"Error listing cutouts for dataset {dataset_image_id}: {e}")
            raise

    def count_by_dataset_image(
        self, project_iteration_id: str, dataset_image_id: str
    ) -> int:
        """Count cutouts for a dataset image."""
        try:
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("cutouts")
            )
            query = collection_ref.where(
                filter=FieldFilter("dataset_image_id", "==", dataset_image_id)
            )
            return len(list(query.stream()))
        except Exception as e:
            log_error(f"Error counting cutouts for dataset {dataset_image_id}: {e}")
            raise

    def create(
        self, project_iteration_id: str, cutout_id: str, data: Dict[str, Any]
    ) -> None:
        """Create a new cutout document."""
        try:
            data["cutout_id"] = cutout_id
            data["project_iteration_id"] = project_iteration_id
            data = prepare_data_for_firestore(data)
            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("cutouts")
                .document(cutout_id)
            )
            doc_ref.set(data)
            logger.debug(f"Created cutout: {cutout_id}")
        except Exception as e:
            log_error(f"Error creating cutout {cutout_id}: {e}")
            raise

    def update(
        self,
        project_iteration_id: str,
        cutout_id: str,
        updates: Dict[str, Any],
        transaction: Optional[Transaction] = None,
    ) -> None:
        """Update cutout document."""
        try:
            updates = prepare_data_for_firestore(updates, use_server_timestamp=False)
            if "updated_at" not in updates:
                updates["updated_at"] = SERVER_TIMESTAMP

            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("cutouts")
                .document(cutout_id)
            )
            if transaction:
                transaction.update(doc_ref, updates)
            else:
                doc_ref.update(updates)
            logger.debug(f"Updated cutout: {cutout_id}")
        except Exception as e:
            log_error(f"Error updating cutout {cutout_id}: {e}")
            raise

    def add_to_set(
        self,
        project_iteration_id: str,
        cutout_id: str,
        field: str,
        value: Any,
        transaction: Optional[Transaction] = None,
    ) -> None:
        """
        Add a value to an array field, avoiding duplicates (Firestore ArrayUnion).

        This mirrors MongoDB's $addToSet semantics.
        """
        try:
            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("cutouts")
                .document(cutout_id)
            )
            updates = {
                field: firestore_ArrayUnion([value]),
                "updated_at": SERVER_TIMESTAMP,
            }
            if transaction:
                transaction.update(doc_ref, updates)
            else:
                doc_ref.update(updates)
            logger.debug(f"Added to set field '{field}' for cutout: {cutout_id}")
        except Exception as e:
            log_error(f"Error adding to set for cutout {cutout_id} field {field}: {e}")
            raise

    def update_many(
        self,
        project_iteration_id: str,
        filter_dict: Dict[str, Any],
        updates: Dict[str, Any],
    ) -> int:
        """Update multiple cutouts matching filter (replaces MongoDB update_many)."""
        try:
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("cutouts")
            )
            query = collection_ref
            for field, value in filter_dict.items():
                if isinstance(value, dict) and "$in" in value:
                    # Handle MongoDB $in operator: {"field": {"$in": [val1, val2]}}
                    query = query.where(filter=FieldFilter(field, "in", value["$in"]))
                elif isinstance(value, list):
                    # Handle direct list (Firestore "in" operator)
                    query = query.where(filter=FieldFilter(field, "in", value))
                else:
                    query = query.where(filter=FieldFilter(field, "==", value))

            # Handle array operations ($addToSet, $pull)
            firestore_updates = {}
            for field, value in updates.items():
                if isinstance(value, dict):
                    # Handle MongoDB-style operators
                    if "$addToSet" in value:
                        # Firestore doesn't have $addToSet, need to read-modify-write
                        continue  # Handle separately below
                    elif "$pull" in value:
                        # Firestore doesn't have $pull, need to read-modify-write
                        continue  # Handle separately below
                    else:
                        firestore_updates[field] = value
                else:
                    firestore_updates[field] = value

            firestore_updates = prepare_data_for_firestore(
                firestore_updates, use_server_timestamp=False
            )
            if "updated_at" not in firestore_updates:
                firestore_updates["updated_at"] = SERVER_TIMESTAMP

            updated_count = 0
            for doc in query.stream():
                doc_data = doc.to_dict()
                doc_updates = firestore_updates.copy()

                # Handle $addToSet
                for field, value in updates.items():
                    if isinstance(value, dict) and "$addToSet" in value:
                        current_array = doc_data.get(field, [])
                        if not isinstance(current_array, list):
                            current_array = []
                        add_value = value["$addToSet"]
                        if add_value not in current_array:
                            current_array = current_array + [add_value]
                            doc_updates[field] = current_array

                # Handle $pull
                for field, value in updates.items():
                    if isinstance(value, dict) and "$pull" in value:
                        current_array = doc_data.get(field, [])
                        if isinstance(current_array, list):
                            pull_value = value["$pull"]
                            current_array = [
                                v for v in current_array if v != pull_value
                            ]
                            doc_updates[field] = current_array

                doc.reference.update(doc_updates)
                updated_count += 1

            logger.debug(f"Updated {updated_count} cutouts")
            return updated_count
        except Exception as e:
            log_error(f"Error updating cutouts: {e}")
            raise

    def delete_by_project_iteration(self, project_iteration_id: str) -> int:
        """Delete all cutouts for a project iteration."""
        try:
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("cutouts")
            )
            deleted_count = 0
            for doc in collection_ref.stream():
                doc.reference.delete()
                deleted_count += 1
            logger.debug(
                f"Deleted {deleted_count} cutouts for project {project_iteration_id}"
            )
            return deleted_count
        except Exception as e:
            log_error(f"Error deleting cutouts for project {project_iteration_id}: {e}")
            raise


class CutoutAnalysisRepository(BaseRepository):
    """Repository for cutout_analyses subcollection."""

    def get_by_id(
        self, project_iteration_id: str, cutout_id: str, analysis_type: str
    ) -> Optional[Dict[str, Any]]:
        """Get cutout analysis by cutout ID and analysis type."""
        try:
            doc_id = f"{cutout_id}__{analysis_type}"
            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("cutout_analyses")
                .document(doc_id)
            )
            doc = doc_ref.get()
            if doc.exists:
                return doc_to_dict(doc)
            return None
        except Exception as e:
            log_error(f"Error getting cutout analysis {cutout_id}/{analysis_type}: {e}")
            raise

    def count_by_dataset_image(
        self, project_iteration_id: str, dataset_image_id: str, analysis_type: str
    ) -> int:
        """Count cutout analyses for a dataset image and analysis type."""
        try:
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("cutout_analyses")
            )
            query = collection_ref.where(
                filter=FieldFilter("dataset_image_id", "==", dataset_image_id)
            ).where(filter=FieldFilter("analysis_type", "==", analysis_type))
            return len(list(query.stream()))
        except Exception as e:
            log_error(
                f"Error counting cutout analyses for dataset {dataset_image_id}: {e}"
            )
            raise

    def create_or_update(
        self,
        project_iteration_id: str,
        cutout_id: str,
        analysis_type: str,
        data: Dict[str, Any],
    ) -> None:
        """Create or update cutout analysis (replaces MongoDB upsert)."""
        try:
            doc_id = f"{cutout_id}__{analysis_type}"
            data["cutout_id"] = cutout_id
            data["analysis_type"] = analysis_type
            data["project_iteration_id"] = project_iteration_id
            data = prepare_data_for_firestore(data)
            if "updated_at" not in data or data["updated_at"] is None:
                data["updated_at"] = SERVER_TIMESTAMP

            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("cutout_analyses")
                .document(doc_id)
            )
            # Use merge=True for upsert behavior
            doc_ref.set(data, merge=True)
            logger.debug(f"Created/updated cutout analysis: {doc_id}")
        except Exception as e:
            log_error(
                f"Error creating/updating cutout analysis {cutout_id}/{analysis_type}: {e}"
            )
            raise

    def delete_by_project_iteration(self, project_iteration_id: str) -> int:
        """Delete all cutout analyses for a project iteration."""
        try:
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("cutout_analyses")
            )
            deleted_count = 0
            for doc in collection_ref.stream():
                doc.reference.delete()
                deleted_count += 1
            logger.debug(
                f"Deleted {deleted_count} cutout analyses for project {project_iteration_id}"
            )
            return deleted_count
        except Exception as e:
            log_error(
                f"Error deleting cutout analyses for project {project_iteration_id}: {e}"
            )
            raise


class ProcessedEventRepository(BaseRepository):
    """Repository for processed_events subcollection (idempotency tracking)."""

    def _get_event_doc_id(self, event_type: str, event_data: Dict[str, Any]) -> str:
        """Generate deterministic document ID for processed event."""
        project_iteration_id = event_data.get("project_iteration_id", "")

        if event_type == "image_downloaded":
            image_type = event_data.get("image_type")
            if image_type == "product":
                product_image_id = event_data.get("product_image_id", "")
                return f"image_downloaded__product__{product_image_id}"
            elif image_type == "dataset":
                dataset_image_id = event_data.get("dataset_image_id", "")
                return f"image_downloaded__dataset__{dataset_image_id}"
        elif event_type == "cutouts_ready":
            dataset_image_id = event_data.get("dataset_image_id", "")
            return f"cutouts_ready__{dataset_image_id}"
        elif event_type == "product_image_analyzed":
            product_image_id = event_data.get("product_image_id", "")
            analysis_type = event_data.get("analysis_type", "")
            return f"product_image_analyzed__{product_image_id}__{analysis_type}"
        elif event_type == "dataset_image_analyzed":
            cutout_id = event_data.get("cutout_id", "")
            analysis_type = event_data.get("analysis_type", "")
            return f"dataset_image_analyzed__{cutout_id}__{analysis_type}"
        elif event_type == "annotation_created":
            dataset_image_id = event_data.get("dataset_image_id", "")
            return f"annotation_created__{dataset_image_id}"
        elif event_type == "start_project_iteration":
            return f"start_project_iteration__{project_iteration_id}"
        elif event_type == "annotate_dataset":
            dataset_image_id = event_data.get("dataset_image_id", "")
            return f"annotate_dataset__{dataset_image_id}"

        # Fallback: use event_type + project_iteration_id
        return f"{event_type}__{project_iteration_id}"

    def is_processed(self, event_type: str, event_data: Dict[str, Any]) -> bool:
        """Check if event has already been processed (read-only)."""
        try:
            doc_id = self._get_event_doc_id(event_type, event_data)
            project_iteration_id = event_data.get("project_iteration_id")
            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("processed_events")
                .document(doc_id)
            )
            doc = doc_ref.get()
            return doc.exists
        except Exception as e:
            log_error(f"Error checking if event is processed: {e}")
            return False

    def mark_processed(
        self,
        event_type: str,
        event_data: Dict[str, Any],
        transaction: Optional[Transaction] = None,
    ) -> bool:
        """
        Mark event as processed (idempotent).

        Returns:
            True if event was already processed, False if newly marked
        """
        try:
            doc_id = self._get_event_doc_id(event_type, event_data)
            project_iteration_id = event_data.get("project_iteration_id")

            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("processed_events")
                .document(doc_id)
            )

            # Check if already exists
            doc = doc_ref.get()
            if doc.exists:
                return True

            # Create new event record
            event_doc = {
                "event_type": event_type,
                "project_iteration_id": project_iteration_id,
                "correlation_id": event_data.get("correlation_id", ""),
                "processed_at": SERVER_TIMESTAMP,
                "created_at": SERVER_TIMESTAMP,
            }
            # Add event-specific fields
            for key in [
                "image_type",
                "product_image_id",
                "dataset_image_id",
                "cutout_id",
                "analysis_type",
                "label",
            ]:
                if key in event_data:
                    event_doc[key] = event_data[key]

            if transaction:
                transaction.set(doc_ref, event_doc)
            else:
                doc_ref.set(event_doc)
            return False
        except Exception as e:
            log_error(f"Error marking event as processed: {e}")
            raise

    def delete_by_project_iteration(self, project_iteration_id: str) -> int:
        """Delete all processed events for a project iteration."""
        try:
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("processed_events")
            )
            deleted_count = 0
            for doc in collection_ref.stream():
                doc.reference.delete()
                deleted_count += 1
            logger.debug(
                f"Deleted {deleted_count} processed events for project {project_iteration_id}"
            )
            return deleted_count
        except Exception as e:
            log_error(
                f"Error deleting processed events for project {project_iteration_id}: {e}"
            )
            raise


class AnnotatedImageRepository(BaseRepository):
    """Repository for annotated_images subcollection and nested cutouts."""

    def get_summary(
        self, project_iteration_id: str, dataset_image_id: str
    ) -> Optional[Dict[str, Any]]:
        """Get annotated image summary document."""
        try:
            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("annotated_images")
                .document(dataset_image_id)
            )
            doc = doc_ref.get()
            if doc.exists:
                return doc_to_dict(doc)
            return None
        except Exception as e:
            log_error(f"Error getting annotated image summary {dataset_image_id}: {e}")
            raise

    def list_annotations(
        self, project_iteration_id: str, dataset_image_id: str
    ) -> List[Dict[str, Any]]:
        """List all annotation items (cutouts) for an annotated image."""
        try:
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("annotated_images")
                .document(dataset_image_id)
                .collection("cutouts")
            )
            docs = collection_ref.stream()
            return [doc_to_dict(doc) for doc in docs]
        except Exception as e:
            log_error(f"Error listing annotations for dataset {dataset_image_id}: {e}")
            raise

    def count_annotations(
        self, project_iteration_id: str, dataset_image_id: str
    ) -> int:
        """Count annotation items for an annotated image."""
        try:
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("annotated_images")
                .document(dataset_image_id)
                .collection("cutouts")
            )
            return len(list(collection_ref.stream()))
        except Exception as e:
            log_error(f"Error counting annotations for dataset {dataset_image_id}: {e}")
            raise

    def get_distinct_cutout_ids(
        self, project_iteration_id: str, dataset_image_id: str
    ) -> List[str]:
        """Get distinct cutout IDs (replaces MongoDB distinct)."""
        try:
            # Firestore doesn't have distinct, so we query and de-duplicate
            annotations = self.list_annotations(project_iteration_id, dataset_image_id)
            cutout_ids = [
                ann.get("cutout_id") for ann in annotations if ann.get("cutout_id")
            ]
            return list(set(cutout_ids))
        except Exception as e:
            log_error(
                f"Error getting distinct cutout IDs for dataset {dataset_image_id}: {e}"
            )
            raise

    def create_or_update_annotation(
        self,
        project_iteration_id: str,
        dataset_image_id: str,
        cutout_id: str,
        data: Dict[str, Any],
    ) -> None:
        """Create or update annotation item (replaces MongoDB bulk_write with upsert)."""
        try:
            data["cutout_id"] = cutout_id
            data["project_iteration_id"] = project_iteration_id
            data["dataset_image_id"] = dataset_image_id
            data = prepare_data_for_firestore(data)
            if "updated_at" not in data or data["updated_at"] is None:
                data["updated_at"] = SERVER_TIMESTAMP

            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("annotated_images")
                .document(dataset_image_id)
                .collection("cutouts")
                .document(cutout_id)
            )
            doc_ref.set(data, merge=True)
            logger.debug(f"Created/updated annotation: {dataset_image_id}/{cutout_id}")
        except Exception as e:
            log_error(
                f"Error creating/updating annotation {dataset_image_id}/{cutout_id}: {e}"
            )
            raise

    def bulk_write_annotations(
        self,
        project_iteration_id: str,
        dataset_image_id: str,
        annotations: List[Dict[str, Any]],
    ) -> None:
        """Bulk write annotations (replaces MongoDB bulk_write)."""
        try:
            batch = self.client.batch()
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("annotated_images")
                .document(dataset_image_id)
                .collection("cutouts")
            )

            for annotation in annotations:
                cutout_id = annotation.get("cutout_id")
                if not cutout_id:
                    log_warning(f"Skipping annotation without cutout_id: {annotation}")
                    continue

                annotation["project_iteration_id"] = project_iteration_id
                annotation["dataset_image_id"] = dataset_image_id
                annotation = prepare_data_for_firestore(annotation)
                if "updated_at" not in annotation or annotation["updated_at"] is None:
                    annotation["updated_at"] = SERVER_TIMESTAMP

                doc_ref = collection_ref.document(cutout_id)
                batch.set(doc_ref, annotation, merge=True)

            batch.commit()
            logger.debug(
                f"Bulk wrote {len(annotations)} annotations for dataset {dataset_image_id}"
            )
        except Exception as e:
            log_error(
                f"Error bulk writing annotations for dataset {dataset_image_id}: {e}"
            )
            raise

    def update_summary(
        self,
        project_iteration_id: str,
        dataset_image_id: str,
        updates: Dict[str, Any],
        transaction: Optional[Transaction] = None,
    ) -> None:
        """Update annotated image summary document."""
        try:
            updates = prepare_data_for_firestore(updates, use_server_timestamp=False)
            if "updated_at" not in updates:
                updates["updated_at"] = SERVER_TIMESTAMP

            doc_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("annotated_images")
                .document(dataset_image_id)
            )
            if transaction:
                transaction.update(doc_ref, updates)
            else:
                doc_ref.set(updates, merge=True)
            logger.debug(f"Updated annotated image summary: {dataset_image_id}")
        except Exception as e:
            log_error(f"Error updating annotated image summary {dataset_image_id}: {e}")
            raise

    def delete_by_project_iteration(self, project_iteration_id: str) -> int:
        """Delete all annotated images for a project iteration."""
        try:
            collection_ref = (
                self.client.collection("project_iterations")
                .document(project_iteration_id)
                .collection("annotated_images")
            )
            deleted_count = 0
            for summary_doc in collection_ref.stream():
                # Delete nested cutouts
                cutouts_ref = summary_doc.reference.collection("cutouts")
                for cutout_doc in cutouts_ref.stream():
                    cutout_doc.reference.delete()
                # Delete summary
                summary_doc.reference.delete()
                deleted_count += 1
            logger.debug(
                f"Deleted {deleted_count} annotated images for project {project_iteration_id}"
            )
            return deleted_count
        except Exception as e:
            log_error(
                f"Error deleting annotated images for project {project_iteration_id}: {e}"
            )
            raise
