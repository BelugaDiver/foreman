"""Integration tests for project endpoints."""

import uuid

import httpx
import pytest

from tests.foreman.integration.conftest import (
    create_generation_via_api,
    create_project_via_api,
    create_user_via_api,
)


@pytest.mark.asyncio
async def test_list_projects_empty(client: httpx.AsyncClient):
    """GET /v1/projects/ with no projects should return empty list."""
    _, headers = await create_user_via_api(client)

    resp = await client.get("/v1/projects/", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_projects_unauthenticated(client: httpx.AsyncClient):
    """GET /v1/projects/ without auth should return 401."""
    resp = await client.get("/v1/projects/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_project(client: httpx.AsyncClient):
    """POST /v1/projects/ should create a new project."""
    _, headers = await create_user_via_api(client)

    resp = await client.post(
        "/v1/projects/",
        headers=headers,
        json={"name": "My Project", "original_image_url": "https://example.com/image.jpg"},
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["name"] == "My Project"
    assert data["original_image_url"] == "https://example.com/image.jpg"


@pytest.mark.asyncio
async def test_create_project_minimal(client: httpx.AsyncClient):
    """POST /v1/projects/ with only name should work."""
    _, headers = await create_user_via_api(client)

    resp = await client.post("/v1/projects/", headers=headers, json={"name": "Minimal Project"})
    assert resp.status_code == 201
    assert resp.json()["original_image_url"] is None


@pytest.mark.asyncio
async def test_create_project_missing_name(client: httpx.AsyncClient):
    """POST /v1/projects/ without name should return 422."""
    _, headers = await create_user_via_api(client)

    resp = await client.post("/v1/projects/", headers=headers, json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_get_project(client: httpx.AsyncClient):
    """GET /v1/projects/{id} should return the project."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers, "Get Test")

    resp = await client.get(f"/v1/projects/{project['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Get Test"


@pytest.mark.asyncio
async def test_get_project_not_found(client: httpx.AsyncClient):
    """GET /v1/projects/{id} with unknown ID should return 404."""
    _, headers = await create_user_via_api(client)

    resp = await client.get(f"/v1/projects/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_project_wrong_user(client: httpx.AsyncClient):
    """GET /v1/projects/{id} from another user should return 404."""
    _, headers_a = await create_user_via_api(client, "usera@test.com")
    _, headers_b = await create_user_via_api(client, "userb@test.com")

    project = await create_project_via_api(client, headers_a, "A's Project")

    resp = await client.get(f"/v1/projects/{project['id']}", headers=headers_b)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_project(client: httpx.AsyncClient):
    """PATCH /v1/projects/{id} should update the project."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers, "Original Name")

    resp = await client.patch(
        f"/v1/projects/{project['id']}",
        headers=headers,
        json={"name": "Updated Name", "room_analysis": {"style": "modern"}},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "Updated Name"
    assert data["room_analysis"] == {"style": "modern"}


@pytest.mark.asyncio
async def test_update_project_partial(client: httpx.AsyncClient):
    """PATCH /v1/projects/{id} with partial data should preserve other fields."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers, "Name", "https://example.com/image.jpg")

    resp = await client.patch(
        f"/v1/projects/{project['id']}", headers=headers, json={"name": "New Name"}
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["name"] == "New Name"
    assert data["original_image_url"] == "https://example.com/image.jpg"


@pytest.mark.asyncio
async def test_update_project_not_found(client: httpx.AsyncClient):
    """PATCH /v1/projects/{id} with unknown ID should return 404."""
    _, headers = await create_user_via_api(client)

    resp = await client.patch(f"/v1/projects/{uuid.uuid4()}", headers=headers, json={"name": "X"})
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_delete_project(client: httpx.AsyncClient):
    """DELETE /v1/projects/{id} should delete the project."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers, "To Delete")

    resp = await client.delete(f"/v1/projects/{project['id']}", headers=headers)
    assert resp.status_code == 204

    resp2 = await client.get(f"/v1/projects/{project['id']}", headers=headers)
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_delete_project_not_found(client: httpx.AsyncClient):
    """DELETE /v1/projects/{id} with unknown ID should return 404."""
    _, headers = await create_user_via_api(client)

    resp = await client.delete(f"/v1/projects/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_list_project_generations(client: httpx.AsyncClient):
    """GET /v1/projects/{id}/generations should list generations."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers)

    await create_generation_via_api(client, headers, project["id"])

    resp = await client.get(f"/v1/projects/{project['id']}/generations", headers=headers)
    assert resp.status_code == 200
    assert len(resp.json()) == 1
