"""Tests for project management endpoints."""

# ---------------------------------------------------------------------------
# Stdlib
# ---------------------------------------------------------------------------
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock

# ---------------------------------------------------------------------------
# Third-party
# ---------------------------------------------------------------------------
import pytest
from fastapi import Header, HTTPException
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Local
# ---------------------------------------------------------------------------
from foreman.api.deps import get_current_user, get_db
from foreman.exceptions import ResourceNotFoundError
from foreman.main import app
from foreman.models.project import Project
from foreman.models.user import User
from foreman.schemas.project import ProjectCreate, ProjectUpdate

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
users_db: dict[uuid.UUID, User] = {}
projects_db: dict[uuid.UUID, Project] = {}

# Two fixed users seeded before each test
USER_A_ID = uuid.uuid4()
USER_B_ID = uuid.uuid4()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_dependencies(monkeypatch):
    """Seed users, mock DB + CRUD, override FastAPI dependencies."""

    now = datetime.now(timezone.utc)
    users_db[USER_A_ID] = User(
        id=USER_A_ID,
        email="usera@example.com",
        full_name="User A",
        is_active=True,
        is_deleted=False,
        created_at=now,
        updated_at=None,
    )
    users_db[USER_B_ID] = User(
        id=USER_B_ID,
        email="userb@example.com",
        full_name="User B",
        is_active=True,
        is_deleted=False,
        created_at=now,
        updated_at=None,
    )

    # ------------------------------------------------------------------
    # Dependency overrides
    # ------------------------------------------------------------------

    async def override_get_db():
        return None  # CRUD is monkeypatched; DB is never touched

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

    # ------------------------------------------------------------------
    # Mock CRUD functions
    # ------------------------------------------------------------------

    async def mock_list_projects(db, user_id, limit=20, offset=0):
        results = [p for p in projects_db.values() if p.user_id == user_id]
        return results[offset : offset + limit]

    async def mock_get_project_by_id(db, project_id, user_id):
        project = projects_db.get(project_id)
        if not project or project.user_id != user_id:
            raise ResourceNotFoundError("Project", str(project_id))
        return project

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

    async def mock_update_project(db, project_id, user_id, project_in: ProjectUpdate):
        project = projects_db.get(project_id)
        if not project or project.user_id != user_id:
            raise ResourceNotFoundError("Project", str(project_id))
        for key, value in project_in.model_dump(exclude_unset=True).items():
            setattr(project, key, value)
        project.updated_at = datetime.now(timezone.utc)
        return project

    async def mock_delete_project(db, project_id, user_id):
        project = projects_db.get(project_id)
        if not project or project.user_id != user_id:
            raise ResourceNotFoundError("Project", str(project_id))
        del projects_db[project_id]

    monkeypatch.setattr("foreman.api.v1.endpoints.projects.crud.list_projects", mock_list_projects)
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.projects.crud.get_project_by_id",
        mock_get_project_by_id,
    )
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.projects.crud.create_project", mock_create_project
    )
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.projects.crud.update_project", mock_update_project
    )
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.projects.crud.delete_project", mock_delete_project
    )

    yield

    users_db.clear()
    projects_db.clear()
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """TestClient for the FastAPI app."""
    return TestClient(app)


@pytest.fixture
def headers_a():
    """Auth headers for User A."""
    return {"X-User-ID": str(USER_A_ID)}


@pytest.fixture
def headers_b():
    """Auth headers for User B."""
    return {"X-User-ID": str(USER_B_ID)}


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


def create_project(client, headers, name="Test Project", image_url=None):
    """Create a project via the API and assert success."""
    body = {"name": name}
    if image_url:
        body["original_image_url"] = image_url
    resp = client.post("/v1/projects/", headers=headers, json=body)
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_projects_empty(client, headers_a):
    """GET /v1/projects/ with no projects should return an empty list."""
    # Arrange — store is empty by default

    # Act
    resp = client.get("/v1/projects/", headers=headers_a)

    # Assert
    assert resp.status_code == 200
    assert resp.json() == []


def test_create_project(client, headers_a):
    """POST /v1/projects/ with valid data should return 201 and the new project."""
    # Arrange
    payload = {"name": "Living Room", "original_image_url": "https://example.com/img.jpg"}

    # Act
    resp = client.post("/v1/projects/", headers=headers_a, json=payload)

    # Assert
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "Living Room"
    assert data["original_image_url"] == "https://example.com/img.jpg"
    assert data["user_id"] == str(USER_A_ID)
    assert data["room_analysis"] is None
    assert "id" in data
    assert "created_at" in data


def test_create_project_name_only(client, headers_a):
    """original_image_url is optional; omitting it should return null in the response."""
    # Arrange
    payload = {"name": "Bedroom"}

    # Act
    resp = client.post("/v1/projects/", headers=headers_a, json=payload)

    # Assert
    assert resp.status_code == 201
    assert resp.json()["original_image_url"] is None


