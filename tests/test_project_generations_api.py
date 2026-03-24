"""Tests for project-nested generations endpoints."""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

from foreman.api.deps import get_current_user, get_db
from foreman.main import app
from foreman.models.generation import Generation
from foreman.models.project import Project
from foreman.models.user import User
from foreman.schemas.generation import GenerationCreate
from foreman.schemas.project import ProjectCreate

users_db: dict[uuid.UUID, User] = {}
projects_db: dict[uuid.UUID, Project] = {}
generations_db: dict[uuid.UUID, Generation] = {}
generation_owners: dict[uuid.UUID, uuid.UUID] = {}


@pytest.fixture(autouse=True)
def mock_dependencies(monkeypatch):
    """Seed users, override app dependencies, and mock project/generation repositories."""
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

    async def mock_create_project(db, user_id, project_in: ProjectCreate):
        project = Project(
            id=uuid.uuid4(),
            user_id=user_id,
            name=project_in.name,
            original_image_url=project_in.original_image_url,
            room_analysis=None,
            created_at=datetime.now(timezone.utc),
            updated_at=None,
        )
        projects_db[project.id] = project
        return project

    async def mock_get_project_by_id(db, project_id, user_id):
        project = projects_db.get(project_id)
        if not project:
            return None
        if project.user_id != user_id:
            return None
        return project

    async def mock_get_generation_by_id(db, generation_id, user_id):
        generation = generations_db.get(generation_id)
        if not generation:
            return None
        if generation_owners.get(generation_id) != user_id:
            return None
        return generation

    async def mock_create_generation(db, project_id, input_image_url, generation_in: GenerationCreate):
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
            metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=None,
        )
        generations_db[generation.id] = generation
        project = projects_db.get(project_id)
        if not project:
            raise RuntimeError("Project not found while creating generation")
        generation_owners[generation.id] = project.user_id
        return generation

    async def mock_list_generations_by_project(db, project_id, user_id, limit=20, offset=0):
        rows = [
            generation
            for generation_id, generation in generations_db.items()
            if generation.project_id == project_id and generation_owners.get(generation_id) == user_id
        ]
        rows.sort(key=lambda row: row.created_at, reverse=True)
        return rows[offset : offset + limit]

    monkeypatch.setattr(
        "foreman.api.v1.endpoints.projects.crud.create_project",
        mock_create_project,
    )
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.projects.crud.get_project_by_id",
        mock_get_project_by_id,
    )
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.projects.gen_repo.get_generation_by_id",
        mock_get_generation_by_id,
    )
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.projects.gen_repo.create_generation",
        mock_create_generation,
    )
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.projects.gen_repo.list_generations_by_project",
        mock_list_generations_by_project,
    )

    yield

    users_db.clear()
    projects_db.clear()
    generations_db.clear()
    generation_owners.clear()
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """TestClient for API tests."""
    return TestClient(app)


@pytest.fixture
def headers_a():
    """Auth headers for User A."""
    return {"X-User-ID": "00000000-0000-0000-0000-000000000001"}


@pytest.fixture
def headers_b():
    """Auth headers for User B."""
    return {"X-User-ID": "00000000-0000-0000-0000-000000000002"}


def _create_project(client: TestClient, headers: dict[str, str], image_url: str | None) -> dict:
    """Create a project via API for nested generations tests."""
    payload = {"name": "Design Project"}
    if image_url is not None:
        payload["original_image_url"] = image_url
    response = client.post("/v1/projects/", headers=headers, json=payload)
    assert response.status_code == 201
    return response.json()


def _seed_completed_generation(owner_headers: dict[str, str], project_id: str) -> Generation:
    """Insert a completed generation row directly into in-memory store."""
    generation_id = uuid.uuid4()
    owner_id = uuid.UUID(owner_headers["X-User-ID"])
    generation = Generation(
        id=generation_id,
        project_id=uuid.UUID(project_id),
        parent_id=None,
        status="completed",
        prompt="Initial design",
        style_id="minimal",
        input_image_url="https://example.com/original.jpg",
        output_image_url="https://example.com/completed.jpg",
        error_message=None,
        model_used="gpt-image-1",
        processing_time_ms=900,
        metadata={},
        created_at=datetime.now(timezone.utc),
        updated_at=None,
    )
    generations_db[generation_id] = generation
    generation_owners[generation_id] = owner_id
    return generation


