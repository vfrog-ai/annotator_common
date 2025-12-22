# Firestore Migration - MongoDB Usage Inventory

This document captures the complete inventory of MongoDB usage patterns that need to be migrated to Firestore.

## Collections and Their Firestore Mappings

### 1. `project_iterations` → `project_iterations/{projectIterationId}`

**MongoDB Usage:**
- Primary document per project iteration
- Queries: `find_one({"project_iteration_id": ...})`
- Updates: `update_one()` with `$set`, `$inc`, `$setOnInsert`
- Creates: `insert_one()`

**Fields:**
- `project_iteration_id` (docId)
- `callback_url`
- `status` (enum: DOWNLOADING, CUTOUT_EXTRACTION, ANALYZING, ANNOTATING, COMPLETED, etc.)
- Counters: `total_product_images`, `total_dataset_images`, `total_cutouts`, `total_annotations`, `product_images_analyzed`, `total_cutouts_extracted`, `total_cutouts_analyzed`, `total_dataset_images_analyzed`, `total_dataset_images_extracted`, `total_product_images_downloaded`, `total_dataset_images_downloaded`
- Training fields (from inference-server): `message`, `trained_status`, `current_epoch`, `total_epochs`, `percentage`, `training_percentage`, `training_message`, `cls_loss`, `mAP50-95`, `map50_95`, `mAP50`, `map50`
- Timestamps: `created_at`, `updated_at`

**Firestore Path:** `project_iterations/{projectIterationId}` (root document)

---

### 2. `dataset_images` → `project_iterations/{projectIterationId}/dataset_images/{datasetImageId}`

**MongoDB Usage:**
- Queries: `find({"project_iteration_id": ..., "dataset_image_id": ...})`, `find_one()`, `count_documents()`
- Updates: `update_one()` with `$set` (status, cutout_count, annotation_completed)
- Creates: `insert_one()`
- Deletes: `delete_many({"project_iteration_id": ...})`

**Fields:**
- `dataset_image_id` (docId)
- `project_iteration_id`
- `url`
- `status` (pending, total_cutouts_extracted)
- `cutout_count` (optional, set when cutouts_ready event with count=0)
- `annotation_completed` (bool)
- Timestamps: `created_at`, `updated_at`

**Firestore Path:** `project_iterations/{projectIterationId}/dataset_images/{datasetImageId}`

**Unique Constraints:** None (docId is unique by design)

---

### 3. `product_images` → `project_iterations/{projectIterationId}/product_images/{productImageId}`

**MongoDB Usage:**
- Queries: `find({"project_iteration_id": ...})`, `find_one({"product_image_id": ..., "project_iteration_id": ...})`
- Updates: `update_one()` with `$set` (analysis, analysis_type, analyzed_at, analysis_error, analysis_status)
- Creates: `insert_one()`
- Deletes: `delete_many({"project_iteration_id": ...})`

**Fields:**
- `product_image_id` (docId)
- `project_iteration_id`
- `url`
- `label`
- `status` (pending, etc.)
- `analysis` (object, from image_analyzed events)
- `analysis_type`
- `analyzed_at`
- `analysis_error` (optional)
- `analysis_status` (optional: failed, completed)
- Timestamps: `created_at`

**Firestore Path:** `project_iterations/{projectIterationId}/product_images/{productImageId}`

**Unique Constraints:** None (docId is unique by design)

---

### 4. `cutouts` → `project_iterations/{projectIterationId}/cutouts/{cutoutId}`

**MongoDB Usage:**
- Queries: `find({"project_iteration_id": ..., "dataset_image_id": ...})`, `find_one()`, `count_documents()`
- Updates: `update_one()`, `update_many()` with `$addToSet` (analysis_types), `$pull` (analysis_types), `$set`
- Creates: `insert_one()`
- Aggregations: `aggregate()` with `$lookup` to join with `cutout_analysis` collection
- Deletes: `delete_many({"project_iteration_id": ...})`

**Fields:**
- `cutout_id` (docId, UUID generated)
- `project_iteration_id`
- `dataset_image_id`
- `product_image_id`
- `bbox` (object: x, y, width, height)
- `confidence`
- `class`
- `cutout_path`
- `cutout_number` (idx)
- `status` (extracted)
- `analysis_types` (array of strings, e.g. ["detailed"])
- Timestamps: `created_at`, `updated_at`

**Firestore Path:** `project_iterations/{projectIterationId}/cutouts/{cutoutId}`

**Complex Queries:**
- Aggregation pipeline in `annotator_project_manager/main.py:646-675` joins `cutouts` with `cutout_analysis` to count analyzed cutouts. In Firestore, this will be done by querying the subcollection directly.

---

### 5. `cutout_analysis` → `project_iterations/{projectIterationId}/cutout_analyses/{cutoutId__analysisType}`

