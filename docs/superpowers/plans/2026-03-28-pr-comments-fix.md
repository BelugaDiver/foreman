# PR Comments Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix PR review comments: security (email enumeration), correctness (ClientError handling), test coverage (503 handlers), and diagnostics (exception chaining)

**Architecture:** Narrow ClientError to transient codes only, add generic error messages, add exception chaining, add tests for global handlers

**Tech Stack:** Python, FastAPI, pytest, asyncpg, botocore

---

## PR Comments Summary

| Comment | Status |
|---------|--------|
| DuplicateResourceError → 409 | ✅ Already done |
| DuplicateResourceError exposes email | 🔲 To fix |
| ClientError too broad for 503 | 🔲 To fix |
| No tests for 503 handlers | 🔲 To fix |
| user_id missing from logs | 🔲 To fix |
| Design doc wrong exception | 🔲 To fix |
| Exception chaining | 🔲 To fix |

---

## Task 1: Fix email enumeration in DuplicateResourceError

**Files:**
- Modify: `foreman/api/v1/endpoints/users.py`

**Context:** Currently `DuplicateResourceError` includes the email in the message, enabling user enumeration. Need to return a generic message instead.

- [ ] **Step 1: Read current implementation**

Read `foreman/api/v1/endpoints/users.py` to see how DuplicateResourceError is handled

- [ ] **Step 2: Change to generic message**

```python
# Current:
except DuplicateResourceError as e:
    raise HTTPException(status_code=409, detail=str(e))

# Change to:
except DuplicateResourceError:
    raise HTTPException(status_code=409, detail="A user with this information already exists")
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_users.py -v
```

- [ ] **Step 4: Commit**

```bash
git add foreman/api/v1/endpoints/users.py
git commit -m "fix: avoid email enumeration in duplicate user error"
```

---

## Task 2: Narrow ClientError handling for S3

**Files:**
- Modify: `foreman/main.py`

**Context:** `ClientError` is too broad - maps all S3 errors to 503 which misleads clients. Should only return 503 for transient errors.

- [ ] **Step 1: Read current implementation**

Read `foreman/main.py` to find the ClientError handler

- [ ] **Step 2: Implement narrowed handler**

```python
from botocore.exceptions import ClientError

async def storage_client_error_handler(request: Request, exc: ClientError):
    error_code = None
    try:
        error_code = (exc.response or {}).get("Error", {}).get("Code")
    except Exception:
        error_code = None

    error_logger.exception(
        "Storage client error",
        extra={
            "url": str(request.url),
            "method": request.method,
            "error_type": type(exc).__name__,
            "error_code": error_code,
        },
    )

    transient_error_codes = {
        "SlowDown",
        "RequestTimeout",
        "InternalError",
        "ServiceUnavailable",
        "Throttling",
        "RequestLimitExceeded",
    }

    if error_code in transient_error_codes:
        status_code = 503
        detail = "Storage service temporarily unavailable"
    else:
        status_code = 500
        detail = "Storage service error"

    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
    )
```

- [ ] **Step 3: Run tests**

```bash
pytest -v
```

- [ ] **Step 4: Commit**

```bash
git add foreman/main.py
git commit -m "fix: narrow ClientError handling to transient S3 errors"
```

---

## Task 3: Add tests for 503 global exception handlers

**Files:**
- Create: `tests/test_global_exception_handlers.py`

**Context:** Need tests for ConnectionFailureError, QueryCanceledError, TimeoutError, ClientError handlers

- [ ] **Step 1: Create test file**

Create `tests/test_global_exception_handlers.py` with tests that trigger each handler and verify 503 response

- [ ] **Step 2: Run tests to verify they work**

```bash
pytest tests/test_global_exception_handlers.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_global_exception_handlers.py
git commit -m "test: add tests for global 503 exception handlers"
```

---

## Task 4: Add user_id to debug logs in repositories

**Files:**
- Modify: `foreman/repositories/postgres_images_repository.py`
- Modify: `foreman/repositories/postgres_generations_repository.py`

**Context:** Debug logs are missing user_id even though queries are user-scoped

- [ ] **Step 1: Read and update images repo**

Add user_id back to debug log extra in `get_image_by_id`

- [ ] **Step 2: Read and update generations repo**

Add user_id back to debug log extra in `get_generation_by_id`

- [ ] **Step 3: Run tests**

```bash
pytest -v
```

- [ ] **Step 4: Commit**

```bash
git add foreman/repositories/
git commit -m "fix: add user_id to debug logs for better traceability"
```

---

## Task 5: Fix design doc exception type

**Files:**
- Modify: `docs/superpowers/specs/2026-03-27-error-handling-design.md`

**Context:** Doc references `asyncpg.ConnectionFailure` but code uses `ConnectionFailureError`

- [ ] **Step 1: Read and fix doc**

Change `ConnectionFailure` to `ConnectionFailureError`

- [ ] **Step 2: Commit**

```bash
git add docs/superpowers/specs/
git commit -m "docs: fix exception type in error handling design"
```

---

## Task 6: Add exception chaining for UniqueViolationError

**Files:**
- Modify: `foreman/repositories/postgres_users_repository.py`

**Context:** Should chain exceptions to preserve root cause in logs/traces

- [ ] **Step 1: Read current implementation**

```python
except asyncpg.UniqueViolationError:
    raise DuplicateResourceError("User", "email", user_in.email)
```

- [ ] **Step 2: Add exception chaining**

```python
except asyncpg.UniqueViolationError as exc:
    raise DuplicateResourceError("User", "email", user_in.email) from exc
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_users.py -v
```

- [ ] **Step 4: Commit**

```bash
git add foreman/repositories/postgres_users_repository.py
git commit -m "fix: add exception chaining for UniqueViolationError"
```

---

## Summary

| Task | Description |
|------|-------------|
| 1 | Fix email enumeration - return generic message |
| 2 | Narrow ClientError to transient S3 errors |
| 3 | Add tests for 503 handlers |
| 4 | Add user_id to debug logs |
| 5 | Fix design doc exception type |
| 6 | Add exception chaining |

**Total: 6 tasks**
