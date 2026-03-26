"""Integration tests for style endpoints."""

import uuid

import pytest
from fastapi.testclient import TestClient

from tests.integration.conftest import create_user_via_api


def test_list_styles_unauthenticated(client: TestClient):
    """GET /v1/styles/ without auth should return 401."""
    resp = client.get("/v1/styles/")
    assert resp.status_code == 401


def test_list_styles_empty(client: TestClient):
    """GET /v1/styles/ should return list of styles."""
    _, headers = create_user_via_api(client)

    resp = client.get("/v1/styles/", headers=headers)
    assert resp.status_code == 200
    # Styles table may be empty if not seeded


def test_get_style_not_found(client: TestClient):
    """GET /v1/styles/{id} with unknown ID should return 404."""
    _, headers = create_user_via_api(client)

    resp = client.get(f"/v1/styles/{uuid.uuid4()}", headers=headers)
    assert resp.status_code == 404