**MongoDB Usage:**
- Queries: `find_one({"cutout_id": ..., "project_iteration_id": ..., "analysis_type": ...})`, `count_documents()`
- Updates: `update_one()` with `upsert=True` (unique on cutout_id + project_iteration_id + analysis_type)
- Deletes: `delete_many({"project_iteration_id": ...})`

**Fields:**
- `cutout_analysis_id` (generated UUID, but not used as unique key)
- `cutout_id` (part of docId)
- `project_iteration_id`
- `analysis_type` (part of docId: "initial", "detailed")
- `image_type` ("cutout")
- `dataset_image_id`
- `product_image_id`
- `analysis_result` (object, LLM response)
- `processor_id`
- `status` (completed, failed)
- `error` (optional string)
- `cutout_path`, `cutout_filename`, `cutout_url` (debug fields)
- Timestamps: `created_at`, `updated_at`

**Firestore Path:** `project_iterations/{projectIterationId}/cutout_analyses/{cutoutId__analysisType}`

**Unique Constraints:** Replaced by deterministic docId: `${cutoutId}__${analysisType}`

---

### 6. `annotations` → `project_iterations/{projectIterationId}/annotated_images/{datasetImageId}/cutouts/{cutoutId}`

**MongoDB Usage:**
- Queries: `find({"project_iteration_id": ..., "dataset_image_id": ...})`, `distinct("cutout_id", {...})`
- Updates: `bulk_write()` with `UpdateOne` and `upsert=True` (unique on cutout_id + project_iteration_id)
- Deletes: `delete_many({"project_iteration_id": ...})`

**Fields:**
- `annotation_id` (generated UUID, but unique key is cutout_id + project_iteration_id)
- `project_iteration_id`
- `cutout_id` (docId in subcollection)
- `product_image_id`
- `dataset_image_id` (parent docId)
- `label`
- `bbox` (object)
- `match_score` (similarity score)
- `similarity_data` (object, detailed matching data)
- `color_primary`, `colors_secondary`
- `status` (completed)
- Timestamps: `created_at`, `updated_at`

**Firestore Path:** 
- Summary: `project_iterations/{projectIterationId}/annotated_images/{datasetImageId}` (metadata doc)
- Items: `project_iterations/{projectIterationId}/annotated_images/{datasetImageId}/cutouts/{cutoutId}` (per-cutout annotation)

**Note:** The summary doc at `annotated_images/{datasetImageId}` should store:
- `projectIterationId`
- `datasetId` (datasetImageId)
- `productImageId`
- `annotation_completed` (bool)
- `annotations_count` (denormalized count)
- `created_at`, `updated_at`

**Unique Constraints:** Replaced by deterministic docId: `cutoutId` (unique per datasetImageId parent)

---

### 7. `processed_events` → `project_iterations/{projectIterationId}/processed_events/{eventId}`

**MongoDB Usage:**
- Queries: `find_one()` with composite filter based on event_type
- Updates: `update_one()` with `upsert=True`, `$setOnInsert`
- Deletes: `delete_many({"project_iteration_id": ...})`

**Event Types and Composite Keys:**
1. **`image_downloaded` (product)**: `event_type + project_iteration_id + image_type("product") + product_image_id`
   - DocId: `image_downloaded__product__{productImageId}`
2. **`image_downloaded` (dataset)**: `event_type + project_iteration_id + image_type("dataset") + dataset_image_id`
   - DocId: `image_downloaded__dataset__{datasetImageId}`
3. **`cutouts_ready`**: `event_type + project_iteration_id + dataset_image_id`
   - DocId: `cutouts_ready__{datasetImageId}`
4. **`product_image_analyzed`**: `event_type + project_iteration_id + image_type("product") + product_image_id + analysis_type`
   - DocId: `product_image_analyzed__{productImageId}__{analysisType}`
5. **`dataset_image_analyzed`** (cutout analysis): `event_type + project_iteration_id + image_type("cutout") + cutout_id + analysis_type`
   - DocId: `dataset_image_analyzed__{cutoutId}__{analysisType}`
6. **`annotation_created`**: `event_type + project_iteration_id + dataset_image_id`
   - DocId: `annotation_created__{datasetImageId}`
7. **`start_project_iteration`**: `event_type + project_iteration_id`
   - DocId: `start_project_iteration__{projectIterationId}`
8. **`annotate_dataset`**: `event_type + project_iteration_id + dataset_image_id`
   - DocId: `annotate_dataset__{datasetImageId}`

**Fields:**
- `event_type` (part of docId)
- `project_iteration_id`
- `correlation_id`
- Additional fields vary by event_type (see above)
- `processed_at`
- `created_at`

**Firestore Path:** `project_iterations/{projectIterationId}/processed_events/{eventId}`

**Unique Constraints:** Replaced by deterministic docId rules above

---

### 8. `modal_billing` → `modal_billing/{date__functionName__environment}` (GLOBAL)

