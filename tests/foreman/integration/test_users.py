"""Integration tests for user endpoints."""

import httpx
import pytest

from tests.foreman.integration.conftest import create_user_via_api


@pytest.mark.asyncio
async def test_create_user(client: httpx.AsyncClient):
    """POST /v1/users with valid data should return 201 and user data."""
    resp = await client.post(
        "/v1/users", json={"email": "newuser@example.com", "full_name": "New User"}
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@example.com"
    assert data["full_name"] == "New User"
    assert "id" in data
    assert "password" not in data


@pytest.mark.asyncio
async def test_create_user_duplicate_email(client: httpx.AsyncClient):
    """POST /v1/users with duplicate email should return 409."""
    payload = {"email": "duplicate@example.com", "full_name": "First User"}
    resp1 = await client.post("/v1/users", json=payload)
    assert resp1.status_code == 201

    resp2 = await client.post("/v1/users", json=payload)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_create_user_missing_fields(client: httpx.AsyncClient):
    """POST /v1/users with missing required fields should return 422."""
    resp = await client.post("/v1/users", json={"email": "test@example.com"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_current_user(client: httpx.AsyncClient):
    """GET /v1/users/me should return the authenticated user."""
    user, headers = await create_user_via_api(client, "meuser@example.com")

    resp = await client.get("/v1/users/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == user["id"]
    assert data["email"] == "meuser@example.com"


@pytest.mark.asyncio
async def test_get_current_user_unauthenticated(client: httpx.AsyncClient):
    """GET /v1/users/me without auth header should return 401."""
    resp = await client.get("/v1/users/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_update_current_user(client: httpx.AsyncClient):
    """PATCH /v1/users/me should update the user."""
    _, headers = await create_user_via_api(client, "update@example.com")

    resp = await client.patch("/v1/users/me", headers=headers, json={"full_name": "Updated Name"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["full_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_delete_current_user(client: httpx.AsyncClient):
    """DELETE /v1/users/me should soft-delete the user."""
    _, headers = await create_user_via_api(client, "delete@example.com")

    resp = await client.delete("/v1/users/me", headers=headers)
    assert resp.status_code == 204

    resp2 = await client.get("/v1/users/me", headers=headers)
    assert resp2.status_code == 401
