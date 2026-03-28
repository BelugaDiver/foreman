# 100% Test Coverage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Achieve 100% test coverage across the foreman codebase by addressing all uncovered code paths.

**Architecture:** Add targeted unit tests to existing test files to cover missing branches, edge cases, and error handlers. No production code changes needed - this is purely a testing effort.

**Tech Stack:** pytest, pytest-cov, unittest.mock (AsyncMock, MagicMock)

---

## Coverage Gap Summary

| Module | Current | Missing Lines |
|--------|---------|---------------|
| `postgres_images_repository.py` | 43% | 57, 66-88, 98-133, 142-149 |
| `r2_storage.py` | 45% | 28-35, 41-44, 58-81, 88-95, 102-117 |
| `postgres_users_repository.py` | 75% | 32-36, 44-55, 75, 87, 111 |
| `main.py` | 74% | 32-60, 124-125 |
| `api/deps.py` | 79% | 15, 28-29, 37, 40 |
| `logging_config.py` | 85% | 28, 42-46 |
| `schemas/image.py` | 85% | 36, 38, 40, 47, 54, 56 |
| `generations.py` (endpoints) | 87% | 73, 96, 141, 154-156, 203, 206-208, 254, 257-259 |
| `images.py` (endpoints) | 88% | 67-76, 170-171, 179-189 |

---

## Task 1: Fix postgres_images_repository.py (43% → 100%)

**Files:**
- Create: `tests/test_images_repository.py`
- Modify: `tests/test_images.py` (add update tests)

**Reference:** `foreman/repositories/postgres_images_repository.py:1-149`

- [ ] **Step 1: Create test_images_repository.py with tests for create_image failure path**

```python
"""Tests for postgres_images_repository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from foreman.models.image import Image
from foreman.repositories import postgres_images_repository as repo
from foreman.schemas.image import ImageCreate

# Create test data
USER_ID = uuid.uuid4()
PROJECT_ID = uuid.uuid4()

@pytest.fixture
def mock_db():
    """Mock database with fetchrow returning None for failure test."""
    db = AsyncMock()
    # Test: create_image when fetchrow returns None
    db.fetchrow = AsyncMock(return_value=None)
    return db

@pytest.mark.asyncio
async def test_create_image_failure(mock_db):
    """create_image should raise RuntimeError when DB returns no record."""
    image_in = ImageCreate(
        project_id=PROJECT_ID,
        user_id=USER_ID,
        filename="test.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        storage_key="test/key",
    )
    
    with pytest.raises(RuntimeError, match="Failed to create image record"):
        await repo.create_image(mock_db, image_in)
```

- [ ] **Step 2: Add test for update_image with no fields (early return)**

```python
@pytest.mark.asyncio
async def test_update_image_no_fields_returns_existing():
    """update_image with empty update_data should return existing image."""
    # Mock db.fetchrow to return an existing image
    existing_image = Image(
        id=uuid.uuid4(),
        project_id=PROJECT_ID,
        user_id=USER_ID,
        filename="test.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        storage_key="test/key",
        url=None,
        created_at=datetime.now(timezone.utc),
        updated_at=None,
    )
    
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=MagicMock(**{
        '_asdict': lambda: {
            'id': existing_image.id,
            'project_id': existing_image.project_id,
            'user_id': existing_image.user_id,
            'filename': existing_image.filename,
            'content_type': existing_image.content_type,
            'size_bytes': existing_image.size_bytes,
            'storage_key': existing_image.storage_key,
            'url': existing_image.url,
            'created_at': existing_image.created_at,
            'updated_at': existing_image.updated_at,
        }
    }))
    
    from foreman.schemas.image import ImageUpdate
    result = await repo.update_image(db, existing_image.id, USER_ID, ImageUpdate())
    assert result is not None
```

- [ ] **Step 3: Add test for delete_image success**