**MongoDB Usage:**
- Queries: Query by `date`, `function_name`, `environment`
- Updates: `update_one()` with `upsert=True`, `$inc`, `$set`, `$setOnInsert` (unique on date + function_name + environment)
- Used in: `inference-server/modal_tasks.py`, `annotator_api_service/main.py` (usage dashboard)

**Fields:**
- `date` (datetime, midnight UTC)
- `function_name` (train_model, run_inference)
- `environment` (staging, production)
- `requests` (incremented)
- `cost_usd` (incremented)
- `gpu_hours`, `cpu_hours`, `memory_gb_hours` (incremented)
- `gpu_type`
- `metadata` (object: cpu_cores, memory_gb)
- Timestamps: `created_at`, `updated_at`

**Firestore Path:** `modal_billing/{date__functionName__environment}` (global collection, not scoped to project_iteration)

**Unique Constraints:** Replaced by deterministic docId: `${date.toISOString().split('T')[0]}__${functionName}__${environment}`

---

### 9. `usage_dashboard_cache` → `usage_dashboard_cache/{cacheKey}` (GLOBAL)

**MongoDB Usage:**
- Queries: `find_one({"cache_key": ...})`
- Creates: `insert_one()`
- Used in: `annotator_api_service/main.py` (usage dashboard endpoint)

**Fields:**
- `cache_key` (docId, format: `usage_dashboard_{startDate}_{endDate}`)
- `data` (object, cached dashboard data)
- `created_at`

**Firestore Path:** `usage_dashboard_cache/{cacheKey}` (global collection)

---

### 10. `analysis_config` / `model_config` → `analysis_config/{configId}` (GLOBAL) or `project_iterations/{projectIterationId}/configs/{configId}`

**MongoDB Usage:**
- Queries: `find({"active": True})`, `find({})`, `count_documents()`
- Used in: `annotator_image_analysis_service/main.py` (processor manager)
- Note: Currently global, but could be iteration-scoped if needed

**Fields:**
- `config_id` (docId)
- `active` (bool)
- Processor configuration fields (varies)

**Firestore Path:** 
- Option A (global): `analysis_config/{configId}`
- Option B (scoped): `project_iterations/{projectIterationId}/configs/{configId}`

**Decision Needed:** Keep global for now unless requirements specify per-iteration configs.

---

### 11. `detections` → `project_iterations/{projectIterationId}/detections/{detectionId}`

**MongoDB Usage:**
- Queries: `find({"project_iteration_id": ..., "dataset_images_id": ...})`
- Used in: `annotator_api_service/main.py` (status endpoint)

**Fields:**
- `project_iteration_id`
- `dataset_images_id`
- Detection result fields (TBD based on usage)

**Firestore Path:** `project_iterations/{projectIterationId}/detections/{detectionId}`

**Note:** This collection is referenced but usage patterns need verification.

---

### 12. `image_product_comparisons` → `project_iterations/{projectIterationId}/comparisons/{comparisonId}`

**MongoDB Usage:**
- Creates: `insert_one()`
- Used in: `annotator_image_analysis_service/main.py`

**Fields:**
- TBD (needs verification)

**Firestore Path:** `project_iterations/{projectIterationId}/comparisons/{comparisonId}` (if iteration-scoped) or global if cross-iteration

---

## Query Patterns to Replicate in Firestore

### Simple Queries
- `find_one({"field": value})` → `.document(path).get()`
- `find({"field": value})` → `.where("field", "==", value).stream()`
- `count_documents({"field": value})` → `.where("field", "==", value).count()`

### Complex Queries
1. **Aggregation with $lookup** (cutouts + cutout_analysis): Replace with direct subcollection query
2. **Bulk writes**: Use Firestore batch writes
3. **Distinct**: Query and de-duplicate in application code
4. **Updates with $inc**: Use transactions: read, increment, write
5. **Updates with $addToSet/$pull**: Use transactions: read array, modify, write
6. **Upserts**: Use `.set()` with merge or transactions

### Transactions
- Multi-document updates (e.g., update project_iteration + dataset_image) → Firestore transactions
- Idempotency checks + writes → Firestore transactions

---

## Index Mapping

MongoDB compound indexes are replaced by:
1. **Deterministic document IDs** for unique constraints
2. **Single-field indexes** in Firestore (created automatically for queryable fields)
3. **Composite indexes** (created in Firestore console/CLI for compound queries)

---

## Migration Priority

Based on dependencies and usage:

1. **High Priority** (core workflow):
   - `project_iterations`
   - `dataset_images`
   - `product_images`
   - `cutouts`
   - `cutout_analyses`
   - `annotations` / `annotated_images`
   - `processed_events`

2. **Medium Priority** (supporting features):
   - `detections`
   - `image_product_comparisons`

3. **Low Priority** (administrative/cross-cutting):
   - `modal_billing` (global)
   - `usage_dashboard_cache` (global)
   - `analysis_config` (global)

