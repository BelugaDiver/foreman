"""Tests for user management endpoints."""

# ---------------------------------------------------------------------------
# Stdlib
# ---------------------------------------------------------------------------
import uuid
from datetime import datetime, timezone

# ---------------------------------------------------------------------------
# Third-party
# ---------------------------------------------------------------------------
import pytest
from asyncpg.exceptions import UniqueViolationError
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Local
# ---------------------------------------------------------------------------
from foreman.api.deps import get_current_user, get_db
from foreman.main import app
from foreman.models.user import User
from foreman.schemas.user import UserCreate, UserUpdate

# In-memory store for tests
users_db = {}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_dependencies(monkeypatch):
    """Mock database and CRUD operations for endpoint tests."""

    async def override_get_db():
        return None  # Replaced by mocked CRUD functions

    async def override_get_current_user(x_user_id: str | None = Header(None)):
        if not x_user_id:
            raise HTTPException(status_code=401, detail="X-User-ID header missing")
        try:
            uid = uuid.UUID(x_user_id)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid X-User-ID")

        if uid not in users_db:
            raise HTTPException(status_code=401, detail="User not found")

        user = users_db[uid]
        if not user.is_active or user.is_deleted:
            raise HTTPException(status_code=401, detail="User is inactive or deleted")
        return user

    # Override FastAPI dependencies
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    # Mock CRUD functions
    async def mock_create_user(db, user_in: UserCreate):
        for u in users_db.values():
            if u.email == user_in.email:
                raise UniqueViolationError("unique constraint violation")
        new_user = User(
            id=uuid.uuid4(),
            email=user_in.email,
            full_name=user_in.full_name,
            is_active=True,
            is_deleted=False,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        users_db[new_user.id] = new_user
        return new_user

    async def mock_update_user(db, user_id, user_in: UserUpdate):
        if user_id not in users_db:
            return None
        user = users_db[user_id]
        if user_in.email is not None:
            user.email = user_in.email
        if user_in.full_name is not None:
            user.full_name = user_in.full_name
        return user

    async def mock_soft_delete_user(db, user_id):
        if user_id not in users_db:
            return False
        user = users_db[user_id]
        user.is_deleted = True
        user.is_active = False
        return True

    monkeypatch.setattr("foreman.api.v1.endpoints.users.crud.create_user", mock_create_user)
    monkeypatch.setattr("foreman.api.v1.endpoints.users.crud.update_user", mock_update_user)
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.users.crud.soft_delete_user", mock_soft_delete_user
    )

    yield

    users_db.clear()
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_create_user(client):
    """POST /v1/users/ with valid data should return 201 and the new user."""
    # Arrange
    payload = {"email": "test_create@example.com", "full_name": "Test Create User"}

    # Act
    response = client.post("/v1/users/", json=payload)

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test_create@example.com"
    assert "id" in data


def test_create_user_duplicate_email_returns_400(client):
    """POST /v1/users/ with a duplicate e-mail should return 400."""
    # Arrange
    payload = {"email": "dupe@example.com", "full_name": "First"}
    client.post("/v1/users/", json=payload)

    # Act
    response = client.post("/v1/users/", json={"email": "dupe@example.com", "full_name": "Second"})

    # Assert
    assert response.status_code == 400


def test_get_user_me(client):
    """GET /v1/users/me should return the authenticated user's profile."""
    # Arrange
    create_resp = client.post(
        "/v1/users/", json={"email": "test_me@example.com", "full_name": "Me User"}
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]

    # Act
    response = client.get("/v1/users/me", headers={"X-User-ID": user_id})

    # Assert
    assert response.status_code == 200
    assert response.json()["email"] == "test_me@example.com"


def test_update_user_me(client):
    """PATCH /v1/users/me should update the authenticated user's profile."""
    # Arrange
    create_resp = client.post(
        "/v1/users/", json={"email": "test_update@example.com", "full_name": "Update User"}
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]

    # Act
    response = client.patch(
        "/v1/users/me",
        headers={"X-User-ID": user_id},
        json={"full_name": "Updated Name"},
    )

    # Assert
    assert response.status_code == 200
    assert response.json()["full_name"] == "Updated Name"


def test_delete_user_me(client):
    """DELETE /v1/users/me should soft-delete the user; subsequent GET returns 401."""
    # Arrange
    create_resp = client.post(
        "/v1/users/", json={"email": "test_delete@example.com", "full_name": "Delete User"}
    )
    assert create_resp.status_code == 201
    user_id = create_resp.json()["id"]

    # Act
    delete_resp = client.delete("/v1/users/me", headers={"X-User-ID": user_id})

    # Assert
    assert delete_resp.status_code == 204
    # Soft-deleted user is rejected by the auth dependency
    get_resp = client.get("/v1/users/me", headers={"X-User-ID": user_id})
    assert get_resp.status_code == 401


def test_create_user_internal_error_returns_500(client, monkeypatch):
    """POST /v1/users/ returns 500 if crud raises an unexpected exception."""

    # Arrange
    async def mock_err(*args, **kwargs):
        raise Exception("DB failure")

    monkeypatch.setattr("foreman.api.v1.endpoints.users.crud.create_user", mock_err)

    # Act
    response = client.post("/v1/users/", json={"email": "500@example.com", "full_name": "500"})

    # Assert
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}


def test_update_user_internal_error_returns_500(client, monkeypatch):
    """PATCH /v1/users/me returns 500 if crud raises an unexpected exception."""
    # Arrange
    create_resp = client.post(
        "/v1/users/", json={"email": "patch500@example.com", "full_name": "Ready"}
    )
    user_id = create_resp.json()["id"]

    async def mock_err(*args, **kwargs):
        raise Exception("Disk full")

    monkeypatch.setattr("foreman.api.v1.endpoints.users.crud.update_user", mock_err)

    # Act
    response = client.patch(
        "/v1/users/me",
        headers={"X-User-ID": user_id},
        json={"full_name": "Boom"},
    )

    # Assert
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}


def test_delete_user_internal_error_returns_500(client, monkeypatch):
    """DELETE /v1/users/me returns 500 if crud raises an unexpected exception."""
    # Arrange
    create_resp = client.post(
        "/v1/users/", json={"email": "del500@example.com", "full_name": "Ready"}
    )
    user_id = create_resp.json()["id"]

    async def mock_err(*args, **kwargs):
        raise Exception("Network issue")

    monkeypatch.setattr("foreman.api.v1.endpoints.users.crud.soft_delete_user", mock_err)

    # Act
    response = client.delete("/v1/users/me", headers={"X-User-ID": user_id})

    # Assert
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