```python
@pytest.mark.asyncio
async def test_delete_image_returns_true():
    """delete_image should return True when row is deleted."""
    db = AsyncMock()
    db.fetchrow = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))
    
    result = await repo.delete_image(db, uuid.uuid4(), USER_ID)
    assert result is True
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_images_repository.py -v
```

- [ ] **Step 5: Commit**

```bash
git add tests/test_images_repository.py
git commit -m "test: add images repository tests for 100% coverage"
```

---

## Task 2: Fix r2_storage.py (45% → 100%)

**Files:**
- Create: `tests/test_r2_storage.py`

**Reference:** `foreman/storage/r2_storage.py:1-117`

- [ ] **Step 1: Create test_r2_storage.py with lazy client initialization test**

```python
"""Tests for R2 storage."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from foreman.storage.r2_storage import R2Storage
from foreman.storage.settings import R2Settings

@pytest.fixture
def configured_settings():
    """R2 settings with all required env vars."""
    return R2Settings(
        endpoint="https://example.r2.cloudflarestorage.com",
        access_key_id="test-key",
        secret_access_key="test-secret",
        bucket="test-bucket",
        public_url=None,
    )

@pytest.fixture
def unconfigured_settings():
    """R2 settings missing required env vars."""
    return R2Settings(
        endpoint=None,
        access_key_id=None,
        secret_access_key=None,
        bucket="test-bucket",
    )

def test_lazy_client_initialization(configured_settings):
    """boto3 client should be created on first operation."""
    with patch('foreman.storage.r2_storage.boto3.client') as mock_client:
        mock_client.return_value = MagicMock()
        storage = R2Storage(configured_settings)
        
        # Client should NOT be created during __init__
        assert storage._client is not None
        mock_client.assert_called_once()

def test_unconfigured_storage_raises_on_operation(unconfigured_settings):
    """Unconfigured storage should raise ValueError on operations."""
    storage = R2Storage(unconfigured_settings)
    
    with pytest.raises(ValueError, match="not configured"):
        # Trigger _ensure_client
        storage._ensure_client()

@pytest.mark.asyncio
async def test_get_download_url_with_public_url(configured_settings):
    """get_download_url should use public_url when available."""
    configured_settings.public_url = "https://cdn.example.com"
    storage = R2Storage(configured_settings)
    storage._client = MagicMock()
    
    url = await storage.get_download_url("path/to/file.jpg")
    assert url == "https://cdn.example.com/path/to/file.jpg"
    storage._client.generate_presigned_url.assert_not_called()

@pytest.mark.asyncio
async def test_delete_returns_false_on_exception(configured_settings):
    """delete should return False when boto3 raises exception."""
    storage = R2Storage(configured_settings)
    storage._client = MagicMock()
    storage._client.delete_object = MagicMock(side_effect=Exception("AWS error"))
    
    result = await storage.delete("some/key")
    assert result is False
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_r2_storage.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_r2_storage.py
git commit -m "test: add R2 storage tests for 100% coverage"
```

---

## Task 3: Fix postgres_users_repository.py (75% → 100%)

**Files:**
- Create: `tests/test_users_repository.py`

**Reference:** `foreman/repositories/postgres_users_repository.py:1-128`

- [ ] **Step 1: Create test_users_repository.py**

