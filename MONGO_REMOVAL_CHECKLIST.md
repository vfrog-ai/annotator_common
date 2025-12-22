# MongoDB Removal Checklist

This checklist ensures all MongoDB dependencies and references are removed after migrating to Firestore.

## Code Changes

### Services
- [ ] `annotator_api_service`
  - [ ] Remove `from annotator_common.database import get_database`
  - [ ] Remove `db = get_database()` calls
  - [ ] Replace all `db.*` calls with repository methods
  - [ ] Remove MongoDB-related imports (`pymongo`, `bson`, etc.)

- [ ] `annotator_project_manager`
  - [ ] Remove MongoDB database calls
  - [ ] Replace with Firestore repositories
  - [ ] Update imports

- [ ] `annotator_annotation_service`
  - [ ] Remove MongoDB database calls
  - [ ] Replace with Firestore repositories
  - [ ] Update imports

- [ ] `annotator_cutout_service`
  - [ ] Remove MongoDB database calls
  - [ ] Replace with Firestore repositories
  - [ ] Update imports

- [ ] `annotator_image_analysis_service`
  - [ ] Remove MongoDB database calls
  - [ ] Replace with Firestore repositories
  - [ ] Update imports

- [ ] `annotator_image_download_service`
  - [ ] Remove MongoDB database calls
  - [ ] Replace with Firestore repositories
  - [ ] Update imports

### Common Library
- [ ] `annotator_common/annotator_common/database/connection.py`
  - [ ] **Option A**: Remove file entirely if not needed for backward compatibility
  - [ ] **Option B**: Keep with deprecation warnings, remove after all services migrated
  - [ ] Document deprecation

- [ ] `annotator_common/annotator_common/config.py`
  - [ ] Remove MongoDB config fields (or mark as deprecated)
  - [ ] Keep for backward compatibility temporarily if needed

### Inference Server
- [ ] `inference-server/train.py`
  - [ ] Replace MongoDB client with Firestore repositories
  - [ ] Update `get_mongodb_client()` usage

- [ ] `inference-server/modal_tasks.py`
  - [ ] Replace `modal_billing` MongoDB collection with Firestore
  - [ ] Update `track_modal_billing()` function

## Dependencies

### Python Requirements

**annotator_common/setup.py:**
- [ ] Remove `pymongo>=4.6.0` from `install_requires`
- [ ] Keep `google-cloud-firestore>=2.13.0` (already added)

**Service requirements.txt files:**
- [ ] Remove `pymongo` from:
  - `annotator_api_service/requirements.txt`
  - `annotator_project_manager/requirements.txt`
  - `annotator_annotation_service/requirements.txt`
  - `annotator_cutout_service/requirements.txt`
  - `annotator_image_analysis_service/requirements.txt`
  - `annotator_image_download_service/requirements.txt`
  - `inference-server/requirements.txt`

### Docker Images
- [ ] Remove MongoDB-related packages from Dockerfiles if explicitly installed
- [ ] No changes needed if using pip-installed packages only

## Configuration Files

### Environment Variables

**Remove from:**
- [ ] `.env` files (local development)
- [ ] `docker-compose.yml` files
- [ ] Cloud Run service configurations
- [ ] GitHub Actions workflow files
- [ ] Terraform configurations
- [ ] Kubernetes manifests (if used)

**Remove variables:**
- `MONGODB_URI`
- `MONGODB_HOST`
- `MONGODB_PORT`
- `MONGODB_USER`
- `MONGODB_PASSWORD`
- `MONGODB_DATABASE`

### Secrets

- [ ] Remove `MONGODB_URI` from:
  - [ ] Google Cloud Secret Manager
  - [ ] GitHub Secrets
  - [ ] Other secret management systems

## Documentation

### Update Documentation

- [ ] Update `README.md` files to remove MongoDB references
- [ ] Update `DEPLOYMENT.md` / `DEPLOYMENT_GUIDE.md`
- [ ] Update `LOCAL_DEVELOPMENT.md` / setup guides
- [ ] Remove or archive MongoDB-specific docs:
  - [ ] `MONGODB_PERMISSIONS_GUIDE.md`
  - [ ] `MONGODB_ATLAS_GCP_MARKETPLACE.md`
  - [ ] `FIX_MONGODB_PERMISSIONS.md`

### Add New Documentation

- [ ] Firestore setup guide (see `FIRESTORE_EMULATOR_README.md`)
- [ ] Migration guide (see `MIGRATION_GUIDE.md`)
- [ ] Firestore schema documentation (see `FIRESTORE_SCHEMA.md`)

## Infrastructure

### Terraform

- [ ] Remove MongoDB Atlas resources (if managed via Terraform)
- [ ] Remove MongoDB-related variables from `terraform.tfvars`
- [ ] Update outputs to remove MongoDB connection strings

### CI/CD

- [ ] Remove MongoDB setup steps from CI pipelines
- [ ] Add Firestore Emulator setup for CI (if needed)
- [ ] Update deployment scripts

## Testing

- [ ] Update unit tests to use Firestore Emulator
- [ ] Update integration tests
- [ ] Remove MongoDB-specific test fixtures
- [ ] Update test documentation

## Data Migration

**Note:** This checklist assumes production data migration is handled separately (out of scope for VFR-33).

- [ ] Document data migration process (separate issue)
- [ ] Plan rollback strategy if migration fails
- [ ] Test data migration on staging environment

## Verification Steps

After removal:

1. **Search codebase for MongoDB references:**
   ```bash
   grep -r "pymongo\|MongoClient\|mongodb" --include="*.py" --exclude-dir=__pycache__
   grep -r "MONGODB_" --include="*.yml" --include="*.yaml" --include="*.env*"
   ```

2. **Verify no MongoDB imports:**
   ```bash
   grep -r "from pymongo\|import pymongo\|from bson" --include="*.py"
   ```

3. **Check requirements files:**
   ```bash
   grep -r "pymongo\|mongodb" requirements*.txt
   ```

4. **Test services locally:**
   - Start Firestore Emulator
   - Run each service
   - Verify no MongoDB connection errors

5. **Test services in staging:**
   - Deploy to staging with Firestore
   - Run smoke tests
   - Verify data persistence

## Rollback Plan

If issues are discovered after removal:

1. **Immediate rollback:**
   - Restore MongoDB environment variables
   - Redeploy previous code version (pre-Firestore)
   - Re-enable MongoDB dependencies

2. **Gradual rollback:**
   - Keep both MongoDB and Firestore code paths (feature flag)
   - Route traffic back to MongoDB
   - Fix Firestore issues
   - Re-enable Firestore gradually

## Timeline

Recommended order:

1. **Phase 1**: Complete service migrations (code changes)
2. **Phase 2**: Update dependencies and configs
3. **Phase 3**: Remove MongoDB from infrastructure
4. **Phase 4**: Clean up documentation and secrets
5. **Phase 5**: Final verification and testing

## Notes

- Keep MongoDB connection code temporarily with deprecation warnings during transition
- Maintain backward compatibility layer if needed
- Document any MongoDB references that must remain (e.g., legacy scripts)

