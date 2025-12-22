# Cloud Run Configuration for Firestore

This document describes the Cloud Run configuration changes needed for the Firestore migration.

## Environment Variables

### Remove (MongoDB-related):

- `MONGODB_URI`
- `MONGODB_HOST`
- `MONGODB_PORT`
- `MONGODB_USER`
- `MONGODB_PASSWORD`
- `MONGODB_DATABASE`

### Add/Ensure (Firestore-related):

- `GOOGLE_CLOUD_PROJECT` - Must be set to your GCP project ID
- **DO NOT SET** `FIRESTORE_EMULATOR_HOST` - This should only be set for local/CI

## Service Account Permissions

The Cloud Run service account needs Firestore permissions:

### Required IAM Roles:

- `roles/datastore.user` - Read/write access to Firestore

### Grant Permission:

```bash
PROJECT_ID="your-project-id"
SERVICE_ACCOUNT="your-service-account@your-project.iam.gserviceaccount.com"

gcloud projects add-iam-policy-binding $PROJECT_ID \
  --member="serviceAccount:$SERVICE_ACCOUNT" \
  --role="roles/datastore.user"
```

Or via Terraform:

```hcl
resource "google_project_iam_member" "firestore_user" {
  project = var.project_id
  role    = "roles/datastore.user"
  member  = "serviceAccount:${google_service_account.service_account.email}"
}
```

## Deployment Configuration

### Example: GitHub Actions Workflow

Update your deployment workflows to:

1. **Remove MongoDB secret references:**

```yaml
# BEFORE:
env:
  MONGODB_URI: ${{ secrets.MONGODB_URI }}

# AFTER:
env:
  GOOGLE_CLOUD_PROJECT: ${{ secrets.GCP_PROJECT_ID }}
  # No FIRESTORE_EMULATOR_HOST in production
```

2. **Ensure service account has Firestore permissions** (see above)

3. **Update Cloud Run service environment variables:**

```yaml
- name: Deploy to Cloud Run
  run: |
    gcloud run services update $SERVICE_NAME \
      --project=$PROJECT_ID \
      --region=$REGION \
      --remove-env-vars MONGODB_URI,MONGODB_DATABASE \
      --update-env-vars GOOGLE_CLOUD_PROJECT=$PROJECT_ID
```

### Example: Terraform Configuration

```hcl
resource "google_cloud_run_service" "api_service" {
  name     = "api-service"
  location = var.region

  template {
    spec {
      containers {
        image = var.image_url

        env {
          name  = "GOOGLE_CLOUD_PROJECT"
          value = var.project_id
        }

        # Remove MongoDB env vars:
        # - MONGODB_URI
        # - MONGODB_DATABASE
        # etc.
      }

      service_account_name = google_service_account.service_account.email
    }
  }
}
```

## Application Default Credentials (ADC)

Cloud Run automatically uses the service account's Application Default Credentials (ADC) for Firestore access. No explicit credential files needed.

The Firestore client initialization in `connection.py` automatically:

1. Detects if `FIRESTORE_EMULATOR_HOST` is set (local/CI mode)
2. Uses ADC if not set (production mode)

## Verification

### Test Firestore Connection

Add a health check endpoint that verifies Firestore connectivity:

```python
@app.get("/health")
async def health_check():
    try:
        from annotator_common.firestore import get_firestore_client
        client = get_firestore_client()
        # Try a simple read operation
        client.collection("_health_check").limit(1).stream()
        return {"status": "healthy", "firestore": "connected"}
    except Exception as e:
        return {"status": "unhealthy", "error": str(e)}, 500
```

### Monitor Logs

Check Cloud Run logs for Firestore connection messages:

```bash
gcloud logging read "resource.type=cloud_run_revision AND textPayload=~'Firestore'" \
  --project=$PROJECT_ID \
  --limit=50
```

## Rollback Plan

If you need to rollback to MongoDB:

1. Restore MongoDB environment variables in Cloud Run
2. Redeploy previous version of services (before Firestore migration)
3. Revert code changes

## Cost Considerations

Firestore pricing is different from MongoDB Atlas:

- Read operations: $0.06 per 100k reads
- Write operations: $0.18 per 100k writes
- Storage: $0.18 per GB/month

Monitor usage via Cloud Console → Firestore → Usage tab.

Consider enabling Firestore budgets:

```bash
gcloud billing budgets create \
  --billing-account=$BILLING_ACCOUNT \
  --display-name="Firestore Budget" \
  --budget-amount=100USD \
  --threshold-rule=percent=90
```
