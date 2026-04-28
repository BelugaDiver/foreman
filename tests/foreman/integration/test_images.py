"""Integration tests for image endpoints."""

import uuid

import httpx
import pytest

from tests.foreman.integration.conftest import (
    create_image_direct,
    create_project_via_api,
    create_user_via_api,
    get_db_dsn,
)


@pytest.mark.asyncio
async def test_list_images_empty(client: httpx.AsyncClient):
    """GET /v1/projects/{id}/images with no images should return empty list."""
    _, headers = await create_user_via_api(client)
    project = await create_project_via_api(client, headers)

    resp = await client.get(f"/v1/projects/{project['id']}/images", headers=headers)
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.asyncio
async def test_list_images_unauthenticated(client: httpx.AsyncClient):
    """GET /v1/projects/{id}/images without auth should return 401."""
    resp = await client.get(f"/v1/projects/{uuid.uuid4()}/images")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_images_not_found_project(client: httpx.AsyncClient):
    """GET /v1/projects/{id}/images with unknown project should return 404."""
    _, headers = await create_user_via_api(client)

    resp = await client.get(f"/v1/projects/{uuid.uuid4()}/images", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_image_not_found(client: httpx.AsyncClient):
    """GET /v1/images/{id} with unknown ID should return 404."""
    _, headers = await create_user_via_api(client)

    resp = await client.get(f"/v1/images/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_get_image_wrong_user(client: httpx.AsyncClient):
    """GET /v1/images/{id} from another user should return 404."""
    _, headers_a = await create_user_via_api(client, "usera@test.com")
    _, headers_b = await create_user_via_api(client, "userb@test.com")

    project = await create_project_via_api(client, headers_a)

    image = await create_image_direct(
        get_db_dsn(),
        uuid.UUID(project["id"]),
        uuid.UUID(headers_a["X-User-ID"]),
    )

    resp = await client.get(f"/v1/images/{image['id']}", headers=headers_b)
    assert resp.status_code == 404
