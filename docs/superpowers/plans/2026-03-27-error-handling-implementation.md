# Error Handling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement hybrid error handling that returns actionable 4xx/5xx status codes instead of generic 500s for infrastructure failures.

**Architecture:** 
- Centralized handlers in main.py for infrastructure errors (DB connection, timeouts)
- Custom domain exceptions in foreman/exceptions.py for domain errors (not found, duplicates, invalid state)
- Endpoints catch domain exceptions and return appropriate 4xx, let infrastructure errors propagate
- Domain exceptions (NotFound, InvalidState, Duplicate) are NOT logged as errors - only traced (expected user errors)
- Infrastructure exceptions (DB connection, timeout, storage) ARE logged as errors for OTel

**Tech Stack:** FastAPI, asyncpg, boto3 (storage), OpenTelemetry

---

## File Structure

- **Create:** `foreman/exceptions.py` - Domain exception classes
- **Modify:** `foreman/main.py` - Add exception handlers
- **Modify:** `foreman/api/v1/endpoints/users.py` - Remove unnecessary 500 handlers
- **Modify:** `foreman/api/v1/endpoints/projects.py` - Remove unnecessary 500 handlers  
- **Modify:** `foreman/api/v1/endpoints/generations.py` - Remove unnecessary 500 handlers
- **Modify:** `foreman/api/v1/endpoints/images.py` - Remove unnecessary 500 handlers
- **Modify:** `foreman/repositories/postgres_users_repository.py` - Raise domain exceptions
- **Modify:** `foreman/repositories/postgres_projects_repository.py` - Raise domain exceptions
- **Modify:** `foreman/repositories/postgres_generations_repository.py` - Raise domain exceptions
- **Modify:** `foreman/repositories/postgres_images_repository.py` - Raise domain exceptions

---

## Task 1: Create Domain Exceptions Module

**Files:**
- Create: `foreman/exceptions.py`

- [ ] **Step 1: Write domain exceptions module**

```python
"""Domain exceptions for Foreman API."""


class ResourceNotFoundError(Exception):
    """Raised when a resource doesn't exist or user doesn't have access."""
    def __init__(self, resource: str, identifier: str | None = None):
        self.resource = resource
        self.identifier = identifier
        msg = f"{resource} not found"
        if identifier:
            msg += f": {identifier}"
        super().__init__(msg)


class DuplicateResourceError(Exception):
    """Raised when creating a resource that already exists."""
    def __init__(self, resource: str, field: str, value: str):
        self.resource = resource
        self.field = field
        self.value = value
        super().__init__(f"{resource} with {field}='{value}' already exists")


class InvalidStateError(Exception):
    """Raised when operation can't be performed due to current resource state."""
    def __init__(self, resource: str, current_state: str, operation: str):
        self.resource = resource
        self.current_state = current_state
        self.operation = operation
        super().__init__(
            f"Cannot {operation} {resource} in state '{current_state}'"
        )
```

- [ ] **Step 2: Commit**

```bash
git add foreman/exceptions.py
git commit -m "feat: add domain exception classes"
```

---

## Task 2: Add Infrastructure Exception Handlers to main.py

**Files:**
- Modify: `foreman/main.py`

- [ ] **Step 1: Read main.py to find where to add handlers**

```bash
# Already read in context - handlers go after app creation, before routers
```

- [ ] **Step 2: Add exception imports**

Add after existing imports:
```python
from asyncpg import ConnectionFailure, QueryCanceledError
from fastapi import Request
from fastapi.responses import JSONResponse
import asyncio
```

- [ ] **Step 3: Add exception handler functions**

Add after existing imports in main.py (find `logger = logging.getLogger(__name__)`):
```python
error_logger = logging.getLogger("foreman.errors")
```

Add before `@app.get("/")`:
```python
async def connection_failure_handler(request: Request, exc: ConnectionFailure):
    error_logger.exception(
        "Database connection failed",
        extra={"url": str(request.url), "method": request.method},
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database temporarily unavailable"},
    )


async def query_canceled_handler(request: Request, exc: QueryCanceledError):
    error_logger.exception(
        "Database query cancelled",
        extra={"url": str(request.url), "method": request.method},
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database temporarily unavailable"},
    )


async def timeout_error_handler(request: Request, exc: asyncio.TimeoutError):
    error_logger.exception(
        "Request timeout",
        extra={"url": str(request.url), "method": request.method},
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Service temporarily unavailable"},
    )
```

- [ ] **Step 4: Register handlers**

Add after `instrument_app(app)` and before router registration:
```python
app.add_exception_handler(ConnectionFailure, connection_failure_handler)
app.add_exception_handler(QueryCanceledError, query_canceled_handler)
app.add_exception_handler(asyncio.TimeoutError, timeout_error_handler)
```

- [ ] **Step 5: Run lint to verify**

```bash
ruff check foreman/main.py
```

- [ ] **Step 6: Commit**

```bash
git add foreman/main.py
git commit -m "feat: add infrastructure exception handlers for 503 responses"
```

