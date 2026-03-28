"""Tests for postgres_images_repository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from foreman.models.image import Image
from foreman.repositories import postgres_images_repository as repo
from foreman.schemas.image import ImageCreate, ImageUpdate

USER_ID = uuid.uuid4()
PROJECT_ID = uuid.uuid4()


@pytest.fixture
def mock_db():
    """Mock database."""
    return AsyncMock()


@pytest.mark.asyncio
async def test_create_image_failure(mock_db, monkeypatch):
    """create_image should raise RuntimeError when DB returns no record."""
    mock_db.fetchrow = AsyncMock(return_value=None)

    image_in = ImageCreate(
        project_id=PROJECT_ID,
        user_id=USER_ID,
        filename="test.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        storage_key="test/key",
    )

    def mock_info(msg, *args, **kwargs):
        pass

    monkeypatch.setattr("foreman.repositories.postgres_images_repository.logger.info", mock_info)

    with pytest.raises(RuntimeError, match="Failed to create image record"):
        await repo.create_image(mock_db, image_in)


@pytest.mark.asyncio
async def test_update_image_no_fields_returns_existing(mock_db):
    """update_image with empty update_data should return existing image."""
    now = datetime.now(timezone.utc)
    image_id = uuid.uuid4()
    Image(
        id=image_id,
        project_id=PROJECT_ID,
        user_id=USER_ID,
        filename="test.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        storage_key="test/key",
        url=None,
        created_at=now,
        updated_at=None,
    )

    def create_record():
        return {
            "id": image_id,
            "project_id": PROJECT_ID,
            "user_id": USER_ID,
            "filename": "test.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 1024,
            "storage_key": "test/key",
            "url": None,
            "created_at": now,
            "updated_at": None,
        }

    mock_db.fetchrow = AsyncMock(side_effect=[create_record(), create_record()])

    result = await repo.update_image(mock_db, image_id, USER_ID, ImageUpdate())
    assert result is not None
    assert result.id == image_id


@pytest.mark.asyncio
async def test_update_image_not_found(mock_db):
    """update_image should return None when image not found."""
    mock_db.fetchrow = AsyncMock(return_value=None)

    result = await repo.update_image(
        mock_db, uuid.uuid4(), USER_ID, ImageUpdate(url="http://example.com")
    )
    assert result is None


@pytest.mark.asyncio
async def test_delete_image_returns_true(mock_db):
    """delete_image should return True when row is deleted."""
    mock_db.fetchrow = AsyncMock(return_value=MagicMock(id=uuid.uuid4()))

    result = await repo.delete_image(mock_db, uuid.uuid4(), USER_ID)
    assert result is True


@pytest.mark.asyncio
async def test_delete_image_returns_false_when_not_found(mock_db):
    """delete_image should return False when row not found."""
    mock_db.fetchrow = AsyncMock(return_value=None)

    result = await repo.delete_image(mock_db, uuid.uuid4(), USER_ID)
    assert result is False
