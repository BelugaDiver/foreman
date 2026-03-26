"""Tests for style catalog endpoints."""

# ---------------------------------------------------------------------------
# Stdlib
# ---------------------------------------------------------------------------
import uuid
from datetime import datetime, timezone

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
from foreman.main import app
from foreman.models.style import Style
from foreman.models.user import User

# ---------------------------------------------------------------------------
# In-memory stores
# ---------------------------------------------------------------------------
users_db: dict[uuid.UUID, User] = {}
styles_db: dict[uuid.UUID, Style] = {}

USER_A_ID = uuid.uuid4()
USER_B_ID = uuid.uuid4()

STYLE_MODERN_ID = uuid.uuid4()
STYLE_MINIMAL_ID = uuid.uuid4()


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

    styles_db[STYLE_MODERN_ID] = Style(
        id=STYLE_MODERN_ID,
        name="Modern",
        description="Clean lines and contemporary aesthetics",
        example_image_url="https://example.com/styles/modern.jpg",
        created_at=now,
        updated_at=None,
    )
    styles_db[STYLE_MINIMAL_ID] = Style(
        id=STYLE_MINIMAL_ID,
        name="Minimalist",
        description="Less is more",
        example_image_url="https://example.com/styles/minimal.jpg",
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

    async def mock_list_styles(db, limit=20, offset=0):
        results = list(styles_db.values())
        return results[offset : offset + limit]

    async def mock_get_style_by_id(db, style_id):
        return styles_db.get(style_id)

    monkeypatch.setattr("foreman.api.v1.endpoints.styles.crud.list_styles", mock_list_styles)
    monkeypatch.setattr(
        "foreman.api.v1.endpoints.styles.crud.get_style_by_id", mock_get_style_by_id
    )

    yield

    users_db.clear()
    styles_db.clear()
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


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_list_styles_empty(client, headers_a):
    """GET /v1/styles with no styles should return an empty list."""
    styles_db.clear()

    resp = client.get("/v1/styles", headers=headers_a)

    assert resp.status_code == 200
    assert resp.json() == []


def test_list_styles_after_seeding(client, headers_a):
    """GET /v1/styles should return all seeded styles."""
    resp = client.get("/v1/styles", headers=headers_a)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    assert any(s["name"] == "Modern" for s in data)
    assert any(s["name"] == "Minimalist" for s in data)


def test_list_styles_pagination(client, headers_a):
    """GET /v1/styles with limit and offset should paginate correctly."""
    resp = client.get("/v1/styles?limit=1&offset=0", headers=headers_a)

    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1


def test_get_style(client, headers_a):
    """GET /v1/styles/{id} should return the matching style."""
    resp = client.get(f"/v1/styles/{STYLE_MODERN_ID}", headers=headers_a)

    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Modern"
    assert data["description"] == "Clean lines and contemporary aesthetics"


def test_get_style_not_found(client, headers_a):
    """GET /v1/styles/{id} with an unknown ID should return 404."""
    resp = client.get(f"/v1/styles/{uuid.uuid4()}", headers=headers_a)

    assert resp.status_code == 404


def test_unauthenticated_list(client):
    """GET /v1/styles without auth header should return 401."""
    resp = client.get("/v1/styles")

    assert resp.status_code == 401


def test_unauthenticated_get(client):
    """GET /v1/styles/{id} without auth header should return 401."""
    resp = client.get(f"/v1/styles/{STYLE_MODERN_ID}")

    assert resp.status_code == 401