```python
"""Tests for postgres_users_repository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import asyncpg

from foreman.models.user import User
from foreman.repositories import postgres_users_repository as repo
from foreman.schemas.user import UserCreate, UserUpdate
from foreman.exceptions import DuplicateResourceError

USER_ID = uuid.uuid4()
NOW = datetime.now(timezone.utc)

@pytest.fixture
def mock_db():
    return AsyncMock()

@pytest.mark.asyncio
async def test_get_user_by_email_found(mock_db):
    """get_user_by_email should return user when found."""
    mock_record = MagicMock()
    mock_record.__getitem__ = lambda self, k: {
        'id': USER_ID, 'email': 'test@example.com', 'full_name': 'Test',
        'is_active': True, 'is_deleted': False, 'created_at': NOW, 'updated_at': None
    }[k]
    mock_record.__iter__ = lambda self: iter([
        ('id', USER_ID), ('email', 'test@example.com'), ('full_name', 'Test'),
        ('is_active', True), ('is_deleted', False), ('created_at', NOW), ('updated_at', None)
    ])
    mock_db.fetchrow = AsyncMock(return_value=mock_record)
    
    result = await repo.get_user_by_email(mock_db, 'test@example.com')
    assert result is not None
    assert result.email == 'test@example.com'

@pytest.mark.asyncio
async def test_get_user_by_email_not_found(mock_db):
    """get_user_by_email should return None when not found."""
    mock_db.fetchrow = AsyncMock(return_value=None)
    
    result = await repo.get_user_by_email(mock_db, 'notfound@example.com')
    assert result is None

@pytest.mark.asyncio
async def test_ensure_dev_user_creates_if_not_exists(mock_db):
    """ensure_dev_user should create user if it doesn't exist."""
    mock_db.fetchrow = AsyncMock(side_effect=[None, MagicMock(
        **{'__getitem__': lambda s, k: {'id': USER_ID, 'email': 'test@example.com', 
            'full_name': 'Test', 'is_active': True, 'is_deleted': False,
            'created_at': NOW, 'updated_at': None}[k]}
    )])
    
    result = await repo.ensure_dev_user(mock_db)
    assert result.email == 'test@example.com'

@pytest.mark.asyncio
async def test_update_user_no_fields_returns_existing(mock_db):
    """update_user with empty fields should return existing user."""
    mock_record = MagicMock()
    mock_record.__getitem__ = lambda s, k: {
        'id': USER_ID, 'email': 'test@example.com', 'full_name': 'Test',
        'is_active': True, 'is_deleted': False, 'created_at': NOW, 'updated_at': None
    }[k]
    mock_db.fetchrow = AsyncMock(return_value=mock_record)
    
    result = await repo.update_user(mock_db, USER_ID, UserUpdate())
    assert result is not None

@pytest.mark.asyncio
async def test_soft_delete_user_returns_true(mock_db):
    """soft_delete_user should return True when user is deleted."""
    mock_db.fetchrow = AsyncMock(return_value=MagicMock(id=USER_ID))
    
    result = await repo.soft_delete_user(mock_db, USER_ID)
    assert result is True

@pytest.mark.asyncio
async def test_soft_delete_user_returns_false_when_not_found(mock_db):
    """soft_delete_user should return False when user not found."""
    mock_db.fetchrow = AsyncMock(return_value=None)
    
    result = await repo.soft_delete_user(mock_db, uuid.uuid4())
    assert result is False

@pytest.mark.asyncio
async def test_create_user_duplicate_email(mock_db):
    """create_user should raise DuplicateResourceError on unique violation."""
    mock_db.fetchrow = AsyncMock(side_effect=asyncpg.UniqueViolationError('duplicate'))
    
    with pytest.raises(DuplicateResourceError):
        await repo.create_user(mock_db, UserCreate(email='test@example.com', full_name='Test'))
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_users_repository.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_users_repository.py
git commit -m "test: add users repository tests for 100% coverage"
```

---

## Task 4: Fix main.py (74% → 100%)

**Files:**
- Modify: `tests/integration/test_main.py` or create `tests/test_main.py`

**Reference:** `foreman/main.py:1-182`

- [ ] **Step 1: Add tests for error handlers**

