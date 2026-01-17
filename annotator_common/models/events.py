"""
Event models for RabbitMQ message handling.
"""

from enum import Enum
from typing import Optional, Dict, Any, List, Literal
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
    ZERO_SHOT_DETECTION = "zero_shot_detection"
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
    # Analysis can be large; some services intentionally omit it and store it in MongoDB instead.
    analysis_result: Optional[Dict[str, Any]] = None
    image_type: (
        str  # Deprecated - use ProductImageAnalyzedEvent or DatasetImageAnalyzedEvent
    )
    cutout_id: Optional[str] = None


class ProductImageAnalyzedEvent(ProjectEvent):
    """Event for when a product image analysis is complete."""

    analysis_type: str  # 'initial' or 'detailed'
    # Analysis can be large; some services intentionally omit it and store it in MongoDB instead.
    analysis_result: Optional[Dict[str, Any]] = None


class DatasetImageAnalyzedEvent(ProjectEvent):
    """Event for when a dataset image (cutout) analysis is complete."""

    analysis_type: str  # 'initial' or 'detailed'
    # Analysis can be large; some services intentionally omit it and store it in MongoDB instead.
    analysis_result: Optional[Dict[str, Any]] = None
    cutout_id: str


class AnnotationCreatedEvent(ProjectEvent):
    """Event for when an annotation is created."""

    label: str
    dataset_image_id: str
    product_image_id: str


class ErrorEvent(ProjectEvent):
    """Event for when a blocking error occurs in a service."""

    error_message: str
    service_name: str
    error_type: Optional[str] = None  # Exception class name


# ============================================================================
# Strongly-typed command/request events (published to worker topics)
# ============================================================================


class ImageInput(BaseModel):
    """Minimal image input used by START_PROJECT_ITERATION."""

    id: str
    image_url: str
    label: Optional[str] = None  # only for product images


class StartProjectIterationEvent(ProjectEvent):
    """Command: kick off a project iteration (published by API service)."""

    callback_url: Optional[str] = None
    callback_cost_url: Optional[str] = None  # URL for cost tracking callbacks
    organisation_id: Optional[str] = None  # Organisation ID for cost tracking
    industry: Optional[str] = (
        None  # Industry/use case from control analysis (e.g., "Retail", "Agriculture")
    )
    product_image: ImageInput
    dataset_images: List[ImageInput]


class DownloadImageEvent(ProjectEvent):
    """Command: download one image (published by project manager)."""

    image_url: str
    image_type: Literal["product", "dataset"]
    label: Optional[str] = None  # only for product images


class CutoutExtractionEvent(ProjectEvent):
    """Command: run cutout extraction on a dataset image (published by project manager)."""

    image_path: str
    image_type: Literal["dataset"] = "dataset"
    industry: Optional[str] = (
        None  # Industry/use case from control analysis (e.g., "Retail", "Agriculture")
    )


class AnalyzeProductImageEvent(ProjectEvent):
    """Command: run analysis on a product image (published by project manager)."""

    image_path: str
    analysis_type: str = "detailed"


class AnalyzeDatasetImageEvent(ProjectEvent):
    """Command: run analysis on a cutout/dataset image (published by project manager)."""

    image_path: str
    analysis_type: str = "detailed"
    cutout_id: str


class AnnotateDatasetEvent(ProjectEvent):
    """Command: generate annotations for a dataset image (published by project manager)."""

    # dataset_image_id/product_image_id are already on ProjectEvent; keep this class for typing/consistency.
    pass


class ZeroShotDetectionEvent(ProjectEvent):
    """Command: run zero-shot detection on a dataset image (published by project manager for non-retail industries)."""

    dataset_image_url: str
    product_image_url: str
    threshold: float = 0.7
    top_k: int = 10
    nms_iou: float = 0.5
