"""
Google Cloud Pub/Sub publisher for async message publishing.
"""

import json
import os
import asyncio
from typing import Dict, Any, Optional
from google.cloud import pubsub_v1
from google.api_core import exceptions
from annotator_common.config import Config
from annotator_common.logging import get_logger

logger = get_logger(__name__)

# Global publisher client (singleton)
_publisher_client: Optional[pubsub_v1.PublisherClient] = None


def get_publisher_client() -> pubsub_v1.PublisherClient:
    """Get or create the singleton Pub/Sub publisher client."""
    global _publisher_client
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
        """
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

        self._client = get_publisher_client()
        logger.info(f"Initialized PubSubPublisher for project: {self.project_id}")

    def _get_topic_path(self, topic_name: str) -> str:
        """Get full topic path."""
        return self._client.topic_path(self.project_id, topic_name)

    async def publish_message(
        self,
        topic_name: str,
        message: Dict[str, Any],
        attributes: Optional[Dict[str, str]] = None,
        ordering_key: Optional[str] = None,
    ) -> str:
        """
        Publish a message to a Pub/Sub topic.

        Args:
            topic_name: Name of the topic (with environment prefix, e.g., "staging_download_image")
            message: Message payload as dictionary
            attributes: Optional message attributes
            ordering_key: Optional ordering key for ordered delivery

        Returns:
            Message ID from Pub/Sub

        Raises:
            Exception: If publishing fails
        """
        try:
            topic_path = self._get_topic_path(topic_name)

            # Encode message as JSON bytes
            message_bytes = json.dumps(message).encode("utf-8")

            # Prepare message attributes
            message_attributes = attributes or {}

            # Publish message (run in thread pool to avoid blocking event loop)
            future = self._client.publish(
                topic_path,
                message_bytes,
                **message_attributes,
                ordering_key=ordering_key,
            )

            # Wait for publish to complete (run in thread pool for async compatibility)
            message_id = await asyncio.to_thread(future.result, timeout=30)

            logger.info(
                f"Published message to topic {topic_name}: message_id={message_id}, "
                f"attributes={message_attributes}, ordering_key={ordering_key}"
            )

            return message_id

        except exceptions.NotFound:
            # Topic doesn't exist - log warning but don't fail
            logger.warning(
                f"Topic {topic_name} not found. Message not published. "
                f"Create the topic in GCP Console or via gcloud."
            )
            raise
        except Exception as e:
            logger.error(
                f"Failed to publish message to topic {topic_name}: {e}, message: {message}"
            )
            raise

    async def ensure_topic_exists(self, topic_name: str) -> str:
        """
        Ensure a topic exists, creating it if necessary.

        Args:
            topic_name: Name of the topic

        Returns:
            Full topic path
        """
        topic_path = self._get_topic_path(topic_name)

        try:
            # Try to get the topic
            self._client.get_topic(request={"topic": topic_path})
            logger.debug(f"Topic {topic_name} already exists")
        except exceptions.NotFound:
            # Topic doesn't exist, create it
            try:
                self._client.create_topic(request={"name": topic_path})
                logger.info(f"Created topic: {topic_name}")
            except exceptions.AlreadyExists:
                # Race condition - topic was created between check and create
                logger.debug(f"Topic {topic_name} was created concurrently")
            except Exception as e:
                logger.warning(f"Could not create topic {topic_name}: {e}")

        return topic_path


# Singleton instance
_pubsub_publisher: Optional[PubSubPublisher] = None


def get_pubsub_publisher() -> PubSubPublisher:
    """Get the singleton PubSubPublisher instance."""
    global _pubsub_publisher
    if _pubsub_publisher is None:
        _pubsub_publisher = PubSubPublisher()
    return _pubsub_publisher
