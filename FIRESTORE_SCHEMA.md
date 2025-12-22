# Firestore Schema Definition

This document defines the complete Firestore data model for the migration from MongoDB.

## Root Structure

All iteration-scoped data is organized under:
```
project_iterations/{projectIterationId}/
```

Global collections (cross-iteration) are at the root level:
```
modal_billing/{...}
usage_dashboard_cache/{...}
analysis_config/{...}
```

---

## Collection: `project_iterations/{projectIterationId}`

**Type:** Root document

**Document ID:** `projectIterationId` (string, provided by client)

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `project_iteration_id` | string | Yes | Same as docId (denormalized for queries) |
| `callback_url` | string | No | Optional webhook callback URL |
| `status` | string | Yes | Enum: DOWNLOADING, CUTOUT_EXTRACTION, ANALYZING, ANNOTATING, COMPLETED, FAILED |
| `total_product_images` | integer | Yes | Total number of product images |
| `total_dataset_images` | integer | Yes | Total number of dataset images |
| `total_cutouts` | integer | Yes | Total cutouts extracted |
| `total_annotations` | integer | Yes | Total annotations created |
| `product_images_analyzed` | integer | Yes | Count of analyzed product images |
| `total_cutouts_extracted` | integer | Yes | Count of extracted cutouts |
| `total_cutouts_analyzed` | integer | Yes | Count of analyzed cutouts |
| `total_dataset_images_analyzed` | integer | Yes | Count of analyzed dataset images |
| `total_dataset_images_extracted` | integer | Yes | Count of dataset images with extracted cutouts |
| `total_product_images_downloaded` | integer | Yes | Count of downloaded product images |
| `total_dataset_images_downloaded` | integer | Yes | Count of downloaded dataset images |
| `message` | string | No | Status message (for training/inference progress) |
| `trained_status` | string | No | Training status (e.g., "saving_models", "completed") |
| `current_epoch` | integer | No | Current training epoch |
| `total_epochs` | integer | No | Total training epochs |
| `percentage` | integer | No | Completion percentage (0-100) |
| `training_percentage` | integer | No | Training completion percentage |
| `training_message` | string | No | Training status message |
| `cls_loss` | float | No | Classification loss (training metric) |
| `mAP50-95` | float | No | Mean Average Precision 50-95 |
| `map50_95` | float | No | Alias for mAP50-95 |
| `mAP50` | float | No | Mean Average Precision at IoU 0.50 |
| `map50` | float | No | Alias for mAP50 |
| `current_image` | integer | No | Current image being processed (inference) |
| `total_images` | integer | No | Total images to process (inference) |
| `created_at` | timestamp | Yes | Creation timestamp (server timestamp) |
| `updated_at` | timestamp | Yes | Last update timestamp (server timestamp) |

**Indexes:**
- `status` (for querying by status)
- `created_at` (for ordering)
- `project_iteration_id` (implicit via docId)

---

## Collection: `project_iterations/{projectIterationId}/dataset_images/{datasetImageId}`

**Type:** Subcollection document

**Document ID:** `datasetImageId` (string, provided by client)

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `dataset_image_id` | string | Yes | Same as docId |
| `project_iteration_id` | string | Yes | Parent project iteration ID |
| `url` | string | Yes | Image URL |
| `status` | string | Yes | Enum: pending, total_cutouts_extracted |
| `cutout_count` | integer | No | Number of cutouts extracted (0 if none) |
| `annotation_completed` | boolean | No | Whether annotation is complete |
| `created_at` | timestamp | Yes | Creation timestamp |
| `updated_at` | timestamp | Yes | Last update timestamp |

**Indexes:**
- `project_iteration_id` (for listing all datasets in an iteration)
- `status` (for filtering by status)
- `annotation_completed` (for filtering completed annotations)

---

## Collection: `project_iterations/{projectIterationId}/product_images/{productImageId}`

**Type:** Subcollection document

