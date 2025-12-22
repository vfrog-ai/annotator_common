# MongoDB to Firestore Migration Guide

This guide shows how to migrate services from MongoDB to Firestore using the repository layer.

## Overview

The migration replaces direct MongoDB calls (`db.collection.*`) with Firestore repository methods. The repository layer provides a similar API to minimize code changes.

## Setup

### 1. Initialize Firestore in your service

```python
from annotator_common.firestore import init_firestore

# Initialize at service startup
init_firestore()
```

### 2. Import repositories

```python
from annotator_common.firestore import (
    ProjectIterationRepository,
    DatasetImageRepository,
    ProductImageRepository,
    CutoutRepository,
    CutoutAnalysisRepository,
    ProcessedEventRepository,
    AnnotatedImageRepository,
)

# Create repository instances
project_repo = ProjectIterationRepository()
dataset_repo = DatasetImageRepository()
product_repo = ProductImageRepository()
cutout_repo = CutoutRepository()
cutout_analysis_repo = CutoutAnalysisRepository()
processed_event_repo = ProcessedEventRepository()
annotated_image_repo = AnnotatedImageRepository()
```

## Migration Patterns

### Pattern 1: Simple Queries

**MongoDB:**
```python
project = db.project_iterations.find_one({"project_iteration_id": project_iteration_id})
```

**Firestore:**
```python
project = project_repo.get_by_id(project_iteration_id)
```

---

### Pattern 2: List Queries

**MongoDB:**
```python
cutouts = list(db.cutouts.find({
    "project_iteration_id": project_iteration_id,
    "dataset_image_id": dataset_image_id,
}))
```

**Firestore:**
```python
cutouts = cutout_repo.list_by_dataset_image(project_iteration_id, dataset_image_id)
```

---

### Pattern 3: Count Queries

**MongoDB:**
```python
total_cutouts = db.cutouts.count_documents({
    "project_iteration_id": project_iteration_id,
    "dataset_image_id": dataset_image_id,
})
```

**Firestore:**
```python
total_cutouts = cutout_repo.count_by_dataset_image(project_iteration_id, dataset_image_id)
```

---

### Pattern 4: Create Operations

**MongoDB:**
```python
db.dataset_images.insert_one({
    "dataset_image_id": dataset_image_id,
    "project_iteration_id": project_iteration_id,
    "url": url,
    "status": "pending",
    "created_at": datetime.utcnow(),
})
```

**Firestore:**
```python
dataset_repo.create(project_iteration_id, dataset_image_id, {
    "url": url,
    "status": "pending",
    "created_at": datetime.utcnow(),
})
```

---

### Pattern 5: Update Operations

**MongoDB:**
```python
db.project_iterations.update_one(
    {"project_iteration_id": project_iteration_id},
    {
        "$set": {
            "status": "completed",
            "updated_at": datetime.utcnow(),
        }
    }
)
```

**Firestore:**
```python
project_repo.update(project_iteration_id, {
    "status": "completed",
    "updated_at": datetime.utcnow(),
})
```

---

### Pattern 6: Increment Operations

**MongoDB:**
```python
db.project_iterations.update_one(
    {"project_iteration_id": project_iteration_id},
    {
        "$inc": {
            "total_cutouts": 1,
            "total_cutouts_extracted": 1,
        },
        "$set": {"updated_at": datetime.utcnow()},
    }
)
```

**Firestore:**
```python
project_repo.increment_fields(project_iteration_id, {
    "total_cutouts": 1,
    "total_cutouts_extracted": 1,
})
```

---

### Pattern 7: Array Operations ($addToSet)

**MongoDB:**
```python
db.cutouts.update_many(
    {
        "cutout_id": {"$in": cutout_ids},
        "project_iteration_id": project_iteration_id,
    },
    {
        "$addToSet": {"analysis_types": analysis_type},
        "$set": {"updated_at": datetime.utcnow()},
    }
)
```

**Firestore:**
```python
cutout_repo.update_many(
    project_iteration_id,
    {
        "cutout_id": {"$in": cutout_ids},  # Repository handles $in
        "project_iteration_id": project_iteration_id,
    },
    {
        "$addToSet": {"analysis_types": analysis_type},  # Repository handles $addToSet
        "updated_at": datetime.utcnow(),
    }
)
```

