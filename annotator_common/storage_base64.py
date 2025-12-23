"""
Storage utilities for loading images from Google Cloud Storage or local file system as base64.
"""

import os
import base64
from google.cloud import storage
from annotator_common.logging import get_logger, log_info, log_error

logger = get_logger(__name__)


def load_image_as_base64(image_path: str) -> str:
    """
    Load an image from GCS or local file system and convert to base64.
    
    Args:
        image_path: GCS path (gs://bucket/path) or local file path
        
    Returns:
        Base64-encoded image data as string
        
    Raises:
        ValueError: If GCS path is invalid
        FileNotFoundError: If local file doesn't exist
        Exception: For other errors during download or reading
    """
    try:
        if image_path.startswith("gs://"):
            # Download from GCS
            log_info(f"Loading image from GCS: {image_path}")
            
            # Extract bucket name and blob path
            path_parts = image_path.replace("gs://", "").split("/", 1)
            bucket_name = path_parts[0]
            blob_path = path_parts[1] if len(path_parts) > 1 else ""
            
            if not bucket_name:
                raise ValueError(f"Invalid GCS path: bucket name is empty in {image_path}")
            
            # Download blob to memory
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            
            # Download to memory and convert to base64
            image_bytes = blob.download_as_bytes()
            image_data = base64.b64encode(image_bytes).decode("utf-8")
            
            log_info(f"Successfully loaded image from GCS: {image_path} ({len(image_bytes)} bytes)")
            return image_data
        else:
            # Read from local file system
            log_info(f"Loading image from local path: {image_path}")
            
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image file not found: {image_path}")
            
            with open(image_path, "rb") as image_file:
                image_bytes = image_file.read()
                image_data = base64.b64encode(image_bytes).decode("utf-8")
            
            log_info(f"Successfully loaded image from local path: {image_path} ({len(image_bytes)} bytes)")
            return image_data
            
    except Exception as e:
        log_error(f"Error loading image: {e}, image_path: {image_path}")
        raise