---

## Task 3: Update Users Repository and Endpoint

**Files:**
- Modify: `foreman/repositories/postgres_users_repository.py`
- Modify: `foreman/api/v1/endpoints/users.py`

- [ ] **Step 1: Update users repository to raise domain exceptions**

In `postgres_users_repository.py`:

Add import at top:
```python
from foreman.exceptions import DuplicateResourceError
```

Modify `create_user` to raise `DuplicateResourceError` on unique violation. Change the function to:
```python
async def create_user(db: Database, user_in: UserCreate) -> User:
    """Create a new user in the database."""
    logger.info("Creating user", extra={"email": user_in.email})
    try:
        stmt = sql(
            """
            INSERT INTO users (email, full_name)
            VALUES ($1, $2)
            RETURNING *
            """,
            user_in.email,
            user_in.full_name,
        )
        record = await db.fetchrow(stmt)
    except Exception as e:
        # Check for unique violation - asyncpg raises specific error codes
        if "23505" in str(e):  # unique_violation
            raise DuplicateResourceError("User", "email", user_in.email)
        raise
    if not record:
        raise RuntimeError("Failed to create user record")
    return User(**dict(record))
```

- [ ] **Step 2: Update users endpoint to handle domain exceptions**

In `users.py`:

Update imports:
```python
from foreman.exceptions import DuplicateResourceError
```

Update `create_user` endpoint to remove generic `except Exception`:
```python
@router.post("/", response_model=UserRead, status_code=201)
async def create_user(
    user_in: UserCreate = Body(...),
    db: Database = Depends(get_db),
):
    """Register a new user."""
    try:
        user = await crud.create_user(db=db, user_in=user_in)
        logger.info("User created", extra={"user_id": str(user.id), "email": user.email})
        return user
    except DuplicateResourceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Error creating user")
        raise HTTPException(status_code=500, detail="Internal server error")
```

Update `update_user_me` similarly:
```python
    except DuplicateResourceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception:
        logger.exception("Error updating user")
        raise HTTPException(status_code=500, detail="Internal server error")
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_users.py -v
```

- [ ] **Step 4: Commit**

```bash
git add foreman/repositories/postgres_users_repository.py foreman/api/v1/endpoints/users.py
git commit -m "feat: add domain exceptions to users repository and endpoint"
```

---

## Task 4: Update Projects Repository and Endpoints

**Files:**
- Modify: `foreman/repositories/postgres_projects_repository.py`
- Modify: `foreman/api/v1/endpoints/projects.py`

- [ ] **Step 1: Update projects repository**

Add import:
```python
from foreman.exceptions import ResourceNotFoundError
```

Update `get_project_by_id` to raise `ResourceNotFoundError`:
```python
async def get_project_by_id(
    db: Database,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Project:
    """Retrieve a single project by ID scoped to the owning user."""
    logger.debug("Fetching project", extra={"project_id": str(project_id), "user_id": str(user_id)})
    stmt = sql(
        "SELECT * FROM projects WHERE id=$1 AND user_id=$2",
        project_id,
        user_id,
    )
    record = await db.fetchrow(stmt)
    if not record:
        raise ResourceNotFoundError("Project", str(project_id))
    return _parse_project_record(record)
```

Note: Need to update all callers of `get_project_by_id` to handle the exception instead of checking for None.

- [ ] **Step 2: Update projects endpoint to handle ResourceNotFoundError**

Update imports:
```python
from foreman.exceptions import ResourceNotFoundError
```

Update `list_projects` - remove try/except entirely (no changes needed, no exception thrown):
```python
# Already clean - no exception handling needed
```

Update `create_project` - remove try/except:
```python
@router.post("/", response_model=ProjectRead, status_code=201)
async def create_project(
    project_in: ProjectCreate = Body(...),
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Create a new design project."""
    project = await crud.create_project(db=db, user_id=current_user.id, project_in=project_in)
    logger.info(
        "Project created",
        extra={"project_id": str(project.id), "user_id": str(current_user.id)},
    )
    return project
```

Update `get_project`:
```python
@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get details for a single project."""
    try:
        return await crud.get_project_by_id(db=db, project_id=project_id, user_id=current_user.id)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
```

Update `create_generation`:
```python
    try:
        # ... existing logic ...
    except HTTPException:
        raise
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
```

Update `update_project`:
```python
    try:
        project = await crud.update_project(...)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
```

Update `delete_project`:
```python
    try:
        success = await crud.delete_project(...)
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Project not found")
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_projects.py -v
```

- [ ] **Step 4: Commit**

```bash
git add foreman/repositories/postgres_projects_repository.py foreman/api/v1/endpoints/projects.py
git commit -m "feat: add ResourceNotFoundError to projects"
```

---

## Task 5: Update Generations Repository and Endpoints

**Files:**
- Modify: `foreman/repositories/postgres_generations_repository.py`
- Modify: `foreman/api/v1/endpoints/generations.py`