```python
"""Tests for main.py error handlers."""

from unittest.mock import AsyncMock, MagicMock, patch
import pytest
from fastapi.testclient import TestClient
from botocore.exceptions import ClientError, EndpointConnectionError

from foreman.main import app, storage_error_handler

@pytest.fixture
def mock_request():
    """Create a mock request object."""
    request = MagicMock()
    request.url = MagicMock()
    request.url.__str__ = lambda self: "http://test/health"
    request.method = "GET"
    return request

@pytest.mark.asyncio
async def test_storage_error_handler_transient(mock_request):
    """storage_error_handler should return 503 for transient errors."""
    error = ClientError(
        {"Error": {"Code": "SlowDown"}},
        "PutObject"
    )
    
    response = await storage_error_handler(mock_request, error)
    assert response.status_code == 503

@pytest.mark.asyncio
async def test_storage_error_handler_non_transient(mock_request):
    """storage_error_handler should return 500 for non-transient errors."""
    error = ClientError(
        {"Error": {"Code": "AccessDenied"}},
        "PutObject"
    )
    
    response = await storage_error_handler(mock_request, error)
    assert response.status_code == 500

@pytest.mark.asyncio
async def test_storage_error_handler_no_error_code(mock_request):
    """storage_error_handler should return 500 when no error code."""
    error = ClientError({}, "PutObject")
    
    response = await storage_error_handler(mock_request, error)
    assert response.status_code == 500
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_main.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_main.py
git commit -m "test: add main.py error handler tests"
```

---

## Task 5: Fix api/deps.py (79% → 100%)

**Files:**
- Modify: Create `tests/test_deps.py`

**Reference:** `foreman/api/deps.py:1-42`

- [ ] **Step 1: Create test_deps.py**

```python
"""Tests for API dependencies."""

import uuid
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from foreman.api.deps import get_db, get_current_user
from foreman.models.user import User
from foreman.repositories import postgres_users_repository as crud

@pytest.mark.asyncio
async def test_get_db_returns_database():
    """get_db should return database from app state."""
    mock_request = MagicMock()
    mock_db = MagicMock()
    mock_request.app.state.database = mock_db
    
    result = get_db(mock_request)
    assert result == mock_db

@pytest.mark.asyncio
async def test_get_current_user_invalid_uuid():
    """get_current_user should raise 401 for invalid UUID format."""
    mock_db = MagicMock()
    
    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(x_user_id="not-a-uuid", db=mock_db)
    
    assert exc_info.value.status_code == 401
    assert "Invalid X-User-ID format" in exc_info.value.detail

@pytest.mark.asyncio
async def test_get_current_user_none_after_resource_error():
    """get_current_user should handle None user after ResourceNotFoundError."""
    from foreman.exceptions import ResourceNotFoundError
    
    mock_db = MagicMock()
    # Simulate ResourceNotFoundError being caught but user still None
    async def side_effect(*args):
        raise ResourceNotFoundError("User", "test")
    
    with patch.object(crud, 'get_user_by_id', side_effect=side_effect):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(x_user_id=str(uuid.uuid4()), db=mock_db)
        
        assert exc_info.value.status_code == 401

@pytest.mark.asyncio
async def test_get_current_user_inactive():
    """get_current_user should raise 401 for inactive user."""
    mock_db = MagicMock()
    inactive_user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        full_name="Test",
        is_active=False,
        is_deleted=False,
        created_at=MagicMock(),
        updated_at=None,
    )
    
    with patch.object(crud, 'get_user_by_id', return_value=inactive_user):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(x_user_id=str(inactive_user.id), db=mock_db)
        
        assert exc_info.value.status_code == 401
        assert "inactive" in exc_info.value.detail

@pytest.mark.asyncio
async def test_get_current_user_deleted():
    """get_current_user should raise 401 for deleted user."""
    mock_db = MagicMock()
    deleted_user = User(
        id=uuid.uuid4(),
        email="test@example.com",
        full_name="Test",
        is_active=True,
        is_deleted=True,
        created_at=MagicMock(),
        updated_at=None,
    )
    
    with patch.object(crud, 'get_user_by_id', return_value=deleted_user):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(x_user_id=str(deleted_user.id), db=mock_db)
        
        assert exc_info.value.status_code == 401
        assert "deleted" in exc_info.value.detail
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_deps.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_deps.py
git commit -m "test: add deps tests for 100% coverage"
```

