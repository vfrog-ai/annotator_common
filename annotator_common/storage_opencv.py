"""
Storage utilities for loading and saving images from Google Cloud Storage, HTTP/HTTPS URLs, or local file system using OpenCV.
"""

import os
import cv2
import numpy as np
import requests
from google.cloud import storage
from annotator_common.logging import setup_logger, log_info, log_error
from annotator_common.config import Config

logger = setup_logger(Config.SERVICE_NAME, Config.LOG_LEVEL)


def load_image_from_gcs_or_local(image_path: str) -> np.ndarray:
    """
    Load an image from GCS, HTTP/HTTPS URL, or local file system as numpy array for OpenCV.
    
    Args:
        image_path: GCS path (gs://bucket/path), HTTP/HTTPS URL, or local file path
        
    Returns:
        Image as numpy array (BGR format for OpenCV)
        
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
            
            # Download to memory
            image_bytes = blob.download_as_bytes()
            
            # Convert bytes to numpy array
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                raise Exception(f"Could not decode image from GCS: {image_path}")
            
            log_info(f"Successfully loaded image from GCS: {image_path} ({len(image_bytes)} bytes)")
            return image
        elif image_path.startswith("http://") or image_path.startswith("https://"):
            # Download from HTTP/HTTPS URL
            log_info(f"Loading image from URL: {image_path}")
            
            # Download image from URL
            response = requests.get(image_path, timeout=30, stream=True)
            response.raise_for_status()  # Raise an exception for bad status codes
            
            # Read image bytes
            image_bytes = response.content
            
            # Convert bytes to numpy array
            nparr = np.frombuffer(image_bytes, np.uint8)
            image = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if image is None:
                raise Exception(f"Could not decode image from URL: {image_path}")
            
            log_info(f"Successfully loaded image from URL: {image_path} ({len(image_bytes)} bytes)")
            return image
        else:
            # Read from local file system
            log_info(f"Loading image from local path: {image_path}")
            
            if not os.path.exists(image_path):
                raise FileNotFoundError(f"Image file not found: {image_path}")
            
            image = cv2.imread(image_path)
            if image is None:
                raise Exception(f"Could not read image: {image_path}")
            
            log_info(f"Successfully loaded image from local path: {image_path}")
            return image
            
    except Exception as e:
        log_error(f"Error loading image: {e}, image_path: {image_path}")
        raise


def save_image_to_gcs_or_local(image: np.ndarray, save_path: str) -> str:
    """
    Save an image to GCS or local file system.
    
    Args:
        image: Image as numpy array (BGR format from OpenCV)
        save_path: GCS path (gs://bucket/path) or local file path
        
    Returns:
        The save_path that was used
        
    Raises:
        ValueError: If GCS path is invalid
        Exception: For other errors during upload or writing
    """
    try:
        if save_path.startswith("gs://"):
            # Upload to GCS
            log_info(f"Saving image to GCS: {save_path}")
            
            # Extract bucket name and blob path
            path_parts = save_path.replace("gs://", "").split("/", 1)
            bucket_name = path_parts[0]
            blob_path = path_parts[1] if len(path_parts) > 1 else ""
            
            if not bucket_name:
                raise ValueError(f"Invalid GCS path: bucket name is empty in {save_path}")
            
            # Encode image to JPEG bytes
            success, encoded_image = cv2.imencode('.jpg', image)
            if not success:
                raise Exception("Failed to encode image to JPEG")
            
            image_bytes = encoded_image.tobytes()
            
            # Upload to GCS
            client = storage.Client()
            bucket = client.bucket(bucket_name)
            blob = bucket.blob(blob_path)
            blob.upload_from_string(image_bytes, content_type='image/jpeg')
            
            log_info(f"Successfully saved image to GCS: {save_path} ({len(image_bytes)} bytes)")
            return save_path
        else:
            # Save to local file system
            log_info(f"Saving image to local path: {save_path}")
            
            # Create directory if needed
            os.makedirs(os.path.dirname(save_path), exist_ok=True)
            
            cv2.imwrite(save_path, image)
            
            if not os.path.exists(save_path):
                raise Exception(f"Failed to save image: {save_path}")
            
            log_info(f"Successfully saved image to local path: {save_path}")
            return save_path
            
    except Exception as e:
        log_error(f"Error saving image: {e}, save_path: {save_path}")
        raise

