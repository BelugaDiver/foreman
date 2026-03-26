"""Integration tests for project endpoints."""

import uuid

from fastapi.testclient import TestClient

from tests.integration.conftest import (
    create_generation_via_api,
    create_project_via_api,
    create_user_via_api,
)


def test_list_projects_empty(client: TestClient):
    """GET /v1/projects/ with no projects should return empty list."""
    _, headers = create_user_via_api(client)

    resp = client.get("/v1/projects/", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


def test_list_projects_unauthenticated(client: TestClient):
    """GET /v1/projects/ without auth should return 401."""
    resp = client.get("/v1/projects/")
    assert resp.status_code == 401


def test_create_project(client: TestClient):
    """POST /v1/projects/ should create a new project."""
    _, headers = create_user_via_api(client)

    resp = client.post(
        "/v1/projects/",
        headers=headers,
        json={"name": "My Project", "original_image_url": "https://example.com/image.jpg"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Project"
    assert data["original_image_url"] == "https://example.com/image.jpg"


def test_create_project_minimal(client: TestClient):
    """POST /v1/projects/ with only name should work."""
    _, headers = create_user_via_api(client)

    resp = client.post("/v1/projects/", headers=headers, json={"name": "Minimal Project"})
    assert resp.status_code == 201
    assert resp.json()["original_image_url"] is None


def test_create_project_missing_name(client: TestClient):
    """POST /v1/projects/ without name should return 422."""
    _, headers = create_user_via_api(client)

    resp = client.post("/v1/projects/", headers=headers, json={})
    assert resp.status_code == 422


def test_get_project(client: TestClient):
    """GET /v1/projects/{id} should return the project."""
    _, headers = create_user_via_api(client)
    project = create_project_via_api(client, headers, "Get Test")

    resp = client.get(f"/v1/projects/{project['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Test"


def test_get_project_not_found(client: TestClient):
    """GET /v1/projects/{id} with unknown ID should return 404."""
    _, headers = create_user_via_api(client)

    resp = client.get(f"/v1/projects/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


def test_get_project_wrong_user(client: TestClient):
    """GET /v1/projects/{id} from another user should return 404."""
    _, headers_a = create_user_via_api(client, "usera@test.com")
    _, headers_b = create_user_via_api(client, "userb@test.com")

    project = create_project_via_api(client, headers_a, "A's Project")

    resp = client.get(f"/v1/projects/{project['id']}", headers=headers_b)
    assert resp.status_code == 404


def test_update_project(client: TestClient):
    """PATCH /v1/projects/{id} should update the project."""
    _, headers = create_user_via_api(client)
    project = create_project_via_api(client, headers, "Original Name")

    resp = client.patch(
        f"/v1/projects/{project['id']}",
        headers=headers,
        json={"name": "Updated Name", "room_analysis": {"style": "modern"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated Name"
    assert data["room_analysis"] == {"style": "modern"}


def test_update_project_partial(client: TestClient):
    """PATCH /v1/projects/{id} with partial data should preserve other fields."""
    _, headers = create_user_via_api(client)
    project = create_project_via_api(client, headers, "Name", "https://example.com/image.jpg")

    resp = client.patch(f"/v1/projects/{project['id']}", headers=headers, json={"name": "New Name"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["original_image_url"] == "https://example.com/image.jpg"


def test_update_project_not_found(client: TestClient):
    """PATCH /v1/projects/{id} with unknown ID should return 404."""
    _, headers = create_user_via_api(client)

    resp = client.patch(f"/v1/projects/{uuid.uuid4()}", headers=headers, json={"name": "X"})
    assert resp.status_code == 404


def test_delete_project(client: TestClient):
    """DELETE /v1/projects/{id} should delete the project."""
    _, headers = create_user_via_api(client)
    project = create_project_via_api(client, headers, "To Delete")

    resp = client.delete(f"/v1/projects/{project['id']}", headers=headers)
    assert resp.status_code == 204

    # Verify deleted
    resp2 = client.get(f"/v1/projects/{project['id']}", headers=headers)
    assert resp2.status_code == 404


def test_delete_project_not_found(client: TestClient):
    """DELETE /v1/projects/{id} with unknown ID should return 404."""
    _, headers = create_user_via_api(client)

    resp = client.delete(f"/v1/projects/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


def test_list_project_generations(client: TestClient):
    """GET /v1/projects/{id}/generations should list generations."""
    _, headers = create_user_via_api(client)
    project = create_project_via_api(client, headers)

    # Create a generation
    create_generation_via_api(client, headers, project["id"])

    resp = client.get(f"/v1/projects/{project['id']}/generations", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
