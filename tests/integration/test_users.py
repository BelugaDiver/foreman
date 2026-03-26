"""Integration tests for user endpoints."""

from fastapi.testclient import TestClient

from tests.integration.conftest import create_user_via_api


def test_create_user(client: TestClient):
    """POST /v1/users with valid data should return 201 and user data."""
    resp = client.post("/v1/users", json={"email": "newuser@example.com", "full_name": "New User"})
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == "newuser@example.com"
    assert data["full_name"] == "New User"
    assert "id" in data
    assert "password" not in data


def test_create_user_duplicate_email(client: TestClient):
    """POST /v1/users with duplicate email should return 400."""
    payload = {"email": "duplicate@example.com", "full_name": "First User"}
    resp1 = client.post("/v1/users", json=payload)
    assert resp1.status_code == 201

    resp2 = client.post("/v1/users", json=payload)
    assert resp2.status_code == 400


def test_create_user_missing_fields(client: TestClient):
    """POST /v1/users with missing required fields should return 422."""
    resp = client.post("/v1/users", json={"email": "test@example.com"})
    assert resp.status_code == 422


def test_get_current_user(client: TestClient):
    """GET /v1/users/me should return the authenticated user."""
    # Create user and get auth headers
    user, headers = create_user_via_api(client, "meuser@example.com")

    resp = client.get("/v1/users/me", headers=headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == user["id"]
    assert data["email"] == "meuser@example.com"


def test_get_current_user_unauthenticated(client: TestClient):
    """GET /v1/users/me without auth header should return 401."""
    resp = client.get("/v1/users/me")
    assert resp.status_code == 401


def test_update_current_user(client: TestClient):
    """PATCH /v1/users/me should update the user."""
    _, headers = create_user_via_api(client, "update@example.com")

    resp = client.patch("/v1/users/me", headers=headers, json={"full_name": "Updated Name"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["full_name"] == "Updated Name"


def test_delete_current_user(client: TestClient):
    """DELETE /v1/users/me should soft-delete the user."""
    _, headers = create_user_via_api(client, "delete@example.com")

    resp = client.delete("/v1/users/me", headers=headers)
    assert resp.status_code == 204

    # Verify user is deleted (can't authenticate)
    resp2 = client.get("/v1/users/me", headers=headers)
    assert resp2.status_code == 401
