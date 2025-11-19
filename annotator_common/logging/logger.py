"""
Logging configuration and utilities.
"""

import logging
import sys
import socket
import json
from typing import Optional, Dict, Any
from datetime import datetime
from annotator_common.config import Config

try:
    from elasticsearch import Elasticsearch

    ELASTICSEARCH_AVAILABLE = True
except ImportError:
    ELASTICSEARCH_AVAILABLE = False


class CloudLoggingJSONFormatter(logging.Formatter):
    """
    Custom formatter that outputs JSON for Cloud Logging when message contains structured data.
    Cloud Logging automatically parses JSON from stdout if the line starts with '{'.
    """

    def format(self, record):
        # Check if message looks like JSON (starts with '{')
        message = record.getMessage()
        if message.strip().startswith("{"):
            try:
                # Try to parse as JSON - if it's valid, output it directly
                parsed = json.loads(message)
                # Output as pure JSON for Cloud Logging
                log_entry = {
                    "severity": record.levelname,
                    "message": parsed.get("message", str(message)),
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "service": record.name,
                }
                # Add all structured fields from parsed JSON
                for key, value in parsed.items():
                    if key != "message":  # Already added above
                        log_entry[key] = value
                return json.dumps(log_entry)
            except (json.JSONDecodeError, ValueError, TypeError):
                # If JSON parsing fails, fall back to standard format
                pass

        # Standard format for non-JSON messages
        return super().format(record)


class ElasticsearchHandler(logging.Handler):
    """Custom handler for logging to Elasticsearch."""

    def __init__(self, es_client, index_pattern="logs-{date}"):
        super().__init__()
        self.es_client = es_client
        self.index_pattern = index_pattern
        self.hostname = socket.gethostname()

    def emit(self, record):
        """Emit a log record to Elasticsearch."""
        try:
            # Create index name with date
            date_str = datetime.utcnow().strftime("%Y.%m.%d")
            index_name = self.index_pattern.format(date=date_str)

            # Create document
            doc = {
                "timestamp": datetime.utcnow().isoformat(),
                "level": record.levelname,
                "service": record.name,
                "hostname": self.hostname,
                "message": self.format(record),
            }

            # Index the document
            self.es_client.index(index=index_name, document=doc)
        except Exception:
            # Silently fail - don't break logging if Elasticsearch is unavailable
            pass


