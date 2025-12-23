"""
Google Cloud Pub/Sub publisher for async message publishing.
Supports both Pub/Sub (production) and Pub/Sub emulator (local development).
"""

import json
import os
import asyncio
from typing import Dict, Any, Optional, Union
from google.cloud import pubsub_v1
from google.api_core import exceptions
from annotator_common.config import Config
from annotator_common.logging import get_logger, log_info, log_warning, log_error
from pydantic import BaseModel

logger = get_logger(__name__)

PUBSUB_EMULATOR_HOST = os.getenv("PUBSUB_EMULATOR_HOST")

# Global publisher client (singleton)
_publisher_client: Optional[pubsub_v1.PublisherClient] = None


def get_publisher_client() -> pubsub_v1.PublisherClient:
    """Get or create the singleton Pub/Sub publisher client.

    Returns a Pub/Sub client for either:
    - Production mode (when PUBSUB_EMULATOR_HOST is not set)
    - Emulator mode (when PUBSUB_EMULATOR_HOST is set)
    """
    global _publisher_client

    if _publisher_client is None:
        _publisher_client = pubsub_v1.PublisherClient()
        if PUBSUB_EMULATOR_HOST:
            log_info(
                f"Created Pub/Sub publisher client (emulator mode: {PUBSUB_EMULATOR_HOST})"
            )
        else:
            log_info("Created Pub/Sub publisher client (production mode)")
    return _publisher_client


class PubSubPublisher:
    """Manages Pub/Sub topic publishing with async support."""

    def __init__(self, project_id: Optional[str] = None):
        """
        Initialize Pub/Sub publisher.

        Args:
            project_id: GCP project ID. If None, uses Config.GCP_PROJECT_ID or
                       attempts to detect from environment.
        """
        # Cache for verified topics to avoid repeated existence checks (rate limit optimization)
        self._verified_topics: set = set()

        # Require GCP_PROJECT_ID
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

        # Create client (will use emulator if PUBSUB_EMULATOR_HOST is set)
        self._client = get_publisher_client()
        log_info(f"Initialized PubSubPublisher for project: {self.project_id}")

    def _get_topic_path(self, topic_name: str) -> str:
        """Get full topic path."""
        return self._client.topic_path(self.project_id, topic_name)

    def _normalize_message(
        self, message: Union[Dict[str, Any], BaseModel]
    ) -> Dict[str, Any]:
        """Convert a pydantic model to a JSON-serializable dict (or pass through dicts)."""
        if isinstance(message, BaseModel):
            return message.model_dump(mode="json")
        return message

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

        Uses Pub/Sub emulator if PUBSUB_EMULATOR_HOST is set, otherwise uses production Pub/Sub.

        Args:
            topic_name: Name of the topic (with environment prefix, e.g., "dev_download_image")
            message: Message payload as dictionary
            attributes: Optional message attributes
            ordering_key: Optional ordering key for ordered delivery
            max_retries: Maximum number of retry attempts for rate limit errors (default: 3)

        Returns:
            Message ID from Pub/Sub

        Raises:
            Exception: If publishing fails after all retries
        """
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

                return message_id

            except exceptions.NotFound:
                # Topic doesn't exist - don't retry
                log_warning(
                    f"Topic {topic_name} not found. Message not published. "
                    f"Create the topic in GCP Console or via gcloud."
                )
                raise

            except (exceptions.ResourceExhausted, exceptions.ServiceUnavailable) as e:
                # Rate limiting or service unavailable - retry with exponential backoff
                last_exception = e
                if attempt < max_retries:
                    wait_time = 2**attempt  # Exponential backoff: 1s, 2s, 4s
                    log_warning(
                        f"Rate limit or service unavailable publishing to {topic_name} "
                        f"(attempt {attempt + 1}/{max_retries + 1}): {e}. "
                        f"Retrying in {wait_time}s..."
                    )
                    await asyncio.sleep(wait_time)
                else:
                    log_error(
                        f"Failed to publish {message.get('event_type')} to topic {topic_name} after {max_retries + 1} attempts "
                        f"(rate limit/service unavailable): {e}, message: {message}",
                        correlation_id=message.get("correlation_id", ""),
                        project_iteration_id=message.get("project_iteration_id", ""),
                        event_type=message.get("event_type", ""),
                        exc_info=True,
                    )
        # Should never reach here, but just in case
        if last_exception:
            raise last_exception
        log_error(
            f"Failed to publish {message.get('event_type', '')} to topic {topic_name} after {max_retries + 1} attempts",
            correlation_id=message.get("correlation_id", ""),
            project_iteration_id=message.get("project_iteration_id", ""),
            event_type=message.get("event_type", ""),
            exc_info=True,
        )

    def ensure_topic_exists(self, topic_name: str) -> str:
        """
        Ensure a topic exists, creating it if necessary.
        Uses caching to avoid repeated existence checks (rate limit optimization).

        Args:
            topic_name: Name of the topic

        Returns:
            Full topic path
        """
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
                log_info(f"Created topic: {topic_name}")
                # Cache that we've verified this topic exists
                self._verified_topics.add(topic_name)
            except exceptions.AlreadyExists:
                # Race condition - topic was created between check and create
                # Topic was created concurrently (debug level, no need to log)
                pass
                # Cache that we've verified this topic exists
                self._verified_topics.add(topic_name)
            except Exception as e:
                log_warning(f"Could not create topic {topic_name}: {e}")
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
