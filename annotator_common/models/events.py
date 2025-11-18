"""
Event models for RabbitMQ message handling.
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field


class EventType(str, Enum):
    """Type of project events."""

    PROJECT_CREATED = "project_created"
    IMAGE_DOWNLOADED = "image_downloaded"
    CUTOUTS_READY = "cutouts_ready"
    IMAGE_ANALYZED = "image_analyzed"
    ANNOTATION_CREATED = "annotation_created"
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
    image_type: str
    cutout_id: Optional[str] = None


class AnnotationCreatedEvent(ProjectEvent):
    """Event for when an annotation is created."""

    annotated_image_path: str
    label: str
    cutout_id: str
    product_image_id: str


class ErrorEvent(ProjectEvent):
    """Event for when a blocking error occurs in a service."""

    error_message: str
    service_name: str
    error_type: Optional[str] = None  # Exception class name

