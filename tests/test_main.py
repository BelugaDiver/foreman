"""Tests for the Foreman FastAPI application."""

# ---------------------------------------------------------------------------
# Third-party
# ---------------------------------------------------------------------------
import pytest
from fastapi.testclient import TestClient

# ---------------------------------------------------------------------------
# Local
# ---------------------------------------------------------------------------
from foreman.main import app


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_root_endpoint(client):
    """GET / should return a healthy status with service metadata."""
    # Arrange — no setup required

    # Act
    response = client.get("/")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "foreman"
    assert "version" in data


def test_health_check(client):
    """GET /health should return a healthy status."""
    # Arrange — no setup required

    # Act
    response = client.get("/health")

    # Assert
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
