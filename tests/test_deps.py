"""Tests for API dependencies."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from foreman.api.deps import get_current_user, get_db
from foreman.exceptions import ResourceNotFoundError
from foreman.models.user import User
from foreman.repositories import postgres_users_repository as crud

USER_ID = uuid.uuid4()
NOW = datetime.now(timezone.utc)


@pytest.fixture
def mock_db():
    return MagicMock()


@pytest.mark.asyncio
async def test_get_db_returns_database(mock_db):
    """get_db should return database from app state."""
    mock_request = MagicMock()
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
async def test_get_current_user_missing_header():
    """get_current_user should raise 401 when X-User-ID header is missing."""
    mock_db = MagicMock()

    with pytest.raises(HTTPException) as exc_info:
        await get_current_user(x_user_id=None, db=mock_db)

    assert exc_info.value.status_code == 401
    assert "missing" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_not_found():
    """get_current_user should raise 401 when user not found."""
    mock_db = MagicMock()

    with patch.object(crud, "get_user_by_id", side_effect=ResourceNotFoundError("User", "test")):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(x_user_id=str(USER_ID), db=mock_db)

    assert exc_info.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_inactive():
    """get_current_user should raise 401 for inactive user."""
    mock_db = MagicMock()
    inactive_user = User(
        id=USER_ID,
        email="test@example.com",
        full_name="Test",
        is_active=False,
        is_deleted=False,
        created_at=NOW,
        updated_at=None,
    )

    with patch.object(crud, "get_user_by_id", return_value=inactive_user):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(x_user_id=str(USER_ID), db=mock_db)

        assert exc_info.value.status_code == 401
        assert "inactive" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_deleted():
    """get_current_user should raise 401 for deleted user."""
    mock_db = MagicMock()
    deleted_user = User(
        id=USER_ID,
        email="test@example.com",
        full_name="Test",
        is_active=True,
        is_deleted=True,
        created_at=NOW,
        updated_at=None,
    )

    with patch.object(crud, "get_user_by_id", return_value=deleted_user):
        with pytest.raises(HTTPException) as exc_info:
            await get_current_user(x_user_id=str(USER_ID), db=mock_db)

        assert exc_info.value.status_code == 401
        assert "deleted" in exc_info.value.detail


@pytest.mark.asyncio
async def test_get_current_user_success():
    """get_current_user should return user for valid request."""
    mock_db = MagicMock()
    active_user = User(
        id=USER_ID,
        email="test@example.com",
        full_name="Test",
        is_active=True,
        is_deleted=False,
        created_at=NOW,
        updated_at=None,
    )

    with patch.object(crud, "get_user_by_id", return_value=active_user):
        result = await get_current_user(x_user_id=str(USER_ID), db=mock_db)

    assert result.id == USER_ID
    assert result.email == "test@example.com"
