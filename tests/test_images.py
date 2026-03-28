"""Tests for image management endpoints."""

# ---------------------------------------------------------------------------
# Stdlib
# ---------------------------------------------------------------------------
import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

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
from foreman.models.image import Image
from foreman.models.project import Project
from foreman.models.user import User
from foreman.schemas.image import ImageCreate

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
users_db: dict[uuid.UUID, User] = {}
projects_db: dict[uuid.UUID, Project] = {}
images_db: dict[uuid.UUID, Image] = {}

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

    from foreman.exceptions import ResourceNotFoundError

    async def mock_get_project_by_id(db, project_id, user_id):
        project = projects_db.get(project_id)
        if not project or project.user_id != user_id:
            raise ResourceNotFoundError("Project", str(project_id))
        return project

    async def mock_create_project(db, user_id, project_in):
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

    async def mock_list_images(db, project_id, user_id, limit=20, offset=0):
        results = [
            i for i in images_db.values() if i.project_id == project_id and i.user_id == user_id
        ]
        return results[offset : offset + limit]

    async def mock_get_image_by_id(db, image_id, user_id):
        image = images_db.get(image_id)
        if not image or image.user_id != user_id:
            raise ResourceNotFoundError("Image", str(image_id))
        return image

    async def mock_create_image(db, image_in: ImageCreate, url=None):
        image = Image(
            id=uuid.uuid4(),
            project_id=image_in.project_id,
            user_id=image_in.user_id,
            filename=image_in.filename,
            content_type=image_in.content_type,
            size_bytes=image_in.size_bytes,
            storage_key=image_in.storage_key,
            url=url,
            created_at=datetime.now(timezone.utc),
            updated_at=None,
        )
        images_db[image.id] = image
        return image

    async def mock_delete_image(db, image_id, user_id):
        image = images_db.get(image_id)
        if not image or image.user_id != user_id:
            return False
        del images_db[image_id]
        return True

    mock_storage = AsyncMock()
    mock_storage.create_upload_url = AsyncMock(
        return_value=MagicMock(
            upload_url="https://example.com/upload",
            file_key="test/key",
            expires_at=datetime.now(timezone.utc),
        )
    )
    mock_storage.get_download_url = AsyncMock(return_value="https://example.com/download")
    mock_storage.delete = AsyncMock(return_value=True)

    def mock_get_storage():
        return mock_storage

    monkeypatch.setattr(
        "foreman.api.v1.endpoints.projects.crud.get_project_by_id", mock_get_project_by_id
    )
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.projects.crud.create_project", mock_create_project
    )
    monkeypatch.setattr("foreman.api.v1.endpoints.images.crud.list_images", mock_list_images)
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.images.crud.get_image_by_id", mock_get_image_by_id
    )
    monkeypatch.setattr("foreman.api.v1.endpoints.images.crud.create_image", mock_create_image)
    monkeypatch.setattr("foreman.api.v1.endpoints.images.crud.delete_image", mock_delete_image)
    monkeypatch.setattr("foreman.api.v1.endpoints.images.get_storage_sync", mock_get_storage)

    yield

    users_db.clear()
    projects_db.clear()
    images_db.clear()
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


@pytest.fixture
def project_a(client, headers_a):
    """Create a project for User A."""
    body = {"name": "Test Project"}
    resp = client.post("/v1/projects/", headers=headers_a, json=body)
    assert resp.status_code == 201
    return resp.json()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_images_empty(client, headers_a, project_a):
    """GET /v1/projects/{id}/images with no images should return an empty list."""
    project_id = project_a["id"]

    resp = client.get(f"/v1/projects/{project_id}/images", headers=headers_a)

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_images_after_create(client, headers_a, project_a):
    """GET /v1/projects/{id}/images should reflect all images created for the project."""
    project_id = project_a["id"]

    resp = client.post(
        f"/v1/projects/{project_id}/images",
        headers=headers_a,
        json={
            "filename": "test.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 1024,
        },
    )
    assert resp.status_code == 201

    resp = client.get(f"/v1/projects/{project_id}/images", headers=headers_a)

    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_list_images_only_own(client, headers_a, headers_b, project_a):
    """User A's list should not include User B's images."""
    project_id = project_a["id"]

    images_db[uuid.uuid4()] = Image(
        id=uuid.uuid4(),
        project_id=project_id,
        user_id=USER_B_ID,
        filename="b_image.jpg",
        content_type="image/jpeg",
        size_bytes=1024,
        storage_key="b/key",
        url=None,
        created_at=datetime.now(timezone.utc),
        updated_at=None,
    )

    resp = client.get(f"/v1/projects/{project_id}/images", headers=headers_a)

    assert resp.status_code == 200
    assert len(resp.json()) == 0


