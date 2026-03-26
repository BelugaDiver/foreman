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

**Verification:** Run `test_update_project` - should return 200 instead of 500


### Task 2: Fix R2 Storage Configuration with LocalStack

**Root Cause Analysis:**

The error `ValueError: R2Settings is not configured` happens because:
1. `foreman/storage/r2_storage.py` initializes R2 storage at module import time
2. It reads `R2Settings` from environment variables immediately
3. Without env vars, it raises `ValueError`

**Solution: Two Options**

#### Option A: Use LocalStack (Recommended)
Add LocalStack container to provide S3 endpoint.

#### Option B: Lazy Initialization (Simpler)
Make R2 storage initialize lazily on first use, not at import time. This avoids the error for tests that don't need storage.

**Steps for Option A:**

1. **Add LocalStack container to conftest.py:**
```python
@pytest.fixture(scope="session", autouse=True)
def localstack_container():
    """Start LocalStack container for S3/R2 emulation."""
    from testcontainers.localstack import LocalStackContainer
    
    with LocalStackContainer(image="localstack/localstack:latest") as ls:
        ls.with_services("s3")
        ls.start()
        
        # Create test bucket using boto3
        import boto3
        s3_client = boto3.client(
            "s3",
            endpoint_url="http://localhost:4566",
            aws_access_key_id="test",
            aws_secret_access_key="test",
        )
        s3_client.create_bucket(Bucket="foreman-images")
        
        yield {"endpoint": "http://localhost:4566", "bucket": "foreman-images"}
```

2. **Set environment variables before app import:**
```python
@pytest.fixture(scope="session", autouse=True)
def setup_r2_env(localstack_container):
    """Set R2 environment variables pointing to LocalStack."""
    os.environ["R2_ACCESS_KEY_ID"] = "test"
    os.environ["R2_SECRET_ACCESS_KEY"] = "test"
    os.environ["R2_ACCOUNT_ID"] = "test-account"
    os.environ["R2_BUCKET_NAME"] = localstack_container["bucket"]
    # Need to check if R2 storage supports endpoint_url from env
```

**Steps for Option B (Simpler):**

1. Modify `foreman/storage/r2_storage.py` to defer initialization:
```python
class R2Storage:
    def __init__(self, settings: R2Settings):
        self._settings = settings
        self._client = None
    
    @property
    def client(self):
        if self._client is None:
            # Initialize on first use, not at import time
            self._client = boto3.client(...)
        return self._client
```

This way, tests that don't actually upload images won't fail - only tests that need storage would need LocalStack.


### Task 3: Fix Response Schema Validation

**Root Cause Analysis:**

Error: `fastapi.exceptions.ResponseValidationError: 1 validation error: {'type': 'dict_type', 'loc': ('response', 'metadata'), 'msg': 'Input should be a valid dictionary', 'input': '{}'}`

**Issue:** The `metadata` field in `GenerationRead` schema is defined as `dict[str, Any]` but the database returns an empty dict `{}`. In Pydantic v2, this type annotation may not properly validate as a dict type.

**Location:** `foreman/schemas/generation.py:59`
```python
metadata: dict[str, Any]  # May need Optional[dict] or different typing
```

**Fix Options:**
1. Change `metadata: dict[str, Any]` to `metadata: Optional[dict[str, Any]] = None`
2. Add default value: `metadata: dict[str, Any] = Field(default_factory=dict)`
3. Or check if the issue is that empty dict `{}` doesn't match `dict[str, Any]` without a default

**Steps:**
1. Modify `foreman/schemas/generation.py` to handle empty dict properly:
```python
# Option: make Optional with default
metadata: Optional[dict[str, Any]] = None
```


### Task 4: Fix Test Cleanup (if needed)

**Files:**
- Modify: `tests/integration/conftest.py`

**Approach:** Add small delay or ensure cleanup waits for connections to close


## Acceptance Criteria

- [ ] All 43 integration tests pass
- [ ] No 500 errors from JSON type issues
- [ ] No R2 storage errors for image tests (using LocalStack)
- [ ] All response schemas validate correctly