- [ ] **Step 1: Update generations repository**

Add import:
```python
from foreman.exceptions import ResourceNotFoundError, InvalidStateError
```

Update `get_generation_by_id` to raise `ResourceNotFoundError`:
```python
async def get_generation_by_id(
    db: Database,
    generation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Generation:
    """Retrieve a generation by ID scoped to the owning user."""
    logger.debug("Fetching generation", extra={"generation_id": str(generation_id)})
    stmt = sql(
        "SELECT * FROM generations WHERE id=$1 AND user_id=$2",
        generation_id,
        user_id,
    )
    record = await db.fetchrow(stmt)
    if not record:
        raise ResourceNotFoundError("Generation", str(generation_id))
    return _parse_generation_record(record)
```

- [ ] **Step 2: Update generations endpoint**

Update imports:
```python
from foreman.exceptions import ResourceNotFoundError, InvalidStateError
```

Update all endpoints to catch `ResourceNotFoundError`:
- `get_generation` - catch and return 404
- `update_generation` - catch and return 404
- `delete_generation` - catch and return 404
- `cancel_generation` - catch and return 404
- `retry_generation` - catch and return 404
- `fork_generation` - catch and return 404

For `list_generations`, keep try/except but only for infrastructure errors (connection/timeout - will be handled by main.py handlers now).

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_generations.py -v
```

- [ ] **Step 4: Commit**

```bash
git add foreman/repositories/postgres_generations_repository.py foreman/api/v1/endpoints/generations.py
git commit -m "feat: add domain exceptions to generations"
```

---

## Task 6: Update Images Repository and Endpoints

**Files:**
- Modify: `foreman/repositories/postgres_images_repository.py`
- Modify: `foreman/api/v1/endpoints/images.py`

- [ ] **Step 1: Update images repository**

Add import:
```python
from foreman.exceptions import ResourceNotFoundError
```

Update `get_image_by_id` to raise `ResourceNotFoundError`:
```python
async def get_image_by_id(
    db: Database,
    image_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Image:
    """Retrieve an image by ID scoped to the owning user."""
    logger.debug("Fetching image", extra={"image_id": str(image_id)})
    stmt = sql(
        "SELECT * FROM images WHERE id=$1 AND user_id=$2",
        image_id,
        user_id,
    )
    record = await db.fetchrow(stmt)
    if not record:
        raise ResourceNotFoundError("Image", str(image_id))
    return _parse_image_record(record)
```

- [ ] **Step 2: Update images endpoint**

Update imports:
```python
from foreman.exceptions import ResourceNotFoundError
```

Update endpoints:
- `get_image` - catch and return 404
- `delete_image` - catch and return 404

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_images.py -v
```

- [ ] **Step 4: Commit**

```bash
git add foreman/repositories/postgres_images_repository.py foreman/api/v1/endpoints/images.py
git commit -m "feat: add domain exceptions to images"
```

---

## Task 7: Add Storage Exception Handler

**Files:**
- Modify: `foreman/main.py`

- [ ] **Step 1: Add boto3 exception handler**

Boto3 exceptions are diverse. Common ones:
- `botocore.exceptions.ClientError` - general S3 errors
- `botocore.exceptions.EndpointConnectionError` - can't reach endpoint

Add handler:
```python
from botocore.exceptions import ClientError, EndpointConnectionError


async def storage_error_handler(request: Request, exc: (ClientError, EndpointConnectionError)):
    error_logger.exception(
        "Storage operation failed",
        extra={"url": str(request.url), "method": request.method, "error_type": type(exc).__name__},
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Storage service temporarily unavailable"},
    )
```

Register:
```python
app.add_exception_handler((ClientError, EndpointConnectionError), storage_error_handler)
```

- [ ] **Step 2: Run lint**

```bash
ruff check foreman/main.py
```

- [ ] **Step 3: Commit**

```bash
git add foreman/main.py
git commit -m "feat: add storage exception handler for 503 responses"
```

---

## Task 8: Run Full Test Suite

- [ ] **Step 1: Run all tests**

```bash
pytest -v
```

- [ ] **Step 2: Run lint**

```bash
ruff check .
```

- [ ] **Step 3: Commit**

```bash
git commit -m "chore: run full test suite and lint"
```

---

## Summary

This plan adds:
- Domain exceptions: `ResourceNotFoundError`, `DuplicateResourceError`, `InvalidStateError`
- Centralized 503 handlers for infrastructure: DB connection, query timeout, storage errors
- Endpoints return proper 404/400 instead of generic 500
- Domain exceptions NOT logged (traced only) - expected user errors
- Infrastructure exceptions logged with context for OTel

Expected behavior changes:
- DB unavailable → 503 "Database temporarily unavailable"
- Storage unavailable → 503 "Storage service temporarily unavailable"  
- Resource not found → 404 "Resource not found"
- Duplicate resource → 400 "User with email='x' already exists"
- Invalid state → 400 "Cannot cancel generation in state 'completed'"