def setup_logger(
    service_name: Optional[str] = None, log_level: Optional[str] = None
) -> logging.Logger:
    """Setup and configure logger for a service."""

    # Use provided name/level or fall back to config
    name = service_name or Config.SERVICE_NAME
    level = log_level or Config.LOG_LEVEL

    # Configure root logger to ensure all loggers inherit handlers
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper()))

    # Avoid duplicate handlers on root logger
    if not root_logger.handlers:
        # Create console handler
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level.upper()))

        # Use custom formatter that outputs JSON for Cloud Logging when structured fields are present
        # For regular logs, use standard format
        formatter = CloudLoggingJSONFormatter(
            fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        console_handler.setFormatter(formatter)

        # Add console handler to root logger
        root_logger.addHandler(console_handler)

        # Add Elasticsearch handler if available and not in Cloud Run
        # In Cloud Run, stdout/stderr automatically go to Cloud Logging
        # Skip Elasticsearch in local mode or if explicitly disabled
        import os

        skip_elasticsearch = (
            os.getenv("K_SERVICE") is not None  # K_SERVICE is set by Cloud Run
            or os.getenv("LOCAL_MODE", "false").lower() == "true"  # Skip in local mode
            or os.getenv("DISABLE_ELASTICSEARCH", "false").lower() == "true"  # Explicitly disabled
        )

        if ELASTICSEARCH_AVAILABLE and not skip_elasticsearch:
            try:
                # Test connection before adding handler to avoid spam
                es_client = Elasticsearch(
                    [f"http://{Config.ELASTICSEARCH_HOST}:{Config.ELASTICSEARCH_PORT}"],
                    verify_certs=False,
                    ssl_show_warn=False,
                    request_timeout=2,
                    max_retries=0,
                )
                # Quick health check - if this fails, don't add the handler
                es_client.ping(request_timeout=1)
                es_handler = ElasticsearchHandler(es_client)
                es_handler.setLevel(getattr(logging, level.upper()))
                es_handler.setFormatter(formatter)
                root_logger.addHandler(es_handler)
            except Exception:
                # Silently fail if Elasticsearch is not available
                # Don't log errors to avoid spam
                pass

    # Return a named logger that will inherit from root logger
    return logging.getLogger(name)


def get_logger(name: str) -> logging.Logger:
    """Get or create a logger with the given name, setting it up if needed."""
    logger = logging.getLogger(name)

    # If logger doesn't have handlers, set it up
    if not logger.handlers:
        # Use Config.SERVICE_NAME (from environment) for the service name
        # but keep the module name for the logger name
        # This ensures logs show the correct service name while maintaining module-level logging
        return setup_logger(service_name=None)  # None will use Config.SERVICE_NAME

    return logger


class StructuredLogger:
    """
    Wrapper around logger that adds structured fields for Google Cloud Logging.
    This allows filtering by fields like project_iteration_id in Cloud Logging Explorer.
    """

    def __init__(self, logger: logging.Logger):
        self.logger = logger

    def _format_structured_message(
        self, message: str, project_iteration_id: Optional[str] = None, **kwargs
    ) -> str:
        """
        Format message with structured fields for Cloud Logging.

        For Cloud Logging to parse JSON automatically, we need to output the entire
        log entry as JSON. However, to maintain compatibility with the existing formatter,
        we'll include the structured fields in the message in a way that Cloud Logging
        can extract, while still showing the message in the log.

        We'll use a format that Cloud Logging can parse: include JSON at the start
        of the message, followed by the readable message.
        """
        if project_iteration_id or kwargs:
            structured_data: Dict[str, Any] = {
                "message": message,
            }
            if project_iteration_id:
                structured_data["project_iteration_id"] = project_iteration_id
            structured_data.update(kwargs)
            # Output JSON that Cloud Logging can parse
            # The CloudLoggingJSONFormatter will detect this and output proper JSON
            json_str = json.dumps(structured_data)
            return json_str
        return message

    def debug(self, message: str, project_iteration_id: Optional[str] = None, **kwargs):
        """Log debug message with optional structured fields."""
        formatted = self._format_structured_message(
            message, project_iteration_id, **kwargs
        )
        self.logger.debug(formatted)

    def info(self, message: str, project_iteration_id: Optional[str] = None, **kwargs):
        """Log info message with optional structured fields."""
        formatted = self._format_structured_message(
            message, project_iteration_id, **kwargs
        )
        self.logger.info(formatted)

    def warning(
        self, message: str, project_iteration_id: Optional[str] = None, **kwargs
    ):
        """Log warning message with optional structured fields."""
        formatted = self._format_structured_message(
            message, project_iteration_id, **kwargs
        )
        self.logger.warning(formatted)

    def error(
        self,
        message: str,
        project_iteration_id: Optional[str] = None,
        exc_info: bool = False,
        **kwargs,
    ):
        """Log error message with optional structured fields."""
        formatted = self._format_structured_message(
            message, project_iteration_id, **kwargs
        )
        self.logger.error(formatted, exc_info=exc_info)

    def critical(
        self, message: str, project_iteration_id: Optional[str] = None, **kwargs
    ):
        """Log critical message with optional structured fields."""
        formatted = self._format_structured_message(
            message, project_iteration_id, **kwargs
        )
        self.logger.critical(formatted)

    def __getattr__(self, name: str):
        """Delegate other attributes to the underlying logger."""
        return getattr(self.logger, name)


def get_structured_logger(name: str) -> StructuredLogger:
    """
    Get a structured logger that supports project_iteration_id filtering.

    Usage:
        logger = get_structured_logger(__name__)
        logger.info("Processing image", project_iteration_id="project-123")

    In Cloud Logging Explorer, you can then filter by:
        jsonPayload.project_iteration_id="project-123"
    """
    return StructuredLogger(logging.getLogger(name))
