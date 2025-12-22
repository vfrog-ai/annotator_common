"""
Firestore database connection and repository layer.
"""

from annotator_common.firestore.connection import init_firestore, get_firestore_client
from annotator_common.firestore.repositories import (
    ProjectIterationRepository,
    DatasetImageRepository,
    ProductImageRepository,
    CutoutRepository,
    CutoutAnalysisRepository,
    ProcessedEventRepository,
    AnnotatedImageRepository,
)

__all__ = [
    "init_firestore",
    "get_firestore_client",
    "ProjectIterationRepository",
    "DatasetImageRepository",
    "ProductImageRepository",
    "CutoutRepository",
    "CutoutAnalysisRepository",
    "ProcessedEventRepository",
    "AnnotatedImageRepository",
]