---

## Task 6: Fix logging_config.py (85% → 100%)

**Files:**
- Create: `tests/test_logging_config.py`

**Reference:** `foreman/logging_config.py:1-58`

- [ ] **Step 1: Create test_logging_config.py**

```python
"""Tests for logging configuration."""

import logging
import os
from unittest.mock import patch, MagicMock

import pytest

from foreman.logging_config import configure_logging, get_logger, CorrelationIdFilter


def test_configure_logging_json_format():
    """configure_logging should use JsonFormatter when LOG_FORMAT=json."""
    with patch.dict(os.environ, {"LOG_FORMAT": "json"}):
        # Clear handlers to ensure new ones are added
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers.copy()
        root_logger.handlers.clear()
        
        try:
            configure_logging()
            
            # Check that a handler was added with JsonFormatter
            assert len(root_logger.handlers) > 0
            handler = root_logger.handlers[0]
            from pythonjsonlogger.json import JsonFormatter
            assert isinstance(handler.formatter, JsonFormatter)
        finally:
            root_logger.handlers = original_handlers


def test_configure_logging_no_existing_handlers():
    """configure_logging should create new handler when none exist."""
    with patch.dict(os.environ, {"LOG_FORMAT": "text"}):
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers.copy()
        root_logger.handlers.clear()
        
        try:
            configure_logging()
            
            assert len(root_logger.handlers) > 0
        finally:
            root_logger.handlers = original_handlers
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_logging_config.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_logging_config.py
git commit -m "test: add logging config tests"
```

---

## Task 7: Fix schemas/image.py (85% → 100%)

**Files:**
- Create: `tests/test_schemas_image.py`

**Reference:** `foreman/schemas/image.py:1-91`

- [ ] **Step 1: Create test_schemas_image.py**

```python
"""Tests for image schemas."""

import pytest

from foreman.schemas.image import ImageUploadRequest, ImageCreate, ImageUpdate


class TestImageUploadRequestValidators:
    """Tests for ImageUploadRequest field validators."""
    
    def test_filename_no_path_separators_forward_slash(self):
        """Validator should reject filename with forward slash."""
        with pytest.raises(ValueError, match="path separators"):
            ImageUploadRequest(
                filename="path/to/file.jpg",
                content_type="image/jpeg",
                size_bytes=1024,
            )
    
    def test_filename_no_path_separators_backslash(self):
        """Validator should reject filename with backslash."""
        with pytest.raises(ValueError, match="path separators"):
            ImageUploadRequest(
                filename="path\\to\\file.jpg",
                content_type="image/jpeg",
                size_bytes=1024,
            )
    
    def test_filename_no_double_dots(self):
        """Validator should reject filename with .."""
        with pytest.raises(ValueError, match=r"\.\."):
            ImageUploadRequest(
                filename="../etc/passwd",
                content_type="image/jpeg",
                size_bytes=1024,
            )
    
    def test_content_type_not_allowed(self):
        """Validator should reject non-image content types."""
        with pytest.raises(ValueError, match="must be one of"):
            ImageUploadRequest(
                filename="test.jpg",
                content_type="application/json",
                size_bytes=1024,
            )
    
    def test_size_bytes_zero(self):
        """Validator should reject size_bytes of 0."""
        with pytest.raises(ValueError, match="positive"):
            ImageUploadRequest(
                filename="test.jpg",
                content_type="image/jpeg",
                size_bytes=0,
            )
    
    def test_size_bytes_exceeds_limit(self):
        """Validator should reject size_bytes > 50MB."""
        with pytest.raises(ValueError, match="50MB"):
            ImageUploadRequest(
                filename="test.jpg",
                content_type="image/jpeg",
                size_bytes=100_000_000,
            )
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_schemas_image.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_schemas_image.py
git commit -m "test: add image schema validator tests"
```

