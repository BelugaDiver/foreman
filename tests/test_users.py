"""Tests for user management endpoints."""

import pytest
from fastapi.testclient import TestClient

from foreman.main import app


import uuid
from datetime import datetime, timezone
from fastapi import Header, HTTPException

from foreman.api.deps import get_current_user, get_db
from foreman.models.user import User
from foreman.schemas.user import UserCreate, UserUpdate

# In-memory DB for tests
users_db = {}


@pytest.fixture(autouse=True)
def mock_dependencies(monkeypatch):
    """Mock database and CRUD operations for endpoints tests."""
    
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

    # Override dependencies
    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    
    # Mock CRUD
    async def mock_create_user(db, user_in: UserCreate):
        for u in users_db.values():
            if u.email == user_in.email:
                raise Exception("unique constraint violation")
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
    monkeypatch.setattr("foreman.api.v1.endpoints.users.crud.soft_delete_user", mock_soft_delete_user)
    
    yield
    
    users_db.clear()
    app.dependency_overrides.clear()


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


def test_create_user(client):
    response = client.post("/v1/users/", json={
        "email": "test_create@example.com",
        "full_name": "Test Create User"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test_create@example.com"
    assert "id" in data
    
    # Try duplicate email
    response_dup = client.post("/v1/users/", json={
        "email": "test_create@example.com",
        "full_name": "Another User"
    })
    assert response_dup.status_code == 400


def test_get_user_me(client):
    # First create a user
    resp_create = client.post("/v1/users/", json={
        "email": "test_me@example.com",
        "full_name": "Me User"
    })
    assert resp_create.status_code == 201
    user_id = resp_create.json()["id"]

    # Now get it using the X-User-ID header
    resp_get = client.get("/v1/users/me", headers={"X-User-ID": user_id})
    assert resp_get.status_code == 200
    assert resp_get.json()["email"] == "test_me@example.com"


def test_update_user_me(client):
    # Create user
    resp_create = client.post("/v1/users/", json={
        "email": "test_update@example.com",
        "full_name": "Update User"
    })
    assert resp_create.status_code == 201
    user_id = resp_create.json()["id"]

    # Update
    resp_patch = client.patch("/v1/users/me", headers={"X-User-ID": user_id}, json={
        "full_name": "Updated Name"
    })
    assert resp_patch.status_code == 200
    assert resp_patch.json()["full_name"] == "Updated Name"


def test_delete_user_me(client):
    # Create user
    resp_create = client.post("/v1/users/", json={
        "email": "test_delete@example.com",
        "full_name": "Delete User"
    })
    assert resp_create.status_code == 201
    user_id = resp_create.json()["id"]

    # Delete
    resp_delete = client.delete("/v1/users/me", headers={"X-User-ID": user_id})
    assert resp_delete.status_code == 204

    # Try getting it again, should be 401 because it's soft-deleted
    resp_get = client.get("/v1/users/me", headers={"X-User-ID": user_id})
    assert resp_get.status_code == 401
