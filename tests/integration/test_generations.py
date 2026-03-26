"""Integration tests for generation endpoints."""

import uuid

import httpx
import pytest

from tests.integration.conftest import (
    create_generation_via_api,
    create_project_via_api,
    create_user_via_api,
)


@pytest.mark.asyncio
async def test_list_generations_empty(client: httpx.AsyncClient):
    """GET /v1/generations/ with no generations should return empty list."""
    _, headers = await create_user_via_api(client)

    resp = await client.get("/v1/generations/", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_generations_unauthenticated(client: httpx.AsyncClient):
    """GET /v1/generations/ without auth should return 401."""
    resp = await client.get("/v1/generations/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_generation_for_project(client: httpx.AsyncClient):
    """POST /v1/projects/{id}/generations should create a generation."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers)

    resp = await client.post(
        f"/v1/projects/{project['id']}/generations",
        headers=headers,
        json={"prompt": "a modern living room", "model_used": "dalle-3", "attempt": 1},
    )
    assert resp.status_code == 202
    data = resp.json()
    assert data["prompt"] == "a modern living room"
    assert data["project_id"] == project["id"]


@pytest.mark.asyncio
async def test_create_generation_no_image(client: httpx.AsyncClient):
    """POST /v1/projects/{id}/generations without image should return 400."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers, "No Image", image_url=None)

    resp = await client.post(
        f"/v1/projects/{project['id']}/generations",
        headers=headers,
        json={"prompt": "test", "model_used": "dalle-3", "attempt": 1},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_get_generation(client: httpx.AsyncClient):
    """GET /v1/generations/{id} should return the generation."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers)
    generation = await create_generation_via_api(client, headers, project["id"])

    resp = await client.get(f"/v1/generations/{generation['id']}", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["id"] == generation["id"]


@pytest.mark.asyncio
async def test_get_generation_not_found(client: httpx.AsyncClient):
    """GET /v1/generations/{id} with unknown ID should return 404."""
    _, headers = await create_user_via_api(client)

    resp = await client.get(f"/v1/generations/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_generation_wrong_user(client: httpx.AsyncClient):
    """GET /v1/generations/{id} from another user should return 404."""
    _, headers_a = await create_user_via_api(client, "usera@test.com")
    _, headers_b = await create_user_via_api(client, "userb@test.com")

    project = await create_project_via_api(client, headers_a)
    generation = await create_generation_via_api(client, headers_a, project["id"])

    resp = await client.get(f"/v1/generations/{generation['id']}", headers=headers_b)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_generation(client: httpx.AsyncClient):
    """PATCH /v1/generations/{id} should update the generation."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers)
    generation = await create_generation_via_api(client, headers, project["id"])

    resp = await client.patch(
        f"/v1/generations/{generation['id']}", headers=headers, json={"status": "completed"}
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "completed"


@pytest.mark.asyncio
async def test_delete_generation(client: httpx.AsyncClient):
    """DELETE /v1/generations/{id} should delete the generation."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers)
    generation = await create_generation_via_api(client, headers, project["id"])

    resp = await client.delete(f"/v1/generations/{generation['id']}", headers=headers)
    assert resp.status_code == 204

    resp2 = await client.get(f"/v1/generations/{generation['id']}", headers=headers)
    assert resp2.status_code == 404


@pytest.mark.asyncio
async def test_cancel_generation(client: httpx.AsyncClient):
    """POST /v1/generations/{id}/cancel should cancel a pending generation."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers)
    generation = await create_generation_via_api(client, headers, project["id"])

    resp = await client.post(f"/v1/generations/{generation['id']}/cancel", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["status"] == "cancelled"


@pytest.mark.asyncio
async def test_cancel_already_cancelled_generation_fails(client: httpx.AsyncClient):
    """POST /v1/generations/{id}/cancel on already cancelled generation should return 400."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers)
    generation = await create_generation_via_api(client, headers, project["id"])

    await client.post(f"/v1/generations/{generation['id']}/cancel", headers=headers)

    resp = await client.post(f"/v1/generations/{generation['id']}/cancel", headers=headers)
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_retry_generation(client: httpx.AsyncClient):
    """POST /v1/generations/{id}/retry should create a new generation."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers)
    generation = await create_generation_via_api(client, headers, project["id"])

    await client.post(f"/v1/generations/{generation['id']}/cancel", headers=headers)

    resp = await client.post(f"/v1/generations/{generation['id']}/retry", headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    # Retry preserves original parent (should be None for a new generation)
    assert data["parent_id"] is None
    assert data["attempt"] == 2
