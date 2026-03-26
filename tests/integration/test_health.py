"""Integration tests for health endpoints."""

import os

os.environ["DEV_MODE"] = "false"

from fastapi.testclient import TestClient

from foreman.main import app


def test_root_health():
    """GET / should return health status."""
    client = TestClient(app)
    resp = client.get("/")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data


def test_health_check():
    """GET /health should return health status."""
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert "version" in data
