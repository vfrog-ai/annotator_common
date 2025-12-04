"""
Event models for RabbitMQ message handling.
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Type of project events."""

    START_PROJECT_ITERATION = "start_project_iteration"
    DOWNLOAD_IMAGE = "download_image"
    IMAGE_DOWNLOADED = "image_downloaded"
    CUTOUT_EXTRACTION = "cutout_extraction"
    CUTOUTS_READY = "cutouts_ready"
    IMAGE_ANALYZED = "image_analyzed"  # Deprecated - use PRODUCT_IMAGE_ANALYZED or DATASET_IMAGE_ANALYZED
    PRODUCT_IMAGE_ANALYZED = "product_image_analyzed"
    DATASET_IMAGE_ANALYZED = "dataset_image_analyzed"
    ANALYZE_PRODUCT_IMAGE = "analyze_product_image"
    ANALYZE_DATASET_IMAGE = "analyze_dataset_image"
    ANNOTATION_CREATED = "annotation_created"
    ANNOTATE_DATASET = "annotate_dataset"
    PROJECT_COMPLETE = "project_complete"
    ERROR = "error"


class ProjectStatus(str, Enum):
    """Project status enumeration."""

    CREATED = "created"
    DOWNLOADING = "downloading"
    CUTOUT_EXTRACTION = "cutout_extraction"
    ANALYZING = "analyzing"
    QUALIFYING = "qualifying"
    ANNOTATING = "annotating"
    COMPLETED = "completed"
    FAILED = "failed"


class CallbackEventType(str, Enum):
    """Callback event types."""

    ANNOTATION_CREATED = "annotation_created"
    PROJECT_STATUS_CHANGED = "project_status_changed"
    PROJECT_PROGRESS_UPDATED = "project_progress_updated"


class ProjectEvent(BaseModel):
    """Base event model for all project events."""

    event_type: EventType
    project_iteration_id: str
    correlation_id: str  # Mandatory - must be provided in all events
    dataset_image_id: Optional[str] = None
    product_image_id: Optional[str] = None
    timestamp: float = Field(default_factory=lambda: __import__("time").time())
    data: Dict[str, Any] = Field(default_factory=dict)


class ImageDownloadedEvent(ProjectEvent):
    """Event for when an image has been downloaded."""

    image_path: str
    image_type: str  # 'dataset' or 'product'
    label: Optional[str] = None  # Only for product images


class CutoutsReadyEvent(ProjectEvent):
    """Event for when cutouts are ready."""

    cutout_count: int
    cutouts: List[Dict[str, Any]]  # List of cutout data with bbox information


class ImageAnalyzedEvent(ProjectEvent):
    """Event for when an image analysis is complete."""

    analysis_type: str  # 'initial' or 'detailed'
    analysis_result: Dict[str, Any]
    image_type: (
        str  # Deprecated - use ProductImageAnalyzedEvent or DatasetImageAnalyzedEvent
    )
    cutout_id: Optional[str] = None


class ProductImageAnalyzedEvent(ProjectEvent):
    """Event for when a product image analysis is complete."""

    analysis_type: str  # 'initial' or 'detailed'
    analysis_result: Dict[str, Any]


class DatasetImageAnalyzedEvent(ProjectEvent):
    """Event for when a dataset image (cutout) analysis is complete."""

    analysis_type: str  # 'initial' or 'detailed'
    analysis_result: Dict[str, Any]
    cutout_id: str


class AnnotationCreatedEvent(ProjectEvent):
    """Event for when an annotation is created."""

    annotated_image_path: str
    label: str
    dataset_image_id: str
    product_image_id: str


class ErrorEvent(ProjectEvent):
    """Event for when a blocking error occurs in a service."""

    error_message: str
    service_name: str
    error_type: Optional[str] = None  # Exception class name