**Document ID:** `productImageId` (string, provided by client)

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `product_image_id` | string | Yes | Same as docId |
| `project_iteration_id` | string | Yes | Parent project iteration ID |
| `url` | string | Yes | Image URL |
| `label` | string | Yes | Product label |
| `status` | string | Yes | Enum: pending, analyzed, failed |
| `analysis` | map | No | LLM analysis result (object) |
| `analysis_type` | string | No | Type of analysis performed |
| `analyzed_at` | timestamp | No | Analysis timestamp |
| `analysis_error` | string | No | Error message if analysis failed |
| `analysis_status` | string | No | Status: completed, failed |
| `created_at` | timestamp | Yes | Creation timestamp |

**Indexes:**
- `project_iteration_id` (for listing all products in an iteration)
- `status` (for filtering by status)
- `analysis_type` (for filtering by analysis type)

---

## Collection: `project_iterations/{projectIterationId}/cutouts/{cutoutId}`

**Type:** Subcollection document

**Document ID:** `cutoutId` (string, UUID generated)

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cutout_id` | string | Yes | Same as docId |
| `project_iteration_id` | string | Yes | Parent project iteration ID |
| `dataset_image_id` | string | Yes | Parent dataset image ID |
| `product_image_id` | string | Yes | Associated product image ID |
| `bbox` | map | Yes | Bounding box: `{x: int, y: int, width: int, height: int}` |
| `confidence` | float | Yes | Detection confidence score |
| `class` | integer | Yes | YOLO class ID |
| `cutout_path` | string | Yes | Path to cutout image file |
| `cutout_number` | integer | Yes | Sequential cutout number/index |
| `status` | string | Yes | Enum: extracted |
| `analysis_types` | array<string> | Yes | Array of analysis types requested (e.g., ["detailed"]) |
| `created_at` | timestamp | Yes | Creation timestamp |
| `updated_at` | timestamp | Yes | Last update timestamp |

**Indexes:**
- `project_iteration_id` (for listing all cutouts in an iteration)
- `dataset_image_id` (for listing cutouts per dataset image)
- `project_iteration_id, dataset_image_id` (composite, for common query pattern)

---

## Collection: `project_iterations/{projectIterationId}/cutout_analyses/{cutoutId__analysisType}`

**Type:** Subcollection document

**Document ID:** `${cutoutId}__${analysisType}` (deterministic, replaces compound unique index)

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cutout_analysis_id` | string | Yes | Generated UUID (for reference) |
| `cutout_id` | string | Yes | Parent cutout ID (part of docId) |
| `project_iteration_id` | string | Yes | Parent project iteration ID |
| `analysis_type` | string | Yes | Type: "initial", "detailed" (part of docId) |
| `image_type` | string | Yes | Always "cutout" |
| `dataset_image_id` | string | Yes | Parent dataset image ID |
| `product_image_id` | string | Yes | Associated product image ID |
| `analysis_result` | map | Yes | LLM analysis result (object) |
| `processor_id` | string | Yes | Processor config ID used |
| `status` | string | Yes | Enum: completed, failed |
| `error` | string | No | Error message if failed |
| `cutout_path` | string | No | Debug: cutout file path |
| `cutout_filename` | string | No | Debug: cutout filename |
| `cutout_url` | string | No | Debug: cutout URL |
| `created_at` | timestamp | Yes | Creation timestamp |
| `updated_at` | timestamp | Yes | Last update timestamp |

**Indexes:**
- `project_iteration_id` (for listing all analyses in an iteration)
- `cutout_id` (for listing analyses per cutout)
- `dataset_image_id` (for listing analyses per dataset image)
- `analysis_type` (for filtering by analysis type)
- `project_iteration_id, dataset_image_id, analysis_type` (composite, for common query pattern)

---

## Collection: `project_iterations/{projectIterationId}/annotated_images/{datasetImageId}`

**Type:** Subcollection document (summary/metadata)