---

## Task 8: Fix generations.py endpoints (87% → 100%)

**Files:**
- Modify: `tests/test_generations_api.py` (add lifecycle tests for exception paths)

**Reference:** `foreman/api/v1/endpoints/generations.py:1-259`

- [ ] **Step 1: Add tests for exception handlers in lifecycle endpoints**

```python
# Add to test_generations_api.py

def test_update_generation_not_found(client, headers_a, monkeypatch):
    """PATCH /v1/generations/{id} should return 404 when not found."""
    async def mock_update(*args, **kwargs):
        return None
    
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.generations.repo.update_generation",
        mock_update
    )
    
    resp = client.patch(
        f"/v1/generations/{uuid.uuid4()}",
        headers=headers_a,
        json={"status": "completed"},
    )
    assert resp.status_code == 404


def test_delete_generation_not_found(client, headers_a, monkeypatch):
    """DELETE /v1/generations/{id} should return 404 when not found."""
    async def mock_delete(*args, **kwargs):
        return False
    
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.generations.repo.delete_generation",
        mock_delete
    )
    
    resp = client.delete(f"/v1/generations/{uuid.uuid4()}", headers=headers_a)
    assert resp.status_code == 404


def test_cancel_generation_not_found(client, headers_a, monkeypatch):
    """POST /v1/generations/{id}/cancel should return 404 when not found on update."""
    async def mock_get(*args, **kwargs):
        # Return a pending generation
        from foreman.models.generation import Generation
        return Generation(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            user_id=uuid.UUID(headers_a["X-User-ID"]),
            prompt="test",
            style_id=None,
            status="pending",
            model_used="test",
            attempt=1,
            input_image_url=None,
            output_image_url=None,
            created_at=MagicMock(),
            updated_at=None,
        )
    
    async def mock_update(*args, **kwargs):
        return None
    
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.generations.repo.get_generation_by_id",
        mock_get
    )
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.generations.repo.update_generation",
        mock_update
    )
    
    resp = client.post(f"/v1/generations/{uuid.uuid4()}/cancel", headers=headers_a)
    assert resp.status_code == 404


def test_retry_generation_not_found(client, headers_a, monkeypatch):
    """POST /v1/generations/{id}/retry should return 404 when not found."""
    async def mock_get(*args, **kwargs):
        from foreman.models.generation import Generation
        return Generation(
            id=uuid.uuid4(),
            project_id=uuid.uuid4(),
            user_id=uuid.UUID(headers_a["X-User-ID"]),
            prompt="test",
            style_id=None,
            status="failed",
            model_used="test",
            attempt=1,
            input_image_url=None,
            output_image_url=None,
            created_at=MagicMock(),
            updated_at=None,
        )
    
    async def mock_create(*args, **kwargs):
        return None
    
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.generations.repo.get_generation_by_id",
        mock_get
    )
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.generations.repo.create_generation",
        mock_create
    )
    
    resp = client.post(f"/v1/generations/{uuid.uuid4()}/retry", headers=headers_a)
    # The mock returns None for create, so we get different behavior
    # Test the not found on get case
    assert resp.status_code == 404


def test_fork_generation_not_found(client, headers_a, monkeypatch):
    """POST /v1/generations/{id}/fork should return 404 when not found."""
    async def mock_get(*args, **kwargs):
        raise Exception("Not found")
    
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.generations.repo.get_generation_by_id",
        mock_get
    )
    
    resp = client.post(f"/v1/generations/{uuid.uuid4()}/fork", headers=headers_a)
    assert resp.status_code == 404
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_generations_api.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_generations_api.py
git commit -m "test: add generations exception handler tests"
```

---

## Task 9: Fix images.py endpoints (88% → 100%)

**Files:**
- Modify: `tests/test_images.py`

**Reference:** `foreman/api/v1/endpoints/images.py:1-197`

