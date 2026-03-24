"""Tests for generation management endpoints."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from foreman.api.deps import get_current_user, get_db
from foreman.main import app
from foreman.models.generation import Generation
from foreman.models.user import User

users_db: dict[uuid.UUID, User] = {}
generations_db: dict[uuid.UUID, Generation] = {}
generation_owners: dict[uuid.UUID, uuid.UUID] = {}


@pytest.fixture(autouse=True)
def mock_dependencies(monkeypatch):
    """Seed users, override dependencies, and mock generation CRUD."""
    now = datetime.now(timezone.utc)
    user_a_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    user_b_id = uuid.UUID("00000000-0000-0000-0000-000000000002")

    users_db[user_a_id] = User(
        id=user_a_id,
        email="usera@example.com",
        full_name="User A",
        is_active=True,
        is_deleted=False,
        created_at=now,
        updated_at=None,
    )
    users_db[user_b_id] = User(
        id=user_b_id,
        email="userb@example.com",
        full_name="User B",
        is_active=True,
        is_deleted=False,
        created_at=now,
        updated_at=None,
    )

    async def override_get_db():
        return None

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

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user

    async def mock_get_generation_by_id(db, generation_id, user_id):
        generation = generations_db.get(generation_id)
        if not generation:
            return None
        if generation_owners.get(generation_id) != user_id:
            return None
        return generation

    async def mock_delete_generation(db, generation_id, user_id):
        generation = generations_db.get(generation_id)
        if not generation:
            return False
        if generation_owners.get(generation_id) != user_id:
            return False

        del generations_db[generation_id]
        del generation_owners[generation_id]
        return True

    monkeypatch.setattr(
        "foreman.api.v1.endpoints.generations.repo.get_generation_by_id",
        mock_get_generation_by_id,
    )
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.generations.repo.delete_generation",
        mock_delete_generation,
    )

    yield

    users_db.clear()
    generations_db.clear()
    generation_owners.clear()
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def headers_a():
    """Auth headers for User A."""
    return {"X-User-ID": "00000000-0000-0000-0000-000000000001"}


@pytest.fixture
def headers_b():
    """Auth headers for User B."""
    return {"X-User-ID": "00000000-0000-0000-0000-000000000002"}


def _seed_generation(owner_header: dict[str, str], *, status: str = "pending") -> uuid.UUID:
    """Insert a generation row into the in-memory store for tests."""
    generation_id = uuid.uuid4()
    owner_id = uuid.UUID(owner_header["X-User-ID"])
    now = datetime.now(timezone.utc)
    generation = Generation(
        id=generation_id,
        project_id=uuid.uuid4(),
        parent_id=None,
        status=status,
        prompt="Design a bright living room",
        style_id="minimal",
        input_image_url="https://example.com/original.jpg",
        output_image_url=None,
        error_message=None,
        model_used="gpt-image-1",
        processing_time_ms=None,
        metadata={},
        created_at=now,
        updated_at=None,
    )
    generations_db[generation_id] = generation
    generation_owners[generation_id] = owner_id
    return generation_id


def test_get_generation_success(client, headers_a):
    """GET /v1/generations/{id} should return a scoped generation."""
    # Arrange
    generation_id = _seed_generation(headers_a)

    # Act
    response = client.get(f"/v1/generations/{generation_id}", headers=headers_a)

    # Assert
    assert response.status_code == 200
    body = response.json()
    assert body["id"] == str(generation_id)
    assert body["status"] == "pending"


def test_get_generation_not_found(client, headers_a):
    """GET /v1/generations/{id} should return 404 for unknown IDs."""
    # Act
    response = client.get(f"/v1/generations/{uuid.uuid4()}", headers=headers_a)

    # Assert
    assert response.status_code == 404


def test_get_generation_ownership(client, headers_a, headers_b):
    """A user cannot fetch another user's generation."""
    # Arrange
    generation_id = _seed_generation(headers_a)

    # Act
    response = client.get(f"/v1/generations/{generation_id}", headers=headers_b)

    # Assert
    assert response.status_code == 404


def test_delete_generation_success(client, headers_a):
    """DELETE /v1/generations/{id} should return 204 for owned generation."""
    # Arrange
    generation_id = _seed_generation(headers_a)

    # Act
    response = client.delete(f"/v1/generations/{generation_id}", headers=headers_a)

    # Assert
    assert response.status_code == 204
    get_response = client.get(f"/v1/generations/{generation_id}", headers=headers_a)
    assert get_response.status_code == 404


def test_delete_generation_not_found(client, headers_a):
    """DELETE /v1/generations/{id} should return 404 for unknown IDs."""
    # Act
    response = client.delete(f"/v1/generations/{uuid.uuid4()}", headers=headers_a)

    # Assert
    assert response.status_code == 404


def test_delete_generation_ownership(client, headers_a, headers_b):
    """A user cannot delete another user's generation."""
    # Arrange
    generation_id = _seed_generation(headers_a)

    # Act
    response = client.delete(f"/v1/generations/{generation_id}", headers=headers_b)

    # Assert
    assert response.status_code == 404


def test_get_generation_unauthenticated(client):
    """GET /v1/generations/{id} without auth should return 401."""
    # Act
    response = client.get(f"/v1/generations/{uuid.uuid4()}")

    # Assert
    assert response.status_code == 401


def test_delete_generation_unauthenticated(client):
    """DELETE /v1/generations/{id} without auth should return 401."""
    # Act
    response = client.delete(f"/v1/generations/{uuid.uuid4()}")

    # Assert
    assert response.status_code == 401


def test_delete_generation_internal_error_returns_500(client, headers_a, monkeypatch):
    """DELETE /v1/generations/{id} returns 500 on unexpected repository errors."""
    # Arrange
    generation_id = _seed_generation(headers_a)

    async def mock_error(*args, **kwargs):
        raise Exception("DB outage")

    monkeypatch.setattr("foreman.api.v1.endpoints.generations.repo.delete_generation", mock_error)

    # Act
    response = client.delete(f"/v1/generations/{generation_id}", headers=headers_a)

    # Assert
    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error"}
