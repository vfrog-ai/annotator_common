"""
Google Cloud Pub/Sub publisher for async message publishing.
Supports both Pub/Sub (production) and direct HTTP calls (local development).
"""

import json
import os
import asyncio
from typing import Dict, Any, Optional, Union
from google.cloud import pubsub_v1
from google.api_core import exceptions
import aiohttp
from annotator_common.config import Config
from annotator_common.logging import get_logger
from pydantic import BaseModel

logger = get_logger(__name__)

# Local mode flag - when True, make direct HTTP calls instead of using Pub/Sub
LOCAL_MODE = os.getenv("LOCAL_MODE", "false").lower() == "true"

# Service URL mappings for local mode (topic_name -> service_url)
LOCAL_SERVICE_URLS = {
    "download_image": os.getenv(
        "IMAGE_DOWNLOAD_SERVICE_URL", "http://image-download-service:8080"
    ),
    "cutout": os.getenv("CUTOUT_SERVICE_URL", "http://cutout-service:8080"),
    "analyze_image": os.getenv(
        "IMAGE_ANALYSIS_SERVICE_URL", "http://image-analysis-service:8080"
    ),
    "annotate_dataset": os.getenv(
        "ANNOTATION_SERVICE_URL", "http://annotation-service:8080"
    ),
    "project_event": os.getenv(
        "PROJECT_MANAGER_SERVICE_URL", "http://project-manager:8080"
    ),
}

# Global publisher client (singleton)
_publisher_client: Optional[pubsub_v1.PublisherClient] = None


def get_publisher_client() -> Optional[pubsub_v1.PublisherClient]:
    """Get or create the singleton Pub/Sub publisher client.

    Returns None if LOCAL_MODE=true (direct HTTP calls are used instead).
    """
    global _publisher_client

    # In local mode, don't create a Pub/Sub client
    if LOCAL_MODE:
        logger.debug("LOCAL_MODE enabled - skipping Pub/Sub client creation")
        return None

    if _publisher_client is None:
        _publisher_client = pubsub_v1.PublisherClient()
        logger.info("Created Pub/Sub publisher client")
    return _publisher_client