---

### Pattern 8: Upsert Operations

**MongoDB:**
```python
db.cutout_analysis.update_one(
    {
        "cutout_id": cutout_id,
        "project_iteration_id": project_iteration_id,
        "analysis_type": analysis_type,
    },
    {"$set": analysis_doc},
    upsert=True
)
```

**Firestore:**
```python
cutout_analysis_repo.create_or_update(
    project_iteration_id,
    cutout_id,
    analysis_type,
    analysis_doc
)
```

---

### Pattern 9: Idempotency Checks

**MongoDB:**
```python
existing = db.processed_events.find_one(filter_doc)
if existing:
    return True  # Already processed

db.processed_events.update_one(
    filter_doc,
    {"$setOnInsert": insert_doc},
    upsert=True
)
```

**Firestore:**
```python
if processed_event_repo.is_processed(event_type, event_data):
    return True  # Already processed

processed_event_repo.mark_processed(event_type, event_data)
```

---

### Pattern 10: Bulk Operations

**MongoDB:**
```python
bulk_operations = []
for annotation_doc in annotations_data:
    bulk_operations.append(
        UpdateOne(
            {"cutout_id": annotation_doc["cutout_id"], "project_iteration_id": project_iteration_id},
            {"$set": annotation_doc},
            upsert=True
        )
    )
result = db.annotations.bulk_write(bulk_operations, ordered=False)
```

**Firestore:**
```python
annotated_image_repo.bulk_write_annotations(
    project_iteration_id,
    dataset_image_id,
    annotations_data
)
```

---

### Pattern 11: Distinct Queries

**MongoDB:**
```python
cutout_ids = db.annotations.distinct(
    "cutout_id",
    {
        "project_iteration_id": project_iteration_id,
        "dataset_image_id": dataset_image_id,
    }
)
```

**Firestore:**
```python
cutout_ids = annotated_image_repo.get_distinct_cutout_ids(
    project_iteration_id,
    dataset_image_id
)
```

---

### Pattern 12: Aggregation Queries

**MongoDB:**
```python
pipeline = [
    {"$match": {"project_iteration_id": project_iteration_id, "dataset_image_id": dataset_image_id}},
    {"$lookup": {...}},
    {"$count": "analyzed_count"},
]
result = list(db.cutouts.aggregate(pipeline))
```

**Firestore:**
```python
# Replace aggregation with direct subcollection query
analyzed_count = cutout_analysis_repo.count_by_dataset_image(
    project_iteration_id,
    dataset_image_id,
    analysis_type="detailed"
)
```

---

### Pattern 13: Transactions

**MongoDB:**
```python
with db.client.start_session() as session:
    with session.start_transaction():
        db.project_iterations.update_one(..., session=session)
        db.dataset_images.update_one(..., session=session)
```

**Firestore:**
```python
transaction = client.transaction()
project_repo.update(project_iteration_id, updates1, transaction=transaction)
dataset_repo.update(project_iteration_id, dataset_image_id, updates2, transaction=transaction)
transaction.commit()
```

Or using Firestore client directly:
```python
@firestore.transactional
def update_multiple_docs(transaction):
    project_repo.update(project_iteration_id, updates1, transaction=transaction)
    dataset_repo.update(project_iteration_id, dataset_image_id, updates2, transaction=transaction)

transaction = client.transaction()
update_multiple_docs(transaction)
```

---

## Complete Example: Migrating a Handler

### Before (MongoDB):

```python
async def handle_start_project_iteration(event: dict):
    project_iteration_id = event.get("project_iteration_id")
    
    # Create project
    project_doc = {
        "project_iteration_id": project_iteration_id,
        "status": "DOWNLOADING",
        "total_product_images": 1,
        "total_dataset_images": len(dataset_images),
        "created_at": datetime.utcnow(),
    }
    db.project_iterations.insert_one(project_doc)
    
    # Store product image
    db.product_images.insert_one({
        "product_image_id": product_image.get("id"),
        "project_iteration_id": project_iteration_id,
        "url": str(product_image.get("image_url")),
        "created_at": datetime.utcnow(),
    })
    
    # Store dataset images
    for dataset_image in dataset_images:
        db.dataset_images.insert_one({
            "dataset_image_id": dataset_image.get("id"),
            "project_iteration_id": project_iteration_id,
            "url": str(dataset_image.get("image_url")),
            "created_at": datetime.utcnow(),
        })
```