def test_create_project_missing_name_returns_422(client, headers_a):
    """POST /v1/projects/ without a required name field should return 422."""
    # Arrange
    payload = {}

    # Act
    resp = client.post("/v1/projects/", headers=headers_a, json=payload)

    # Assert
    assert resp.status_code == 422


def test_list_projects_after_create(client, headers_a):
    """GET /v1/projects/ should reflect all projects created by the user."""
    # Arrange
    create_project(client, headers_a, name="Project 1")
    create_project(client, headers_a, name="Project 2")

    # Act
    resp = client.get("/v1/projects/", headers=headers_a)

    # Assert
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_projects_only_own(client, headers_a, headers_b):
    """User A's list should not include User B's projects."""
    # Arrange
    create_project(client, headers_a, name="A's Project")
    create_project(client, headers_b, name="B's Project")

    # Act
    resp = client.get("/v1/projects/", headers=headers_a)

    # Assert
    assert len(resp.json()) == 1
    assert resp.json()[0]["name"] == "A's Project"


def test_get_project(client, headers_a):
    """GET /v1/projects/{id} should return the matching project."""
    # Arrange
    data = create_project(client, headers_a, name="Kitchen")
    project_id = data["id"]

    # Act
    resp = client.get(f"/v1/projects/{project_id}", headers=headers_a)

    # Assert
    assert resp.status_code == 200
    assert resp.json()["name"] == "Kitchen"


def test_get_project_not_found(client, headers_a):
    """GET /v1/projects/{id} with an unknown ID should return 404."""
    # Arrange — no project created

    # Act
    resp = client.get(f"/v1/projects/{uuid.uuid4()}", headers=headers_a)

    # Assert
    assert resp.status_code == 404


def test_update_project(client, headers_a):
    """PATCH /v1/projects/{id} should update the provided fields and set updated_at."""
    # Arrange
    data = create_project(client, headers_a, name="Den")
    project_id = data["id"]

    # Act
    resp = client.patch(
        f"/v1/projects/{project_id}",
        headers=headers_a,
        json={"name": "Den Updated", "room_analysis": {"style": "modern", "colors": ["white"]}},
    )

    # Assert
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Den Updated"
    assert body["room_analysis"] == {"style": "modern", "colors": ["white"]}
    assert body["updated_at"] is not None


def test_update_project_partial(client, headers_a):
    """Only the provided fields should change; untouched fields should be preserved."""
    # Arrange
    data = create_project(
        client, headers_a, name="Office", image_url="https://example.com/before.jpg"
    )
    project_id = data["id"]

    # Act
    resp = client.patch(
        f"/v1/projects/{project_id}",
        headers=headers_a,
        json={"name": "Home Office"},
    )

    # Assert
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Home Office"
    assert body["original_image_url"] == "https://example.com/before.jpg"


def test_update_project_not_found(client, headers_a):
    """PATCH /v1/projects/{id} with an unknown ID should return 404."""
    # Arrange — no project created

    # Act
    resp = client.patch(
        f"/v1/projects/{uuid.uuid4()}",
        headers=headers_a,
        json={"name": "Ghost"},
    )

    # Assert
    assert resp.status_code == 404


def test_update_project_rejects_extra_fields(client, headers_a):
    """PATCH /v1/projects/{id} with unknown fields should return 422."""
    # Arrange
    data = create_project(client, headers_a, name="Study")

    # Act
    resp = client.patch(
        f"/v1/projects/{data['id']}",
        headers=headers_a,
        json={"unknown_field": "value"},
    )

    # Assert
    assert resp.status_code == 422


def test_delete_project(client, headers_a):
    """DELETE /v1/projects/{id} should return 204; subsequent GET should return 404."""
    # Arrange
    data = create_project(client, headers_a, name="Basement")
    project_id = data["id"]

    # Act
    del_resp = client.delete(f"/v1/projects/{project_id}", headers=headers_a)

    # Assert
    assert del_resp.status_code == 204
    get_resp = client.get(f"/v1/projects/{project_id}", headers=headers_a)
    assert get_resp.status_code == 404


def test_delete_project_not_found(client, headers_a):
    """DELETE /v1/projects/{id} with an unknown ID should return 404."""
    # Arrange — no project created

    # Act
    resp = client.delete(f"/v1/projects/{uuid.uuid4()}", headers=headers_a)

    # Assert
    assert resp.status_code == 404


def test_project_ownership_get(client, headers_a, headers_b):
    """User B cannot read User A's project."""
    # Arrange
    data = create_project(client, headers_a, name="Private Room")

    # Act
    resp = client.get(f"/v1/projects/{data['id']}", headers=headers_b)

    # Assert
    assert resp.status_code == 404


def test_project_ownership_patch(client, headers_a, headers_b):
    """User B cannot update User A's project."""
    # Arrange
    data = create_project(client, headers_a, name="Secret Office")

    # Act
    resp = client.patch(f"/v1/projects/{data['id']}", headers=headers_b, json={"name": "Hijacked"})

    # Assert
    assert resp.status_code == 404


