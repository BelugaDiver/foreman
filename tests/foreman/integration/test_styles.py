"""Integration tests for style endpoints."""

import uuid

import httpx
import pytest

from tests.foreman.integration.conftest import create_user_via_api


@pytest.mark.asyncio
async def test_list_styles_unauthenticated(client: httpx.AsyncClient):
    """GET /v1/styles/ without auth should return 401."""
    resp = await client.get("/v1/styles/")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_styles_empty(client: httpx.AsyncClient):
    """GET /v1/styles/ should return list of styles."""
    _, headers = await create_user_via_api(client)

    resp = await client.get("/v1/styles/", headers=headers)
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_get_style_not_found(client: httpx.AsyncClient):
    """GET /v1/styles/{id} with unknown ID should return 404."""
    _, headers = await create_user_via_api(client)

    resp = await client.get(f"/v1/styles/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404
