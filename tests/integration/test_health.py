"""Integration tests for health endpoints."""

import httpx
import pytest


@pytest.mark.asyncio
async def test_root_health(client: httpx.AsyncClient):
    """GET / should return health status."""
    resp = await client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data


@pytest.mark.asyncio
async def test_health_check(client: httpx.AsyncClient):
    """GET /health should return health status."""
    resp = await client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
