"""
Configuration management for all services.
"""

import os
from typing import Optional


class Config:
    """Configuration class for service settings."""

    # RabbitMQ Configuration
    RABBITMQ_HOST: str = os.getenv("RABBITMQ_HOST", "rabbitmq")
    RABBITMQ_PORT: int = int(os.getenv("RABBITMQ_PORT", "5672"))
    RABBITMQ_USER: str = os.getenv("RABBITMQ_USER", "user")
    RABBITMQ_PASSWORD: str = os.getenv("RABBITMQ_PASSWORD", "password")
    RABBITMQ_VHOST: str = os.getenv("RABBITMQ_VHOST", "/")

    # MongoDB Configuration
    MONGODB_HOST: str = os.getenv("MONGODB_HOST", "mongodb")
    MONGODB_PORT: int = int(os.getenv("MONGODB_PORT", "27017"))
    MONGODB_USER: str = os.getenv("MONGODB_USER", "root")
    MONGODB_PASSWORD: str = os.getenv("MONGODB_PASSWORD", "example")
    MONGODB_DATABASE: str = os.getenv("MONGODB_DATABASE", "annotator")

    # Elasticsearch Configuration
    ELASTICSEARCH_HOST: str = os.getenv("ELASTICSEARCH_HOST", "elasticsearch")
    ELASTICSEARCH_PORT: int = int(os.getenv("ELASTICSEARCH_PORT", "9200"))

    # Environment Configuration
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "dev")  # dev, staging, production

    # Queue Names (with environment prefix)
    # Format: {environment}_{base_name}
    QUEUE_PROJECT_EVENT: str = f"{os.getenv('ENVIRONMENT', 'dev')}_project_event"
    QUEUE_DOWNLOAD_IMAGE: str = f"{os.getenv('ENVIRONMENT', 'dev')}_download_image"
    QUEUE_CUTOUT: str = f"{os.getenv('ENVIRONMENT', 'dev')}_cutout"
    QUEUE_ANALYZE_IMAGE: str = f"{os.getenv('ENVIRONMENT', 'dev')}_analyze_image"
    QUEUE_DISQUALIFY_CUTOUT: str = (
        f"{os.getenv('ENVIRONMENT', 'dev')}_disqualify_cutout"
    )
    QUEUE_ANNOTATE_DATASET: str = f"{os.getenv('ENVIRONMENT', 'dev')}_annotate_dataset"
    QUEUE_VFROG_ANNOTATION: str = (
        f"{os.getenv('ENVIRONMENT', 'dev')}_vfrog_annotation_event"
    )

    # Exchange Names (with environment prefix)
    EXCHANGE_PROJECT: str = f"{os.getenv('ENVIRONMENT', 'dev')}_project_exchange"

    # Service Configuration
    SERVICE_NAME: str = os.getenv("SERVICE_NAME", "unknown_service")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

    # Supabase Configuration (optional)
    SUPABASE_URL: Optional[str] = os.getenv("SUPABASE_URL")
    SUPABASE_KEY: Optional[str] = os.getenv("SUPABASE_API_KEY")

    # Google Cloud Pub/Sub Configuration
    GCP_PROJECT_ID: str = os.getenv("GCP_PROJECT_ID", "")
    PUBSUB_PUSH_ENDPOINT: str = os.getenv("PUBSUB_PUSH_ENDPOINT", "/pubsub/push")

    # Firestore Configuration
    GOOGLE_CLOUD_PROJECT: str = os.getenv(
        "GOOGLE_CLOUD_PROJECT", os.getenv("GCP_PROJECT_ID", "local-dev")
    )
    FIRESTORE_EMULATOR_HOST: Optional[str] = os.getenv("FIRESTORE_EMULATOR_HOST")
    FIRESTORE_DATABASE: Optional[str] = os.getenv("FIRESTORE_DATABASE")

    # Image Storage Configuration
    IMAGE_STORAGE_PATH: str = os.getenv("IMAGE_STORAGE_PATH", "/images")

    # Pub/Sub Topic Names (with environment prefix)
    # Format: {environment}_{base_name}
    # These replace the QUEUE_* constants for Pub/Sub migration
    TOPIC_PROJECT_EVENT: str = f"{os.getenv('ENVIRONMENT', 'dev')}_project_event"
    TOPIC_DOWNLOAD_IMAGE: str = f"{os.getenv('ENVIRONMENT', 'dev')}_download_image"
    TOPIC_CUTOUT: str = f"{os.getenv('ENVIRONMENT', 'dev')}_cutout"
    TOPIC_ANALYZE_IMAGE: str = f"{os.getenv('ENVIRONMENT', 'dev')}_analyze_image"
    TOPIC_DISQUALIFY_CUTOUT: str = (
        f"{os.getenv('ENVIRONMENT', 'dev')}_disqualify_cutout"
    )
    TOPIC_ANNOTATE_DATASET: str = f"{os.getenv('ENVIRONMENT', 'dev')}_annotate_dataset"

    @classmethod
    def get_mongodb_uri(cls) -> str:
        """Get MongoDB connection URI.

        Supports two modes:
        1. Cloud Run: Uses MONGODB_URI environment variable (from Secret Manager)
        2. Docker Compose: Builds URI from individual components
        """
        # Cloud Run mode: use complete URI from environment
        import logging

        mongodb_uri = os.getenv("MONGODB_URI")
        logging.getLogger(__name__).info(f"MongoDB URI: {mongodb_uri}")
        if mongodb_uri:
            return mongodb_uri

        # Docker Compose mode: build URI from components
        if not cls.MONGODB_USER or cls.MONGODB_USER == "":
            return f"mongodb://{cls.MONGODB_HOST}:{cls.MONGODB_PORT}/{cls.MONGODB_DATABASE}"
        return f"mongodb://{cls.MONGODB_USER}:{cls.MONGODB_PASSWORD}@{cls.MONGODB_HOST}:{cls.MONGODB_PORT}/{cls.MONGODB_DATABASE}?authSource=admin"

    @classmethod
    def get_rabbitmq_uri(cls) -> str:
        """Get RabbitMQ connection URI.

        Supports two modes:
        1. Cloud Run: Uses RABBITMQ_URI environment variable (from Secret Manager)
        2. Docker Compose: Builds URI from individual components
        """
        # Cloud Run mode: use complete URI from environment
        rabbitmq_uri = os.getenv("RABBITMQ_URI")
        if rabbitmq_uri:
            return rabbitmq_uri

        # Docker Compose mode: build URI from components
        return f"amqp://{cls.RABBITMQ_USER}:{cls.RABBITMQ_PASSWORD}@{cls.RABBITMQ_HOST}:{cls.RABBITMQ_PORT}{cls.RABBITMQ_VHOST}"