class PubSubPublisher:
    """Manages Pub/Sub topic publishing with async support."""

    def __init__(self, project_id: Optional[str] = None):
        """
        Initialize Pub/Sub publisher.

        Args:
            project_id: GCP project ID. If None, uses Config.GCP_PROJECT_ID or
                       attempts to detect from environment.
                       Not required when LOCAL_MODE=true.
        """
        # Cache for verified topics to avoid repeated existence checks (rate limit optimization)
        self._verified_topics: set = set()
        
        # In local mode, skip GCP_PROJECT_ID validation
        if LOCAL_MODE:
            self.project_id = project_id or Config.GCP_PROJECT_ID or "local-project"
            self._client = None
            logger.info("Initialized PubSubPublisher in LOCAL_MODE (direct HTTP calls)")
            return

        # Production mode: require GCP_PROJECT_ID
        self.project_id = project_id or Config.GCP_PROJECT_ID
        if not self.project_id:
            # Try to detect from environment
            self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv(
                "GCP_PROJECT"
            )
            if not self.project_id:
                raise ValueError(
                    "GCP_PROJECT_ID must be set in environment or passed to PubSubPublisher"
                )

        # Only create client if not in local mode
        self._client = get_publisher_client()
        if self._client is None:
            logger.info(
                f"Initialized PubSubPublisher in LOCAL_MODE for project: {self.project_id}"
            )
        else:
            logger.info(f"Initialized PubSubPublisher for project: {self.project_id}")

    def _get_topic_path(self, topic_name: str) -> str:
        """Get full topic path."""
        return self._client.topic_path(self.project_id, topic_name)

    def _normalize_message(self, message: Union[Dict[str, Any], BaseModel]) -> Dict[str, Any]:
        """Convert a pydantic model to a JSON-serializable dict (or pass through dicts)."""
        if isinstance(message, BaseModel):
            return message.model_dump(mode="json")
        return message

    async def _publish_via_http(
        self,
        topic_name: str,
        message: Union[Dict[str, Any], BaseModel],
        max_retries: int = 3,
    ) -> str:
        """
        Publish message via direct HTTP call (local mode).

        Args:
            topic_name: Name of the topic (with environment prefix, e.g., "staging_download_image")
            message: Message payload as dictionary
            max_retries: Maximum number of retry attempts

        Returns:
            Mock message ID (for compatibility)

        Raises:
            Exception: If HTTP call fails after all retries
        """
        # Extract base topic name (remove environment prefix)
        base_topic = topic_name.split("_", 1)[-1] if "_" in topic_name else topic_name

        # Get service URL
        service_url = LOCAL_SERVICE_URLS.get(base_topic)
        if not service_url:
            raise ValueError(
                f"No service URL configured for topic: {base_topic}. "
                f"Available topics: {list(LOCAL_SERVICE_URLS.keys())}"
            )

        # Determine endpoint path based on topic
        endpoint_map = {
            "download_image": "/pubsub/push/download_image",
            "cutout": "/pubsub/push/cutout",
            "analyze_image": "/pubsub/push/analyze_image",
            "annotate_dataset": "/pubsub/push/annotate_dataset",
            "project_event": "/pubsub/push/project_event",
        }
        endpoint = endpoint_map.get(base_topic, f"/pubsub/push/{base_topic}")
        url = f"{service_url}{endpoint}"

        # Make HTTP POST request with retry logic
        last_exception = None
        normalized_message = self._normalize_message(message)
        async with aiohttp.ClientSession() as session:
            for attempt in range(max_retries + 1):
                try:
                    async with session.post(
                        url,
                        json=normalized_message,
                        timeout=aiohttp.ClientTimeout(total=30),
                    ) as response:
                        if response.status == 200:
                            logger.info(
                                f"Published message via HTTP to {url}: status={response.status}, "
                                f"topic={topic_name}"
                            )
                            return f"http-{topic_name}-{attempt}"  # Mock message ID
                        else:
                            error_text = await response.text()
                            raise Exception(
                                f"HTTP {response.status} from {url}: {error_text}"
                            )
                except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                        logger.warning(
                            f"HTTP call failed to {url} (attempt {attempt + 1}/{max_retries + 1}): {e}. "
                            f"Retrying in {wait_time}s..."
                        )
                        await asyncio.sleep(wait_time)
                    else:
                        logger.error(
                            f"Failed to publish message via HTTP to {url} after {max_retries + 1} attempts: {e}, "
                            f"message: {normalized_message}"
                        )
                        raise
                except Exception as e:
                    logger.error(
                        f"Failed to publish message via HTTP to {url}: {e}, message: {normalized_message}"
                    )
                    raise

        if last_exception:
            raise last_exception
        raise Exception(
            f"Failed to publish message via HTTP to {url} after {max_retries + 1} attempts"
        )

    async def publish_message(
        self,
        topic_name: str,
        message: Union[Dict[str, Any], BaseModel],
        attributes: Optional[Dict[str, str]] = None,
        ordering_key: Optional[str] = None,
        max_retries: int = 3,
    ) -> str:
        """
        Publish a message to a Pub/Sub topic with retry logic for rate limiting.
        In LOCAL_MODE, makes direct HTTP calls instead of using Pub/Sub.

        Args:
            topic_name: Name of the topic (with environment prefix, e.g., "staging_download_image")
            message: Message payload as dictionary
            attributes: Optional message attributes (ignored in local mode)
            ordering_key: Optional ordering key for ordered delivery (ignored in local mode)
            max_retries: Maximum number of retry attempts for rate limit errors (default: 3)

        Returns:
            Message ID from Pub/Sub (or mock ID in local mode)

        Raises:
            Exception: If publishing fails after all retries
        """
        # In local mode, make direct HTTP calls
        if LOCAL_MODE:
            return await self._publish_via_http(topic_name, message, max_retries)

        # Production mode: use Pub/Sub
        # Ensure topic exists before publishing (especially important for emulator)
        topic_path = await asyncio.to_thread(self.ensure_topic_exists, topic_name)

        normalized_message = self._normalize_message(message)

        # Encode message as JSON bytes
        message_bytes = json.dumps(normalized_message).encode("utf-8")

        # Prepare message attributes
        message_attributes = attributes or {}

        # Publish message with retry logic for rate limiting (429/ResourceExhausted)
        publish_kwargs = {
            **message_attributes,
        }
        if ordering_key is not None:
            publish_kwargs["ordering_key"] = ordering_key

        last_exception = None
        for attempt in range(max_retries + 1):
            try:
                future = self._client.publish(
                    topic_path,
                    message_bytes,
                    **publish_kwargs,
                )

                # Wait for publish to complete (run in thread pool for async compatibility)
                message_id = await asyncio.to_thread(future.result, timeout=30)

                logger.info(
                    f"Published message to topic {topic_name}: message_id={message_id}, "
                    f"attributes={message_attributes}, ordering_key={ordering_key}"
                )

                return message_id

            except exceptions.NotFound:
                # Topic doesn't exist - don't retry
                logger.warning(
                    f"Topic {topic_name} not found. Message not published. "
                    f"Create the topic in GCP Console or via gcloud."
                )
                raise

            except (exceptions.ResourceExhausted, exceptions.ServiceUnavailable) as e:
                # Rate limiting or service unavailable - retry with exponential backoff
                last_exception = e
                if attempt < max_retries:
                    wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                    logger.warning(
                        f"Rate limit or service unavailable publishing to {topic_name} "
                        f"(attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"Failed to publish message to topic {topic_name} after {max_retries + 1} attempts "
                        f"(rate limit/service unavailable): {e}, message: {message}"
                    )
                    raise

            except Exception as e:
                # Other errors - don't retry, just raise
                logger.error(
                    f"Failed to publish message to topic {topic_name}: {e}, message: {message}"
                )
                raise

        # Should never reach here, but just in case
        if last_exception:
            raise last_exception
        raise Exception(
            f"Failed to publish message to topic {topic_name} after {max_retries + 1} attempts"
        )

    def ensure_topic_exists(self, topic_name: str) -> str:
        """
        Ensure a topic exists, creating it if necessary.
        Uses caching to avoid repeated existence checks (rate limit optimization).
        No-op in LOCAL_MODE.

        Args:
            topic_name: Name of the topic

        Returns:
            Full topic path
        """
        if LOCAL_MODE:
            # No-op in local mode
            return f"local://{topic_name}"

        topic_path = self._get_topic_path(topic_name)

        # If we've already verified this topic exists, skip the check
        if topic_name in self._verified_topics:
            return topic_path

        try:
            # Try to get the topic
            self._client.get_topic(request={"topic": topic_path})
            logger.debug(f"Topic {topic_name} already exists")
            # Cache that we've verified this topic exists
            self._verified_topics.add(topic_name)
        except exceptions.NotFound:
            # Topic doesn't exist, create it
            try:
                self._client.create_topic(request={"name": topic_path})
                logger.info(f"Created topic: {topic_name}")
                # Cache that we've verified this topic exists
                self._verified_topics.add(topic_name)
            except exceptions.AlreadyExists:
                # Race condition - topic was created between check and create
                logger.debug(f"Topic {topic_name} was created concurrently")
                # Cache that we've verified this topic exists
                self._verified_topics.add(topic_name)
            except Exception as e:
                logger.warning(f"Could not create topic {topic_name}: {e}")
                # Don't cache on error - we'll retry next time

        return topic_path


# Singleton instance
_pubsub_publisher: Optional[PubSubPublisher] = None


def get_pubsub_publisher() -> PubSubPublisher:
    """Get the singleton PubSubPublisher instance."""
    global _pubsub_publisher
    if _pubsub_publisher is None:
        _pubsub_publisher = PubSubPublisher()
    return _pubsub_publisher
