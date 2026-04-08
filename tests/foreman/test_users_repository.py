"""Tests for postgres_users_repository."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from foreman.exceptions import DuplicateResourceError
from foreman.repositories import postgres_users_repository as repo
from foreman.schemas.user import UserCreate, UserUpdate

USER_ID = uuid.uuid4()
NOW = datetime.now(timezone.utc)


def make_user_record(user_id=USER_ID, email="test@example.com", full_name="Test"):
    """Helper to create a mock user record that properly converts to dict."""
    return {
        "id": user_id,
        "email": email,
        "full_name": full_name,
        "is_active": True,
        "is_deleted": False,
        "created_at": NOW,
        "updated_at": None,
    }


@pytest.fixture
def mock_db():
    return AsyncMock()


@pytest.mark.asyncio
async def test_get_user_by_email_found(mock_db):
    """get_user_by_email should return user when found."""
    mock_record = make_user_record()
    mock_db.fetchrow = AsyncMock(return_value=mock_record)

    result = await repo.get_user_by_email(mock_db, "test@example.com")
    assert result is not None
    assert result.email == "test@example.com"


@pytest.mark.asyncio
async def test_get_user_by_email_not_found(mock_db):
    """get_user_by_email should return None when not found."""
    mock_db.fetchrow = AsyncMock(return_value=None)

    result = await repo.get_user_by_email(mock_db, "notfound@example.com")
    assert result is None


@pytest.mark.asyncio
async def test_ensure_dev_user_returns_existing(mock_db):
    """ensure_dev_user should return existing user if found."""
    mock_record = make_user_record()
    mock_db.fetchrow = AsyncMock(return_value=mock_record)

    result = await repo.ensure_dev_user(mock_db)
    assert result.email == "test@example.com"
    mock_db.fetchrow.assert_called_once()


@pytest.mark.asyncio
async def test_ensure_dev_user_creates_if_not_exists(mock_db):
    """ensure_dev_user should create user if it doesn't exist."""

    def fetchrow_side_effect(*args):
        mock_record = make_user_record()
        return mock_record

    mock_db.fetchrow = AsyncMock(side_effect=[None, fetchrow_side_effect()])

    result = await repo.ensure_dev_user(mock_db)
    assert result.email == "test@example.com"


@pytest.mark.asyncio
async def test_ensure_dev_user_raises_on_insert_failure(mock_db):
    """ensure_dev_user should raise RuntimeError if insert fails."""
    mock_db.fetchrow = AsyncMock(return_value=None)

    with pytest.raises(RuntimeError, match="Failed to create dev test user"):
        await repo.ensure_dev_user(mock_db)


@pytest.mark.asyncio
async def test_update_user_no_fields_returns_existing(mock_db):
    """update_user with empty fields should return existing user."""
    mock_record = make_user_record()
    mock_db.fetchrow = AsyncMock(return_value=mock_record)

    result = await repo.update_user(mock_db, USER_ID, UserUpdate())
    assert result is not None


@pytest.mark.asyncio
async def test_update_user_updates_fields(mock_db):
    """update_user should update allowed fields."""
    mock_record = make_user_record(email="new@example.com")
    mock_db.fetchrow = AsyncMock(return_value=mock_record)

    result = await repo.update_user(mock_db, USER_ID, UserUpdate(email="new@example.com"))
    assert result is not None


@pytest.mark.asyncio
async def test_update_user_returns_none_when_not_found(mock_db):
    """update_user should return None when user not found."""
    mock_db.fetchrow = AsyncMock(return_value=None)

    result = await repo.update_user(mock_db, uuid.uuid4(), UserUpdate(email="new@example.com"))
    assert result is None


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
    mock_db.fetchrow = AsyncMock(side_effect=asyncpg.UniqueViolationError("duplicate"))

    with pytest.raises(DuplicateResourceError):
        await repo.create_user(mock_db, UserCreate(email="test@example.com", full_name="Test"))


@pytest.mark.asyncio
async def test_create_user_insert_failure(mock_db):
    """create_user should raise RuntimeError when insert returns None."""
    mock_db.fetchrow = AsyncMock(return_value=None)

    with pytest.raises(RuntimeError, match="Failed to create user record"):
        await repo.create_user(mock_db, UserCreate(email="test@example.com", full_name="Test"))
