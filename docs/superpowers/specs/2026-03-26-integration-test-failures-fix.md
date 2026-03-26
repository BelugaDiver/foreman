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

**Fix:** Either mock the storage or make R2 initialization lazy/on-demand


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

### Task 2: Fix R2 Storage Configuration

**Files:**
- Modify: `foreman/storage/r2_storage.py`
- Modify: `foreman/api/v1/endpoints/images.py`

**Approach:** Make R2 storage initialization lazy (on first use rather than at import time)

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
- [ ] No R2 storage errors for image tests
- [ ] All response schemas validate correctly
