# Structured Logging for Google Cloud Logging

This package provides structured logging support that allows filtering logs by `project_iteration_id` in Google Cloud Logging Explorer.

## Usage

### Basic Usage

Instead of using the regular logger, use `get_structured_logger`:

```python
from annotator_common.logging import get_structured_logger

logger = get_structured_logger(__name__)

# Log with project_iteration_id - this will be filterable in Cloud Logging
logger.info(
    "Processing image download",
    project_iteration_id="project-123"
)
```

### Filtering in Google Cloud Logging Explorer

After using structured logging, you can filter logs in Cloud Logging Explorer using:

```
jsonPayload.project_iteration_id="project-123"
```

Or in the query builder:
- Field: `jsonPayload.project_iteration_id`
- Operator: `=`
- Value: `project-123`

### Additional Fields

You can also add custom fields:

```python
logger.info(
    "Image processed successfully",
    project_iteration_id="project-123",
    image_id="img-456",
    status="completed"
)
```

These will all be available as `jsonPayload.image_id`, `jsonPayload.status`, etc.

### Migration Example

**Before:**
```python
from annotator_common.logging import setup_logger

logger = setup_logger(Config.SERVICE_NAME, Config.LOG_LEVEL)
logger.info(f"Processing image: project_iteration_id={project_iteration_id}")
```

**After:**
```python
from annotator_common.logging import get_structured_logger

logger = get_structured_logger(__name__)
logger.info(
    "Processing image",
    project_iteration_id=project_iteration_id
)
```

## Benefits

1. **Filterable in Cloud Logging**: All logs with `project_iteration_id` can be easily filtered
2. **Structured Data**: JSON format makes it easy to query and analyze
3. **Backward Compatible**: If `project_iteration_id` is not provided, logs work normally
4. **Additional Fields**: Can add any custom fields for filtering

## Notes

- When `project_iteration_id` is provided, the log message is formatted as JSON
- When `project_iteration_id` is not provided, the log message is sent as plain text (backward compatible)
- Cloud Logging automatically parses JSON in log messages and makes fields available for filtering

