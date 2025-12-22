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
        self._processing = False  # Flag to prevent recursion

    def emit(self, record):
        """Emit a log record to Elasticsearch."""
        # Prevent recursion - if we're already processing a log, skip this one
        if self._processing:
            return

        self._processing = True
        try:
            # Create index name with date
            date_str = datetime.utcnow().strftime("%Y.%m.%d")
            index_name = self.index_pattern.format(date=date_str)

            # Get the raw message from the record first (before formatting)
            # Check if the record message itself is JSON
            raw_message = record.getMessage()

            # Try to parse JSON from the raw message first
            parsed_json = None
            if raw_message.strip().startswith("{"):
                try:
                    parsed_json = json.loads(raw_message)
                except (json.JSONDecodeError, ValueError, TypeError):
                    pass

            # If we have parsed JSON from raw message, use it as the base document
            # This preserves ALL structured fields (correlation_id, project_iteration_id, etc.)
            if parsed_json and isinstance(parsed_json, dict):
                # Start with ALL parsed JSON fields (these are ALL the structured fields)
                # Using dict(parsed_json) ensures ALL fields are included as top-level fields
                doc = dict(parsed_json)
                # Ensure we have essential fields (don't override if they exist)
                if "timestamp" not in doc or not doc.get("timestamp"):
                    doc["timestamp"] = datetime.utcnow().isoformat() + "Z"
                if "level" not in doc:
                    doc["level"] = record.levelname
                if "severity" not in doc:
                    doc["severity"] = record.levelname
                if "service" not in doc or not doc.get("service"):
                    doc["service"] = record.name
                doc["hostname"] = self.hostname
            else:
                # Format the record to get the formatted message
                # CloudLoggingJSONFormatter processes JSON and adds severity, timestamp, service
                formatted_message = self.format(record)
                # Try to parse the formatted message (CloudLoggingJSONFormatter outputs JSON)
                if formatted_message.strip().startswith("{"):
                    try:
                        parsed_json = json.loads(formatted_message)
                        if isinstance(parsed_json, dict):
                            # Use ALL parsed JSON fields as the document
                            # This includes all structured fields from CloudLoggingJSONFormatter
                            doc = dict(parsed_json)
                            # Ensure we have essential fields (don't override if they exist)
                            if "timestamp" not in doc or not doc.get("timestamp"):
                                doc["timestamp"] = datetime.utcnow().isoformat() + "Z"
                            if "level" not in doc:
                                doc["level"] = record.levelname
                            if "severity" not in doc:
                                doc["severity"] = record.levelname
                            if "service" not in doc or not doc.get("service"):
                                doc["service"] = record.name
                            doc["hostname"] = self.hostname
                        else:
                            # Fallback if parsed_json is not a dict
                            doc = {
                                "timestamp": datetime.utcnow().isoformat() + "Z",
                                "level": record.levelname,
                                "severity": record.levelname,
                                "service": record.name,
                                "hostname": self.hostname,
                                "message": formatted_message,
                            }
                    except (json.JSONDecodeError, ValueError, TypeError):
                        # If parsing fails, use standard format
                        doc = {
                            "timestamp": datetime.utcnow().isoformat() + "Z",
                            "level": record.levelname,
                            "severity": record.levelname,
                            "service": record.name,
                            "hostname": self.hostname,
                            "message": formatted_message,
                        }
                else:
                    # Standard format for non-JSON messages
                    doc = {
                        "timestamp": datetime.utcnow().isoformat() + "Z",
                        "level": record.levelname,
                        "severity": record.levelname,
                        "service": record.name,
                        "hostname": self.hostname,
                        "message": formatted_message,
                    }

            # Index the document - ALL fields in doc will be stored as top-level fields in Elasticsearch
            self.es_client.index(index=index_name, document=doc)
        except Exception as e:
            # Silently fail - don't break logging if Elasticsearch is unavailable
            # But log to stderr for debugging (using print, not logging, to avoid recursion)
            import sys

            # Only print error details, not full traceback, to avoid recursion
            error_msg = str(e)
            if "recursion" in error_msg.lower():
                print(
                    "[ELASTICSEARCH_HANDLER] Recursion detected, skipping log entry",
                    file=sys.stderr,
                )
            else:
                print(
                    f"[ELASTICSEARCH_HANDLER] Error indexing log: {error_msg}",
                    file=sys.stderr,
                )
            pass
        finally:
            # Always reset the flag, even if an exception occurred
            self._processing = False


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

    # Use custom formatter that outputs JSON for Cloud Logging when structured fields are present
    # For regular logs, use standard format
    formatter = CloudLoggingJSONFormatter(
        fmt="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Add console handler if not already present (uvicorn/FastAPI may have already added one)
    has_console_handler = any(
        isinstance(h, logging.StreamHandler) for h in root_logger.handlers
    )
    if not has_console_handler:
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, level.upper()))
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)

    # Add Elasticsearch handler if available and not in Cloud Run
    # In Cloud Run, stdout/stderr automatically go to Cloud Logging
    # Skip Elasticsearch in local mode or if explicitly disabled
    # Check if Elasticsearch handler already exists to avoid duplicates
    import os

    skip_elasticsearch = (
        os.getenv("K_SERVICE") is not None  # K_SERVICE is set by Cloud Run
        or os.getenv("DISABLE_ELASTICSEARCH", "false").lower()
        == "true"  # Explicitly disabled
        # Allow Elasticsearch in LOCAL_MODE if ELASTICSEARCH_HOST is explicitly set (for local ELK stack)
        or (
            os.getenv("LOCAL_MODE", "false").lower() == "true"
            and not os.getenv("ELASTICSEARCH_HOST")
        )  # Skip only if LOCAL_MODE and no ELASTICSEARCH_HOST
    )

    # Check if Elasticsearch handler already exists to avoid duplicates
    has_elasticsearch_handler = any(
        isinstance(h, ElasticsearchHandler) for h in root_logger.handlers
    )

    if (
        ELASTICSEARCH_AVAILABLE
        and not skip_elasticsearch
        and not has_elasticsearch_handler
    ):
        try:
            print(
                f"[ELASTICSEARCH] Attempting to add handler to {Config.ELASTICSEARCH_HOST}:{Config.ELASTICSEARCH_PORT}",
                file=sys.stderr,
            )
            # Test connection before adding handler to avoid spam
            es_client = Elasticsearch(
                [f"http://{Config.ELASTICSEARCH_HOST}:{Config.ELASTICSEARCH_PORT}"],
                verify_certs=False,
                ssl_show_warn=False,
                request_timeout=2,
                max_retries=0,
            )
            # Quick health check - if this fails, don't add the handler
            ping_result = es_client.ping(request_timeout=1)
            print(f"[ELASTICSEARCH] Ping result: {ping_result}", file=sys.stderr)
            if ping_result:
                es_handler = ElasticsearchHandler(es_client)
                es_handler.setLevel(getattr(logging, level.upper()))
                es_handler.setFormatter(formatter)
                root_logger.addHandler(es_handler)
                print(f"[ELASTICSEARCH] Handler added successfully", file=sys.stderr)
            else:
                print(
                    f"[ELASTICSEARCH] Ping failed, handler not added", file=sys.stderr
                )
        except Exception as e:
            # Log the error for troubleshooting (use print to avoid circular logging)
            # Don't break logging if Elasticsearch is not available
            import traceback

            print(f"[ELASTICSEARCH] Logging not available: {e}", file=sys.stderr)
            print(
                f"[ELASTICSEARCH] Traceback: {traceback.format_exc()}", file=sys.stderr
            )
            pass
    else:
        print(
            f"[ELASTICSEARCH] Skipping handler (AVAILABLE={ELASTICSEARCH_AVAILABLE}, skip={skip_elasticsearch}, has_handler={has_elasticsearch_handler})",
            file=sys.stderr,
        )

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
        self,
        message: str,
        project_iteration_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        **kwargs,
    ) -> str:
        """
        Format message with structured fields for Cloud Logging.
        Includes correlation_id at the beginning of the message for better tracing.

        For Cloud Logging to parse JSON automatically, we need to output the entire
        log entry as JSON. However, to maintain compatibility with the existing formatter,
        we'll include the structured fields in the message in a way that Cloud Logging
        can extract, while still showing the message in the log.

        We'll use a format that Cloud Logging can parse: include JSON at the start
        of the message, followed by the readable message.
        """
        # Prepend correlation_id to message if present
        formatted_message = message
        if correlation_id:
            formatted_message = f"[{correlation_id}] {message}"

        if project_iteration_id or correlation_id or kwargs:
            structured_data: Dict[str, Any] = {
                "message": formatted_message,
            }
            if project_iteration_id:
                structured_data["project_iteration_id"] = project_iteration_id
            if correlation_id:
                structured_data["correlation_id"] = correlation_id
            structured_data.update(kwargs)
            # Output JSON that Cloud Logging can parse
            # The CloudLoggingJSONFormatter will detect this and output proper JSON
            json_str = json.dumps(structured_data)
            return json_str
        return formatted_message

    def debug(
        self,
        message: str,
        project_iteration_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        **kwargs,
    ):
        """Log debug message with optional structured fields."""
        formatted = self._format_structured_message(
            message, project_iteration_id, correlation_id, **kwargs
        )
        self.logger.debug(formatted)

    def info(
        self,
        message: str,
        project_iteration_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        **kwargs,
    ):
        """Log info message with optional structured fields."""
        formatted = self._format_structured_message(
            message, project_iteration_id, correlation_id, **kwargs
        )
        self.logger.info(formatted)

    def warning(
        self,
        message: str,
        project_iteration_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        **kwargs,
    ):
        """Log warning message with optional structured fields."""
        formatted = self._format_structured_message(
            message, project_iteration_id, correlation_id, **kwargs
        )
        self.logger.warning(formatted)

    def error(
        self,
        message: str,
        project_iteration_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        exc_info: bool = False,
        **kwargs,
    ):
        """Log error message with optional structured fields."""
        formatted = self._format_structured_message(
            message, project_iteration_id, correlation_id, **kwargs
        )
        self.logger.error(formatted, exc_info=exc_info)

    def critical(
        self,
        message: str,
        project_iteration_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
        **kwargs,
    ):
        """Log critical message with optional structured fields."""
        formatted = self._format_structured_message(
            message, project_iteration_id, correlation_id, **kwargs
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


def log_info(
    message: str, correlation_id: str = "", logger_name: Optional[str] = None, **kwargs
):
    """
    Log an info message with correlation_id (always required, can be empty string).

    This function always uses structured logging with correlation_id.
    project_iteration_id should be passed as a kwarg, not in the message string.

    Args:
        message: The log message (should not include project_iteration_id in the string)
        correlation_id: Correlation_id for request tracing (required, can be empty string)
        logger_name: Optional logger name (defaults to caller's module name)
        **kwargs: Additional structured fields to include in the log (e.g., project_iteration_id)
    """
    import inspect

    # Get caller's module name if not provided
    if logger_name is None:
        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back
            logger_name = caller_frame.f_globals.get("__name__", "root")
        finally:
            del frame

    # Always use structured logger with correlation_id
    structured_logger = get_structured_logger(logger_name)
    structured_logger.info(message, correlation_id=correlation_id, **kwargs)


def log_warning(
    message: str, correlation_id: str = "", logger_name: Optional[str] = None, **kwargs
):
    """
    Log a warning message with correlation_id (always required, can be empty string).

    This function always uses structured logging with correlation_id.
    project_iteration_id should be passed as a kwarg, not in the message string.

    Args:
        message: The log message (should not include project_iteration_id in the string)
        correlation_id: Correlation_id for request tracing (required, can be empty string)
        logger_name: Optional logger name (defaults to caller's module name)
        **kwargs: Additional structured fields to include in the log (e.g., project_iteration_id)
    """
    import inspect

    # Get caller's module name if not provided
    if logger_name is None:
        frame = inspect.currentframe()
        try:
            caller_frame = frame.f_back
            logger_name = caller_frame.f_globals.get("__name__", "root")
        finally:
            del frame

    # Always use structured logger with correlation_id
    structured_logger = get_structured_logger(logger_name)
    structured_logger.warning(message, correlation_id=correlation_id, **kwargs)