def test_create_upload_intent(client, headers_a, project_a):
    """POST /v1/projects/{id}/images should return presigned upload URL."""
    project_id = project_a["id"]

    resp = client.post(
        f"/v1/projects/{project_id}/images",
        headers=headers_a,
        json={
            "filename": "room.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 500000,
        },
    )

    assert resp.status_code == 201
    data = resp.json()
    assert "upload_url" in data
    assert "image_id" in data
    assert "file_key" in data


def test_create_upload_intent_project_not_found(client, headers_a):
    """POST /v1/projects/{id}/images with unknown project should return 404."""
    resp = client.post(
        f"/v1/projects/{uuid.uuid4()}/images",
        headers=headers_a,
        json={
            "filename": "room.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 500000,
        },
    )

    assert resp.status_code == 404


def test_get_image(client, headers_a, project_a):
    """GET /v1/images/{id} should return the matching image with download URL."""
    project_id = project_a["id"]

    create_resp = client.post(
        f"/v1/projects/{project_id}/images",
        headers=headers_a,
        json={
            "filename": "room.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 1024,
        },
    )
    image_id = create_resp.json()["image_id"]

    resp = client.get(f"/v1/images/{image_id}", headers=headers_a)

    assert resp.status_code == 200
    data = resp.json()
    assert data["filename"] == "room.jpg"
    assert data["url"] is not None


def test_get_image_not_found(client, headers_a):
    """GET /v1/images/{id} with an unknown ID should return 404."""
    resp = client.get(f"/v1/images/{uuid.uuid4()}", headers=headers_a)

    assert resp.status_code == 404


def test_delete_image(client, headers_a, project_a):
    """DELETE /v1/images/{id} should return 204; subsequent GET should return 404."""
    project_id = project_a["id"]

    create_resp = client.post(
        f"/v1/projects/{project_id}/images",
        headers=headers_a,
        json={
            "filename": "room.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 1024,
        },
    )
    image_id = create_resp.json()["image_id"]

    del_resp = client.delete(f"/v1/images/{image_id}", headers=headers_a)

    assert del_resp.status_code == 204

    get_resp = client.get(f"/v1/images/{image_id}", headers=headers_a)
    assert get_resp.status_code == 404


def test_delete_image_not_found(client, headers_a):
    """DELETE /v1/images/{id} with an unknown ID should return 404."""
    resp = client.delete(f"/v1/images/{uuid.uuid4()}", headers=headers_a)

    assert resp.status_code == 404


def test_image_ownership_get(client, headers_a, headers_b, project_a):
    """User B cannot read User A's image."""
    project_id = project_a["id"]

    create_resp = client.post(
        f"/v1/projects/{project_id}/images",
        headers=headers_a,
        json={
            "filename": "private.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 1024,
        },
    )
    image_id = create_resp.json()["image_id"]

    resp = client.get(f"/v1/images/{image_id}", headers=headers_b)

    assert resp.status_code == 404


def test_image_ownership_delete(client, headers_a, headers_b, project_a):
    """User B cannot delete User A's image."""
    project_id = project_a["id"]

    create_resp = client.post(
        f"/v1/projects/{project_id}/images",
        headers=headers_a,
        json={
            "filename": "private.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 1024,
        },
    )
    image_id = create_resp.json()["image_id"]

    resp = client.delete(f"/v1/images/{image_id}", headers=headers_b)

    assert resp.status_code == 404


def test_unauthenticated_list(client, project_a):
    """GET /v1/projects/{id}/images without auth header should return 401."""
    project_id = project_a["id"]

    resp = client.get(f"/v1/projects/{project_id}/images")

    assert resp.status_code == 401


def test_unauthenticated_create(client, project_a):
    """POST /v1/projects/{id}/images without auth header should return 401."""
    project_id = project_a["id"]

    resp = client.post(
        f"/v1/projects/{project_id}/images",
        json={
            "filename": "room.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 1024,
        },
    )

    assert resp.status_code == 401


def test_create_upload_intent_invalid_content_type(client, headers_a, project_a):
    """POST /v1/projects/{id}/images with invalid content_type should return 422."""
    project_id = project_a["id"]

    resp = client.post(
        f"/v1/projects/{project_id}/images",
        headers=headers_a,
        json={
            "filename": "room.jpg",
            "content_type": "application/json",
            "size_bytes": 1024,
        },
    )

    assert resp.status_code == 422


def test_create_upload_intent_invalid_size(client, headers_a, project_a):
    """POST /v1/projects/{id}/images with size_bytes <= 0 should return 422."""
    project_id = project_a["id"]

    resp = client.post(
        f"/v1/projects/{project_id}/images",
        headers=headers_a,
        json={
            "filename": "room.jpg",
            "content_type": "image/jpeg",
            "size_bytes": 0,
        },
    )

    assert resp.status_code == 422
