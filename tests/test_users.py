"""Tests for user management endpoints."""
import pytest
from httpx import AsyncClient

pytestmark = pytest.mark.asyncio

async def test_create_user(client: AsyncClient):
    response = await client.post("/api/v1/users/", json={
        "email": "test_create@example.com",
        "full_name": "Test Create User"
    })
    assert response.status_code == 201
    data = response.json()
    assert data["email"] == "test_create@example.com"
    assert "id" in data
    
    # Try duplicate email
    response_dup = await client.post("/api/v1/users/", json={
        "email": "test_create@example.com",
        "full_name": "Another User"
    })
    assert response_dup.status_code == 400


async def test_get_user_me(client: AsyncClient):
    # First create a user
    resp_create = await client.post("/api/v1/users/", json={
        "email": "test_me@example.com",
        "full_name": "Me User"
    })
    user_id = resp_create.json()["id"]

    # Now get it using the X-User-ID header
    resp_get = await client.get("/api/v1/users/me", headers={"X-User-ID": user_id})
    assert resp_get.status_code == 200
    assert resp_get.json()["email"] == "test_me@example.com"


async def test_update_user_me(client: AsyncClient):
    # Create user
    resp_create = await client.post("/api/v1/users/", json={
        "email": "test_update@example.com",
        "full_name": "Update User"
    })
    user_id = resp_create.json()["id"]

    # Update
    resp_patch = await client.patch("/api/v1/users/me", headers={"X-User-ID": user_id}, json={
        "full_name": "Updated Name"
    })
    assert resp_patch.status_code == 200
    assert resp_patch.json()["full_name"] == "Updated Name"


async def test_delete_user_me(client: AsyncClient):
    # Create user
    resp_create = await client.post("/api/v1/users/", json={
        "email": "test_delete@example.com",
        "full_name": "Delete User"
    })
    user_id = resp_create.json()["id"]

    # Delete
    resp_delete = await client.delete("/api/v1/users/me", headers={"X-User-ID": user_id})
    assert resp_delete.status_code == 204

    # Try getting it again, should be 401 because it's deleted
    resp_get = await client.get("/api/v1/users/me", headers={"X-User-ID": user_id})
    assert resp_get.status_code == 401
