# Integration Test Failures - Root Cause Analysis

## Summary

This document analyzes the 13 failing integration tests and identifies the root causes in the codebase.

## Failing Tests

### Category 1: JSON Type Mismatch (1 test)

**Test:** `test_update_project`
**Error:** `asyncpg.exceptions.DataError: invalid input for query argument $2: {'style': 'modern'} (expected str, got dict)`

**Root Cause:** The `update_project` function in `postgres_projects_repository.py` directly passes `room_analysis` dict to SQL without converting to JSON string. The database column is `JSONB` but asyncpg expects a string.

**Location:** `foreman/repositories/postgres_projects_repository.py:109`
```python
for idx, (key, value) in enumerate(update_data.items(), start=1):
    set_clauses.append(f"{key}=${idx}")
    params.append(value)  # <-- dict passed directly
```

**Fix:** Convert dict to JSON string: `json.dumps(value)` if value is dict


### Category 2: Missing R2 Storage Configuration (2 tests)

**Tests:** 
- `test_get_image_not_found`
- `test_get_image_wrong_user`

**Error:** `ValueError: R2Settings is not configured`

**Root Cause:** The image endpoints import and initialize R2 storage at module load time. Without `R2_*` environment variables, it raises `ValueError` on import.

**Location:** `foreman/storage/r2_storage.py:24`

**Solution: Use LocalStack as R2/S3 emulator**

Cloudflare R2 is S3-compatible. We can use **LocalStack** (local AWS emulator) to provide an S3-compatible endpoint that R2 clients can use locally.

**Approach:**
1. Add LocalStack container (runs alongside PostgreSQL)
2. Configure R2 storage to use LocalStack endpoint
3. LocalStack persists data locally in Docker volume

**Benefits:**
- No external dependencies (all local)
- S3-compatible API works with boto3/R2 SDK
- Can be extended to mock other AWS services if needed


### Category 3: Response Schema Validation (10 tests)

**Tests:**
- All generation tests (10 tests)
- `test_list_project_generations`

**Error:** `fastapi.exceptions.ResponseValidationError: 1 validation error`

**Root Cause:** The generation endpoints return data that doesn't match the Pydantic response schema. Likely missing fields or type mismatches in the `GenerationRead` schema vs what's returned from the database.

**Location:** Likely in `foreman/schemas/generation.py` or the endpoint response construction


### Category 4: Test Cleanup Issue (intermittent)

**Tests:** Some ownership tests fail intermittently

**Root Cause:** The cleanup fixture truncates tables but uses separate connections - timing can cause issues with test isolation.

**Fix:** Ensure cleanup uses the same connection or add explicit wait


## Implementation Plan

### Task 1: Fix JSON Type Mismatch

**Files:**
- Modify: `foreman/repositories/postgres_projects_repository.py`

**Steps:**
1. Add `import json` at top of file
2. In `update_project`, convert dict values to JSON string before passing to SQL:
```python
for idx, (key, value) in enumerate(update_data.items(), start=1):
    set_clauses.append(f"{key}=${idx}")
    if isinstance(value, dict):
        params.append(json.dumps(value))
    else:
        params.append(value)
```

### Task 2: Fix R2 Storage Configuration with LocalStack

**Files:**
- Modify: `tests/integration/conftest.py`
- Modify: `foreman/storage/r2_storage.py` or environment config

**Steps:**

1. **Add LocalStack to conftest.py:**
```python
@pytest.fixture(scope="session", autouse=True)
def localstack_container():
    """Start LocalStack container for S3/R2 emulation."""
    from testcontainers.localstack import LocalStackContainer
    
    with LocalStackContainer(image="localstack/localstack:latest") as ls:
        ls.with_services("s3")
        ls.start()
        
        # Create test bucket
        import boto3
        s3_client = boto3.client(
            "s3",
            endpoint_url="http://localhost:4566",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )
        s3_client.create_bucket(Bucket="test-bucket")
        
        yield ls
```

2. **Set environment variables for tests:**
```python
os.environ["R2_ACCESS_KEY_ID"] = "test"
os.environ["R2_SECRET_ACCESS_KEY"] = "test"
os.environ["R2_BUCKET_NAME"] = "test-bucket"
# Point to LocalStack instead of real R2
os.environ["R2_ENDPOINT_URL"] = "http://localhost:4566"
```

3. **Make R2 storage accept endpoint_url from environment** (if not already supported)

### Task 3: Fix Response Schema Validation

**Files:**
- Review: `foreman/schemas/generation.py`
- Review: `foreman/repositories/postgres_generations_repository.py`
- Review: `foreman/api/v1/endpoints/generations.py`

**Steps:**
1. Check each field in `GenerationRead` schema
2. Compare with fields returned from database query
3. Fix any mismatches

### Task 4: Fix Test Cleanup (if needed)

**Files:**
- Modify: `tests/integration/conftest.py`

**Approach:** Add small delay or ensure cleanup waits for connections to close


## Acceptance Criteria

- [ ] All 43 integration tests pass
- [ ] No 500 errors from JSON type issues
- [ ] No R2 storage errors for image tests (using LocalStack)
- [ ] All response schemas validate correctly