**Document ID:** `datasetImageId` (string, same as dataset_image_id)

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `project_iteration_id` | string | Yes | Parent project iteration ID |
| `dataset_image_id` | string | Yes | Same as docId |
| `product_image_id` | string | Yes | Associated product image ID |
| `annotation_completed` | boolean | Yes | Whether annotation is complete |
| `annotations_count` | integer | Yes | Denormalized count of annotation items |
| `created_at` | timestamp | Yes | Creation timestamp |
| `updated_at` | timestamp | Yes | Last update timestamp |

**Indexes:**
- `project_iteration_id` (for listing all annotated images in an iteration)
- `annotation_completed` (for filtering completed annotations)
- `product_image_id` (for listing annotations per product)

---

## Subcollection: `project_iterations/{projectIterationId}/annotated_images/{datasetImageId}/cutouts/{cutoutId}`

**Type:** Nested subcollection document

**Document ID:** `cutoutId` (string, same as cutout.cutout_id)

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `annotation_id` | string | Yes | Generated UUID (for reference) |
| `project_iteration_id` | string | Yes | Parent project iteration ID |
| `cutout_id` | string | Yes | Same as docId |
| `product_image_id` | string | Yes | Matched product image ID |
| `dataset_image_id` | string | Yes | Parent dataset image ID |
| `label` | string | Yes | Matched product label |
| `bbox` | map | Yes | Bounding box: `{x: int, y: int, width: int, height: int}` |
| `match_score` | float | Yes | Similarity/match score |
| `similarity_data` | map | Yes | Detailed matching data (object) |
| `color_primary` | string | No | Primary color detected |
| `colors_secondary` | array<string> | No | Secondary colors detected |
| `status` | string | Yes | Enum: completed |
| `created_at` | timestamp | Yes | Creation timestamp |
| `updated_at` | timestamp | Yes | Last update timestamp |

**Indexes:**
- `cutout_id` (implicit via docId)
- `product_image_id` (for listing annotations per product)

---

## Collection: `project_iterations/{projectIterationId}/processed_events/{eventId}`

**Type:** Subcollection document

**Document ID:** Deterministic composite key (see mapping below)

**Event Type → Document ID Mapping:**

| Event Type | DocId Pattern | Example |
|------------|---------------|---------|
| `image_downloaded` (product) | `image_downloaded__product__{productImageId}` | `image_downloaded__product__prod123` |
| `image_downloaded` (dataset) | `image_downloaded__dataset__{datasetImageId}` | `image_downloaded__dataset__ds456` |
| `cutouts_ready` | `cutouts_ready__{datasetImageId}` | `cutouts_ready__ds456` |
| `product_image_analyzed` | `product_image_analyzed__{productImageId}__{analysisType}` | `product_image_analyzed__prod123__initial` |
| `dataset_image_analyzed` | `dataset_image_analyzed__{cutoutId}__{analysisType}` | `dataset_image_analyzed__cut789__detailed` |
| `annotation_created` | `annotation_created__{datasetImageId}` | `annotation_created__ds456` |
| `start_project_iteration` | `start_project_iteration__{projectIterationId}` | `start_project_iteration__proj001` |
| `annotate_dataset` | `annotate_dataset__{datasetImageId}` | `annotate_dataset__ds456` |

**Common Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `event_type` | string | Yes | Event type (from mapping above) |
| `project_iteration_id` | string | Yes | Parent project iteration ID |
| `correlation_id` | string | Yes | Correlation ID for tracing |
| `processed_at` | timestamp | Yes | Processing timestamp |
| `created_at` | timestamp | Yes | Creation timestamp |

**Event-Specific Fields:**

- `image_downloaded` (product): `image_type="product"`, `product_image_id`
- `image_downloaded` (dataset): `image_type="dataset"`, `dataset_image_id`
- `cutouts_ready`: `dataset_image_id`, `product_image_id` (optional)
- `product_image_analyzed`: `image_type="product"`, `product_image_id`, `analysis_type`
- `dataset_image_analyzed`: `image_type="cutout"`, `cutout_id`, `analysis_type`
- `annotation_created`: `dataset_image_id`, `product_image_id`, `label`
- `start_project_iteration`: (no additional fields)
- `annotate_dataset`: `dataset_image_id`, `product_image_id` (optional)