def test_project_ownership_delete(client, headers_a, headers_b):
    """User B cannot delete User A's project."""
    # Arrange
    data = create_project(client, headers_a, name="Vault")

    # Act
    resp = client.delete(f"/v1/projects/{data['id']}", headers=headers_b)

    # Assert
    assert resp.status_code == 404


def test_unauthenticated_list(client):
    """GET /v1/projects/ without auth header should return 401."""
    # Arrange — no headers provided

    # Act
    resp = client.get("/v1/projects/")

    # Assert
    assert resp.status_code == 401


def test_unauthenticated_create(client):
    """POST /v1/projects/ without auth header should return 401."""
    # Arrange — no headers provided

    # Act
    resp = client.post("/v1/projects/", json={"name": "Sneaky"})

    # Assert
    assert resp.status_code == 401


def test_create_project_internal_error_returns_500(client, headers_a, monkeypatch):
    """POST /v1/projects/ returns 500 if crud raises an unexpected exception."""

    # Arrange
    async def mock_err(*args, **kwargs):
        raise Exception("DB is down!")

    monkeypatch.setattr("foreman.api.v1.endpoints.projects.crud.create_project", mock_err)

    # Act
    resp = client.post("/v1/projects/", headers=headers_a, json={"name": "Boom"})

    # Assert
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}


def test_update_project_internal_error_returns_500(client, headers_a, monkeypatch):
    """PATCH /v1/projects/{id} returns 500 if crud raises an unexpected exception."""
    # Arrange
    data = create_project(client, headers_a, name="Before explosion")

    async def mock_err(*args, **kwargs):
        raise Exception("Network timeout")

    monkeypatch.setattr("foreman.api.v1.endpoints.projects.crud.update_project", mock_err)

    # Act
    resp = client.patch(f"/v1/projects/{data['id']}", headers=headers_a, json={"name": "Will fail"})

    # Assert
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}


def test_delete_project_internal_error_returns_500(client, headers_a, monkeypatch):
    """DELETE /v1/projects/{id} returns 500 if crud raises an unexpected exception."""
    # Arrange
    data = create_project(client, headers_a, name="Before explosion")

    async def mock_err(*args, **kwargs):
        raise Exception("Out of memory")

    monkeypatch.setattr("foreman.api.v1.endpoints.projects.crud.delete_project", mock_err)

    # Act
    resp = client.delete(f"/v1/projects/{data['id']}", headers=headers_a)

    # Assert
    assert resp.status_code == 500
    assert resp.json() == {"detail": "Internal server error"}


def test_create_generation_publishes_to_queue(client, headers_a, monkeypatch):
    """Creating a generation should publish a message to SQS."""
    from foreman.models.generation import Generation
    from foreman.queue.protocol import QueueMessage
    from foreman.schemas.generation import GenerationCreate

    # Set up project with image
    project_id = uuid.uuid4()
    projects_db[project_id] = Project(
        id=project_id,
        user_id=USER_A_ID,
        name="Test Project",
        original_image_url="https://example.com/room.jpg",
        room_analysis=None,
        created_at=datetime.now(timezone.utc),
        updated_at=None,
    )

    # Mock generation repository functions
    async def mock_get_generation_by_id(db, generation_id, user_id):
        raise ResourceNotFoundError("Generation", str(generation_id))

    async def mock_create_generation(
        db, project_id, input_image_url, generation_in: GenerationCreate
    ):
        return Generation(
            id=uuid.uuid4(),
            project_id=project_id,
            parent_id=generation_in.parent_id,
            prompt=generation_in.prompt,
            style_id=generation_in.style_id,
            model_used=generation_in.model_used,
            input_image_url=input_image_url,
            output_image_url=None,
            status="pending",
            attempt=generation_in.attempt or 1,
            error_message=None,
            processing_time_ms=None,
            metadata={},
            created_at=datetime.now(timezone.utc),
            updated_at=None,
        )

    monkeypatch.setattr(
        "foreman.api.v1.endpoints.projects.gen_repo.get_generation_by_id",
        mock_get_generation_by_id,
    )
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.projects.gen_repo.create_generation",
        mock_create_generation,
    )

    # Mock queue
    mock_queue = AsyncMock()
    mock_queue.publish.return_value = "test-message-id"
    monkeypatch.setattr("foreman.api.v1.endpoints.projects.get_queue", lambda: mock_queue)

    # Create generation
    resp = client.post(
        f"/v1/projects/{project_id}/generations",
        headers=headers_a,
        json={"prompt": "make it modern", "style_id": str(uuid.uuid4())},
    )

    assert resp.status_code == 202
    mock_queue.publish.assert_called_once()
    call_args = mock_queue.publish.call_args[0][0]
    assert isinstance(call_args, QueueMessage)
    assert call_args.body["prompt"] == "make it modern"
