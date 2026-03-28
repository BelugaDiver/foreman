"""Tests for generation lifecycle action endpoints."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from foreman.api.deps import get_current_user, get_db
from foreman.exceptions import ResourceNotFoundError
from foreman.main import app
from foreman.models.generation import Generation
from foreman.models.user import User
from foreman.schemas.generation import GenerationCreate, GenerationUpdate

users_db: dict[uuid.UUID, User] = {}
generations_db: dict[uuid.UUID, Generation] = {}
generation_owners: dict[uuid.UUID, uuid.UUID] = {}
project_owners: dict[uuid.UUID, uuid.UUID] = {}


@pytest.fixture(autouse=True)
def mock_dependencies(monkeypatch):
    """Seed auth users, override dependencies, and mock generation CRUD actions."""
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
            raise ResourceNotFoundError("Generation", str(generation_id))
        if generation_owners.get(generation_id) != user_id:
            raise ResourceNotFoundError("Generation", str(generation_id))
        return generation

    async def mock_update_generation(db, generation_id, user_id, generation_in: GenerationUpdate):
        generation = generations_db.get(generation_id)
        if not generation:
            raise ResourceNotFoundError("Generation", str(generation_id))
        if generation_owners.get(generation_id) != user_id:
            raise ResourceNotFoundError("Generation", str(generation_id))

        updates = generation_in.model_dump(exclude_unset=True)
        for key, value in updates.items():
            setattr(generation, key, value)
        generation.updated_at = datetime.now(timezone.utc)
        return generation

    async def mock_create_generation(
        db, project_id, input_image_url, generation_in: GenerationCreate
    ):
        if project_id not in project_owners:
            raise RuntimeError("Missing project owner mapping")
        attempt = generation_in.attempt if generation_in.attempt is not None else 1
        generation = Generation(
            id=uuid.uuid4(),
            project_id=project_id,
            parent_id=generation_in.parent_id,
            status="pending",
            prompt=generation_in.prompt,
            style_id=generation_in.style_id,
            input_image_url=input_image_url,
            output_image_url=None,
            error_message=None,
            model_used=generation_in.model_used,
            processing_time_ms=None,
            attempt=attempt,
            metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=None,
        )
        generations_db[generation.id] = generation
        generation_owners[generation.id] = project_owners[project_id]
        return generation

    monkeypatch.setattr(
        "foreman.api.v1.endpoints.generations.repo.get_generation_by_id",
        mock_get_generation_by_id,
    )
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.generations.repo.update_generation",
        mock_update_generation,
    )
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.generations.repo.create_generation",
        mock_create_generation,
    )

    yield

    users_db.clear()
    generations_db.clear()
    generation_owners.clear()
    project_owners.clear()
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """Create a test client for lifecycle endpoint tests."""
    return TestClient(app)


@pytest.fixture
def headers_a():
    """Auth headers for User A."""
    return {"X-User-ID": "00000000-0000-0000-0000-000000000001"}


@pytest.fixture
def headers_b():
    """Auth headers for User B."""
    return {"X-User-ID": "00000000-0000-0000-0000-000000000002"}


def _seed_generation(
    owner_headers: dict[str, str],
    *,
    status: str,
    output_image_url: str | None,
    parent_id: uuid.UUID | None = None,
) -> Generation:
    """Insert a generation into in-memory stores for lifecycle tests."""
    owner_id = uuid.UUID(owner_headers["X-User-ID"])
    project_id = uuid.uuid4()
    project_owners[project_id] = owner_id
    generation = Generation(
        id=uuid.uuid4(),
        project_id=project_id,
        parent_id=parent_id,
        status=status,
        prompt="Redesign this room",
        style_id="modern",
        input_image_url="https://example.com/original.jpg",
        output_image_url=output_image_url,
        error_message=None,
        model_used="gpt-image-1",
        processing_time_ms=None,
        attempt=1,
        metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=None,
    )
    generations_db[generation.id] = generation
    generation_owners[generation.id] = owner_id
    return generation


def test_cancel_generation_success(client, headers_a):
    """Pending generation should transition to cancelled."""
    # Arrange
    generation = _seed_generation(headers_a, status="pending", output_image_url=None)

    # Act
    response = client.post(f"/v1/generations/{generation.id}/cancel", headers=headers_a)

    # Assert
    assert response.status_code == 200
    assert response.json()["status"] == "cancelled"


def test_cancel_generation_rejects_terminal_state(client, headers_a):
    """Completed generation cannot be cancelled."""
    # Arrange
    generation = _seed_generation(
        headers_a,
        status="completed",
        output_image_url="https://example.com/result.jpg",
    )

    # Act
    response = client.post(f"/v1/generations/{generation.id}/cancel", headers=headers_a)

    # Assert
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Cannot cancel Generation in state 'completed'. Valid states: pending or processing"
    )


def test_cancel_generation_not_found_for_other_owner(client, headers_a, headers_b):
    """Cancelling another user's generation should return 404."""
    # Arrange
    generation = _seed_generation(headers_a, status="processing", output_image_url=None)

    # Act
    response = client.post(f"/v1/generations/{generation.id}/cancel", headers=headers_b)

    # Assert
    assert response.status_code == 404


