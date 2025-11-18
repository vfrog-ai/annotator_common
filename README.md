# annotator_common

Common utilities and shared code for all annotator services.

## Installation

Install from GitHub:

```bash
pip install git+https://github.com/vfrog-ai/annotator_common.git@v0.1.0
```

Or add to `requirements.txt`:

```
annotator-common @ git+https://github.com/vfrog-ai/annotator_common.git@v0.1.0
```

## Usage

```python
from annotator_common.config import Config
from annotator_common.database import init_database, get_database
from annotator_common.queue import get_async_queue_manager
from annotator_common.models.events import EventType, ProjectStatus
from annotator_common.logging import setup_logger
from annotator_common.matching import find_best_match
from annotator_common.annotation_utils import transform_annotations_for_supabase
from annotator_common.storage_base64 import load_image_as_base64
from annotator_common.storage_opencv import load_image_from_gcs_or_local, save_image_to_gcs_or_local
```

## Versioning

This package uses git tags for versioning. To install a specific version:

```bash
pip install git+https://github.com/vfrog-ai/annotator_common.git@v0.1.0
```

## Modules

- `config`: Configuration management
- `database`: MongoDB connection and utilities
- `queue`: RabbitMQ connection and queue management
- `models`: Event models and data structures
- `logging`: Logging configuration and utilities
- `matching`: Fuzzy matching utilities
- `annotation_utils`: Annotation processing utilities
- `storage_base64`: Image loading as base64 (for LLM APIs)
- `storage_opencv`: Image loading/saving with OpenCV (for image processing)