def test_create_generation_root_success(client, headers_a):
    """POST nested generation should use the project's original image for root jobs."""
    # Arrange
    project = _create_project(client, headers_a, image_url="https://example.com/original.jpg")

    # Act
    response = client.post(
        f"/v1/projects/{project['id']}/generations",
        headers=headers_a,
        json={"prompt": "Add warm lighting"},
    )

    # Assert
    assert response.status_code == 202
    body = response.json()
    assert body["project_id"] == project["id"]
    assert body["input_image_url"] == "https://example.com/original.jpg"
    assert response.headers["location"].startswith("/v1/generations/")


def test_create_generation_requires_project_image_for_root(client, headers_a):
    """Root generation should fail when project has no original image."""
    # Arrange
    project = _create_project(client, headers_a, image_url=None)

    # Act
    response = client.post(
        f"/v1/projects/{project['id']}/generations",
        headers=headers_a,
        json={"prompt": "Generate from missing input"},
    )

    # Assert
    assert response.status_code == 400
    assert response.json() == {"detail": "Project has no original image"}


def test_create_generation_with_parent_success(client, headers_a):
    """Child generation should use parent output image when parent_id is provided."""
    # Arrange
    project = _create_project(client, headers_a, image_url="https://example.com/original.jpg")
    parent = _seed_completed_generation(headers_a, project["id"])

    # Act
    response = client.post(
        f"/v1/projects/{project['id']}/generations",
        headers=headers_a,
        json={"prompt": "Add plants", "parent_id": str(parent.id)},
    )

    # Assert
    assert response.status_code == 202
    body = response.json()
    assert body["parent_id"] == str(parent.id)
    assert body["input_image_url"] == "https://example.com/completed.jpg"


def test_create_generation_rejects_parent_from_other_project(client, headers_a):
    """Parent generation must belong to the same project as the new generation."""
    # Arrange
    project_a = _create_project(client, headers_a, image_url="https://example.com/original-a.jpg")
    project_b = _create_project(client, headers_a, image_url="https://example.com/original-b.jpg")
    parent = _seed_completed_generation(headers_a, project_b["id"])

    # Act
    response = client.post(
        f"/v1/projects/{project_a['id']}/generations",
        headers=headers_a,
        json={"prompt": "Wrong parent", "parent_id": str(parent.id)},
    )

    # Assert
    assert response.status_code == 400
    assert response.json() == {"detail": "Parent belongs to different project"}


def test_create_generation_rejects_invalid_parent(client, headers_a):
    """Parent generation must exist and be visible to current user."""
    # Arrange
    project = _create_project(client, headers_a, image_url="https://example.com/original.jpg")

    # Act
    response = client.post(
        f"/v1/projects/{project['id']}/generations",
        headers=headers_a,
        json={"prompt": "Bad parent", "parent_id": str(uuid.uuid4())},
    )

    # Assert
    assert response.status_code == 400
    assert response.json() == {"detail": "Invalid parent generation"}


def test_list_project_generations_scoped_by_project_and_user(client, headers_a, headers_b):
    """List endpoint should return only generations for the requested project and owner."""
    # Arrange
    project_a1 = _create_project(client, headers_a, image_url="https://example.com/a1.jpg")
    project_a2 = _create_project(client, headers_a, image_url="https://example.com/a2.jpg")
    project_b1 = _create_project(client, headers_b, image_url="https://example.com/b1.jpg")

    response_1 = client.post(
        f"/v1/projects/{project_a1['id']}/generations",
        headers=headers_a,
        json={"prompt": "A1 gen"},
    )
    assert response_1.status_code == 202

    response_2 = client.post(
        f"/v1/projects/{project_a2['id']}/generations",
        headers=headers_a,
        json={"prompt": "A2 gen"},
    )
    assert response_2.status_code == 202

    response_3 = client.post(
        f"/v1/projects/{project_b1['id']}/generations",
        headers=headers_b,
        json={"prompt": "B1 gen"},
    )
    assert response_3.status_code == 202

    # Act
    list_response_a = client.get(f"/v1/projects/{project_a1['id']}/generations", headers=headers_a)
    list_response_b = client.get(f"/v1/projects/{project_a1['id']}/generations", headers=headers_b)

    # Assert
    assert list_response_a.status_code == 200
    assert len(list_response_a.json()) == 1
    assert list_response_a.json()[0]["prompt"] == "A1 gen"

    # User B doesn't own project_a1, should get 404
    assert list_response_b.status_code == 404


def test_nested_generation_routes_require_auth(client):
    """Nested generation routes should reject unauthenticated requests."""
    # Arrange
    project_id = uuid.uuid4()

    # Act
    create_response = client.post(
        f"/v1/projects/{project_id}/generations",
        json={"prompt": "No auth"},
    )
    list_response = client.get(f"/v1/projects/{project_id}/generations")

    # Assert
    assert create_response.status_code == 401
    assert list_response.status_code == 401
