"""Integration tests for generation endpoints."""

import uuid

from fastapi.testclient import TestClient

from tests.integration.conftest import (
    create_generation_via_api,
    create_project_via_api,
    create_user_via_api,
)


def test_list_generations_empty(client: TestClient):
    """GET /v1/generations/ with no generations should return empty list."""
    _, headers = create_user_via_api(client)

    resp = client.get("/v1/generations/", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_generations_unauthenticated(client: TestClient):
    """GET /v1/generations/ without auth should return 401."""
    resp = client.get("/v1/generations/")
    assert resp.status_code == 401


def test_create_generation_for_project(client: TestClient):
    """POST /v1/projects/{id}/generations should create a generation."""
    _, headers = create_user_via_api(client)
    project = create_project_via_api(client, headers)

    resp = client.post(
        f"/v1/projects/{project['id']}/generations",
        headers=headers,
        json={"prompt": "a modern living room", "model_used": "dalle-3", "attempt": 1},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["prompt"] == "a modern living room"
    assert data["project_id"] == project["id"]


def test_create_generation_no_image(client: TestClient):
    """POST /v1/projects/{id}/generations without image should return 400."""
    _, headers = create_user_via_api(client)
    project = create_project_via_api(client, headers, "No Image", image_url=None)

    resp = client.post(
        f"/v1/projects/{project['id']}/generations",
        headers=headers,
        json={"prompt": "test", "model_used": "dalle-3", "attempt": 1},
    )
    assert resp.status_code == 400


def test_get_generation(client: TestClient):
    """GET /v1/generations/{id} should return the generation."""
    _, headers = create_user_via_api(client)
    project = create_project_via_api(client, headers)
    generation = create_generation_via_api(client, headers, project["id"])

    resp = client.get(f"/v1/generations/{generation['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == generation["id"]


def test_get_generation_not_found(client: TestClient):
    """GET /v1/generations/{id} with unknown ID should return 404."""
    _, headers = create_user_via_api(client)

    resp = client.get(f"/v1/generations/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


def test_get_generation_wrong_user(client: TestClient):
    """GET /v1/generations/{id} from another user should return 404."""
    _, headers_a = create_user_via_api(client, "usera@test.com")
    _, headers_b = create_user_via_api(client, "userb@test.com")

    project = create_project_via_api(client, headers_a)
    generation = create_generation_via_api(client, headers_a, project["id"])

    resp = client.get(f"/v1/generations/{generation['id']}", headers=headers_b)
    assert resp.status_code == 404


def test_update_generation(client: TestClient):
    """PATCH /v1/generations/{id} should update the generation."""
    _, headers = create_user_via_api(client)
    project = create_project_via_api(client, headers)
    generation = create_generation_via_api(client, headers, project["id"])

    resp = client.patch(
        f"/v1/generations/{generation['id']}", headers=headers, json={"status": "completed"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


def test_delete_generation(client: TestClient):
    """DELETE /v1/generations/{id} should delete the generation."""
    _, headers = create_user_via_api(client)
    project = create_project_via_api(client, headers)
    generation = create_generation_via_api(client, headers, project["id"])

    resp = client.delete(f"/v1/generations/{generation['id']}", headers=headers)
    assert resp.status_code == 204

    # Verify deleted
    resp2 = client.get(f"/v1/generations/{generation['id']}", headers=headers)
    assert resp2.status_code == 404


def test_cancel_generation(client: TestClient):
    """POST /v1/generations/{id}/cancel should cancel a pending generation."""
    _, headers = create_user_via_api(client)
    project = create_project_via_api(client, headers)
    generation = create_generation_via_api(client, headers, project["id"])

    resp = client.post(f"/v1/generations/{generation['id']}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


def test_cancel_already_cancelled_generation_fails(client: TestClient):
    """POST /v1/generations/{id}/cancel on already cancelled generation should return 400."""
    _, headers = create_user_via_api(client)
    project = create_project_via_api(client, headers)
    generation = create_generation_via_api(client, headers, project["id"])

    # First cancel it
    client.post(f"/v1/generations/{generation['id']}/cancel", headers=headers)

    # Now try to cancel again (it's already cancelled)
    resp = client.post(f"/v1/generations/{generation['id']}/cancel", headers=headers)
    assert resp.status_code == 400


def test_retry_generation(client: TestClient):
    """POST /v1/generations/{id}/retry should create a new generation."""
    _, headers = create_user_via_api(client)
    project = create_project_via_api(client, headers)
    generation = create_generation_via_api(client, headers, project["id"])

    # Cancel first
    client.post(f"/v1/generations/{generation['id']}/cancel", headers=headers)

    # Retry
    resp = client.post(f"/v1/generations/{generation['id']}/retry", headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["parent_id"] == generation["id"]
    assert data["attempt"] == 2