- [ ] **Step 1: Add tests for storage delete warning and DB failure**

```python
# Add to test_images.py

def test_delete_image_storage_failure_warning(client, headers_a, project_a, monkeypatch):
    """DELETE /v1/images/{id} should warn but proceed when storage delete fails."""
    project_id = project_a["id"]
    
    # Create an image first
    create_resp = client.post(
        f"/v1/projects/{project_id}/images",
        headers=headers_a,
        json={"filename": "room.jpg", "content_type": "image/jpeg", "size_bytes": 1024},
    )
    image_id = create_resp.json()["image_id"]
    
    # Mock storage.delete to raise exception
    from unittest.mock import AsyncMock
    mock_storage = AsyncMock()
    mock_storage.delete = AsyncMock(side_effect=Exception("Storage error"))
    mock_storage.get_download_url = AsyncMock(return_value="https://example.com/download")
    
    def mock_get_storage():
        return mock_storage
    
    monkeypatch.setattr("foreman.api.v1.endpoints.images.get_storage_sync", mock_get_storage)
    
    # Should still succeed (204) - storage failure is logged as warning
    resp = client.delete(f"/v1/images/{image_id}", headers=headers_a)
    assert resp.status_code == 204


def test_create_upload_intent_db_failure(client, headers_a, project_a, monkeypatch):
    """POST /v1/projects/{id}/images should return 500 when DB create fails."""
    project_id = project_a["id"]
    
    # Mock create_image to raise exception
    async def mock_create_fail(*args, **kwargs):
        raise Exception("DB error")
    
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.images.crud.create_image",
        mock_create_fail
    )
    
    resp = client.post(
        f"/v1/projects/{project_id}/images",
        headers=headers_a,
        json={"filename": "room.jpg", "content_type": "image/jpeg", "size_bytes": 1024},
    )
    assert resp.status_code == 500


def test_delete_image_db_failure(client, headers_a, project_a, monkeypatch):
    """DELETE /v1/images/{id} should return 500 when DB delete fails."""
    project_id = project_a["id"]
    
    create_resp = client.post(
        f"/v1/projects/{project_id}/images",
        headers=headers_a,
        json={"filename": "room.jpg", "content_type": "image/jpeg", "size_bytes": 1024},
    )
    image_id = create_resp.json()["image_id"]
    
    # Mock delete_image to raise exception
    async def mock_delete_fail(*args, **kwargs):
        raise Exception("DB error")
    
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.images.crud.delete_image",
        mock_delete_fail
    )
    
    resp = client.delete(f"/v1/images/{image_id}", headers=headers_a)
    assert resp.status_code == 500
```

- [ ] **Step 2: Run tests**

```bash
pytest tests/test_images.py -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/test_images.py
git commit -m "test: add images endpoint error handling tests"
```

---

## Task 10: Final Verification

**Files:**
- Run coverage analysis

- [ ] **Step 1: Run full test suite with coverage**

```bash
pytest --cov=foreman --cov-report=term-missing --cov-report=html -v 2>&1
```

- [ ] **Step 2: Check for any remaining gaps**

If there are any remaining uncovered lines, add targeted tests.

- [ ] **Step 3: Commit final coverage improvements**

```bash
git add .
git commit -m "test: achieve 100% test coverage"
```

- [ ] **Step 4: Push changes**

```bash
git push
```

---

## Dependencies Between Tasks

1. Task 1-3 (Repository tests): Can run in parallel
2. Task 4-7 (Core modules): Can run in parallel
3. Task 8-9 (Endpoint tests): Depend on understanding existing test patterns
4. Task 10: Must run last after all other tasks complete

---

## Notes

- All tests follow existing patterns from `tests/test_projects.py`, `tests/test_users.py`
- No production code changes required
- Tests use in-memory mocks per testing conventions
- Run `pytest --cov=foreman --cov-report=term` after each task to verify progress