### After (Firestore):

```python
from annotator_common.firestore import (
    init_firestore,
    ProjectIterationRepository,
    ProductImageRepository,
    DatasetImageRepository,
)

# Initialize at module level or service startup
init_firestore()
project_repo = ProjectIterationRepository()
product_repo = ProductImageRepository()
dataset_repo = DatasetImageRepository()

async def handle_start_project_iteration(event: dict):
    project_iteration_id = event.get("project_iteration_id")
    
    # Create project
    project_repo.create(project_iteration_id, {
        "project_iteration_id": project_iteration_id,
        "status": "DOWNLOADING",
        "total_product_images": 1,
        "total_dataset_images": len(dataset_images),
        "created_at": datetime.utcnow(),
    })
    
    # Store product image
    product_repo.create(project_iteration_id, product_image.get("id"), {
        "product_image_id": product_image.get("id"),
        "project_iteration_id": project_iteration_id,
        "url": str(product_image.get("image_url")),
        "created_at": datetime.utcnow(),
    })
    
    # Store dataset images
    for dataset_image in dataset_images:
        dataset_repo.create(project_iteration_id, dataset_image.get("id"), {
            "dataset_image_id": dataset_image.get("id"),
            "project_iteration_id": project_iteration_id,
            "url": str(dataset_image.get("image_url")),
            "created_at": datetime.utcnow(),
        })
```

## Testing

### Local Development

1. Start Firestore Emulator:
   ```bash
   cd annotator_local_dev
   ./firestore-setup.sh start
   ```

2. Set environment variables:
   ```bash
   export FIRESTORE_EMULATOR_HOST=localhost:8080
   export GOOGLE_CLOUD_PROJECT=local-dev
   ```

3. Run your service - it will automatically use the emulator.

### Unit Tests

```python
import pytest
from annotator_common.firestore import init_firestore

@pytest.fixture(autouse=True)
def setup_firestore_emulator():
    """Setup Firestore Emulator for tests."""
    os.environ["FIRESTORE_EMULATOR_HOST"] = "localhost:8080"
    os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
    init_firestore()

def test_create_project():
    project_repo = ProjectIterationRepository()
    project_repo.create("test-project", {"status": "DOWNLOADING"})
    project = project_repo.get_by_id("test-project")
    assert project is not None
    assert project["status"] == "DOWNLOADING"
```

## Common Pitfalls

1. **Forgetting to initialize Firestore**: Always call `init_firestore()` at service startup.

2. **Using MongoDB _id**: Firestore documents use their document ID directly, not a separate `_id` field.

3. **Timestamp handling**: Firestore uses `SERVER_TIMESTAMP` or `datetime` objects. The repository handles conversion automatically.

4. **Array operations**: `$addToSet` and `$pull` are handled by the repository, but you need to pass them in the updates dict as shown in Pattern 7.

5. **Transactions**: Firestore transactions must complete within 60 seconds and have size limits. Use them judiciously.

## Migration Checklist

For each service:

- [ ] Add `init_firestore()` call at startup
- [ ] Replace `from annotator_common.database import get_database` with repository imports
- [ ] Replace `db = get_database()` with repository instances
- [ ] Replace all `db.<collection>.*` calls with repository methods
- [ ] Test locally with Firestore Emulator
- [ ] Update tests to use Firestore Emulator
- [ ] Remove MongoDB imports and dependencies
- [ ] Update environment variables (remove MONGODB_*, add FIRESTORE_* if needed)

## Next Steps

After migrating all services:

1. Update Cloud Run deployment configs to remove MongoDB references
2. Add Firestore permissions to service accounts
3. Remove MongoDB dependencies from requirements.txt
4. Update documentation