**Indexes:**
- `project_iteration_id` (for listing all events in an iteration)
- `event_type` (for filtering by event type)
- `correlation_id` (for tracing requests)

---

## Collection: `modal_billing/{date__functionName__environment}` (GLOBAL)

**Type:** Root collection document

**Document ID:** `${date.toISOString().split('T')[0]}__${functionName}__${environment}`

Example: `2025-01-31__train_model__staging`

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `date` | timestamp | Yes | Date at midnight UTC |
| `function_name` | string | Yes | Modal function name (train_model, run_inference) |
| `environment` | string | Yes | Environment: staging, production |
| `requests` | integer | Yes | Number of function calls (incremented) |
| `cost_usd` | float | Yes | Total cost in USD (incremented) |
| `gpu_hours` | float | Yes | Total GPU hours (incremented) |
| `cpu_hours` | float | Yes | Total CPU hours (incremented) |
| `memory_gb_hours` | float | Yes | Total memory GB-hours (incremented) |
| `gpu_type` | string | Yes | GPU type (e.g., "A100-80GB") |
| `metadata` | map | No | Additional metadata: `{cpu_cores: float, memory_gb: float}` |
| `created_at` | timestamp | Yes | Creation timestamp |
| `updated_at` | timestamp | Yes | Last update timestamp |

**Indexes:**
- `date` (for querying by date range)
- `function_name` (for filtering by function)
- `environment` (for filtering by environment)
- `date, function_name, environment` (composite, for unique constraint queries)

---

## Collection: `usage_dashboard_cache/{cacheKey}` (GLOBAL)

**Type:** Root collection document

**Document ID:** `cacheKey` (string, format: `usage_dashboard_{startDate}_{endDate}`)

Example: `usage_dashboard_2025-01-01_2025-01-31`

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `cache_key` | string | Yes | Same as docId |
| `data` | map | Yes | Cached dashboard data (object) |
| `created_at` | timestamp | Yes | Creation timestamp |

**Indexes:**
- `cache_key` (implicit via docId)

---

## Collection: `analysis_config/{configId}` (GLOBAL)

**Type:** Root collection document

**Document ID:** `configId` (string)

**Fields:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `config_id` | string | Yes | Same as docId |
| `active` | boolean | Yes | Whether config is active |
| `processor_id` | string | Yes | Processor identifier |
| `host` | string | Yes | Processor host |
| `port` | integer | Yes | Processor port |
| `model_name` | string | Yes | Model name |
| Additional processor-specific fields | varies | No | TBD based on processor requirements |

**Indexes:**
- `active` (for querying active configs)
- `config_id` (implicit via docId)

---

## Timestamp Handling

- Use Firestore `SERVER_TIMESTAMP` for `created_at` and `updated_at` fields
- In Python SDK: `firestore.SERVER_TIMESTAMP` or `datetime.utcnow()` (convert to Firestore Timestamp)

---

## Document Size Limits

- Firestore documents have a **1 MiB size limit**
- Large arrays (e.g., many cutouts) should be stored in subcollections
- `annotated_images/{datasetImageId}/cutouts/...` pattern avoids exceeding limits

---

## Query Patterns

### List all datasets in a project iteration:
```python
collection_ref = db.collection('project_iterations').document(project_iteration_id).collection('dataset_images')
docs = collection_ref.where('project_iteration_id', '==', project_iteration_id).stream()
```

### List all cutouts for a dataset image:
```python
collection_ref = db.collection('project_iterations').document(project_iteration_id).collection('cutouts')
docs = collection_ref.where('dataset_image_id', '==', dataset_image_id).stream()
```

### Get analyzed cutouts count (replaces aggregation):
```python
collection_ref = db.collection('project_iterations').document(project_iteration_id).collection('cutout_analyses')
docs = collection_ref.where('dataset_image_id', '==', dataset_image_id).where('analysis_type', '==', 'detailed').stream()
count = len(list(docs))
```

### Transactions:
- Use for multi-document updates (e.g., update project_iteration + dataset_image)
- Use for idempotency checks + writes