def test_retry_generation_creates_new_record(client, headers_a):
    """Retry should create a new generation with same input, preserving original parent."""
    # Arrange
    original = _seed_generation(headers_a, status="failed", output_image_url=None)

    # Act
    response = client.post(f"/v1/generations/{original.id}/retry", headers=headers_a)

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["id"] != str(original.id)
    assert body["project_id"] == str(original.project_id)
    assert body["input_image_url"] == original.input_image_url
    # Retry preserves original parent (idempotent re-run)
    assert body["parent_id"] == (str(original.parent_id) if original.parent_id else None)
    assert body["attempt"] == 2


def test_retry_rejects_completed(client, headers_a):
    """Retry should return 400 when the generation is completed."""
    # Arrange
    original = _seed_generation(
        headers_a, status="completed", output_image_url="https://example.com/out.jpg"
    )

    # Act
    response = client.post(f"/v1/generations/{original.id}/retry", headers=headers_a)

    # Assert
    assert response.status_code == 400
    assert "Cannot retry Generation in state" in response.json()["detail"]


def test_retry_rejects_pending(client, headers_a):
    """Retry should return 400 when the generation is still pending."""
    # Arrange
    original = _seed_generation(headers_a, status="pending", output_image_url=None)

    # Act
    response = client.post(f"/v1/generations/{original.id}/retry", headers=headers_a)

    # Assert
    assert response.status_code == 400


def test_retry_rejects_processing(client, headers_a):
    """Retry should return 400 when the generation is still processing."""
    # Arrange
    original = _seed_generation(headers_a, status="processing", output_image_url=None)

    # Act
    response = client.post(f"/v1/generations/{original.id}/retry", headers=headers_a)

    # Assert
    assert response.status_code == 400


def test_fork_generation_creates_child_from_output(client, headers_a):
    """Fork should create a child generation using parent's output image as input."""
    # Arrange
    parent = _seed_generation(
        headers_a,
        status="completed",
        output_image_url="https://example.com/completed.jpg",
    )

    # Act
    response = client.post(f"/v1/generations/{parent.id}/fork", headers=headers_a)

    # Assert
    assert response.status_code == 201
    body = response.json()
    assert body["parent_id"] == str(parent.id)
    assert body["input_image_url"] == "https://example.com/completed.jpg"


def test_fork_generation_requires_output_image(client, headers_a):
    """Fork should fail when the parent generation has no output image."""
    # Arrange
    parent = _seed_generation(headers_a, status="failed", output_image_url=None)

    # Act
    response = client.post(f"/v1/generations/{parent.id}/fork", headers=headers_a)

    # Assert
    assert response.status_code == 400
    assert (
        response.json()["detail"]
        == "Cannot fork Generation in state 'no output'. Valid states: has output image"
    )


def test_lifecycle_actions_require_auth(client):
    """Lifecycle routes should reject unauthenticated requests."""
    # Arrange
    generation_id = uuid.uuid4()

    # Act
    cancel_response = client.post(f"/v1/generations/{generation_id}/cancel")
    retry_response = client.post(f"/v1/generations/{generation_id}/retry")
    fork_response = client.post(f"/v1/generations/{generation_id}/fork")

    # Assert
    assert cancel_response.status_code == 401
    assert retry_response.status_code == 401
    assert fork_response.status_code == 401
