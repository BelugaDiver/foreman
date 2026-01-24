"""Tests for the Foreman FastAPI application."""

import pytest
from fastapi.testclient import TestClient

from foreman.main import app


@pytest.fixture
def client():
    """Create a test client for the FastAPI app."""
    return TestClient(app)


def test_root_endpoint(client):
    """Test the root endpoint returns health check."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"
    assert data["service"] == "foreman"
    assert "version" in data


def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_create_request(client):
    """Test creating a new image generation request."""
    request_data = {
        "prompt": "A beautiful sunset over mountains",
        "model": "stable-diffusion-v1",
        "width": 512,
        "height": 512,
        "num_images": 1,
    }
    response = client.post("/requests", json=request_data)
    assert response.status_code == 201
    data = response.json()
    assert "id" in data
    assert data["status"] == "pending"
    assert data["message"] == "Request created successfully"


def test_list_requests(client):
    """Test listing all requests."""
    # Create a request first
    request_data = {"prompt": "Test prompt"}
    client.post("/requests", json=request_data)

    # List requests
    response = client.get("/requests")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0


def test_get_request(client):
    """Test getting a specific request."""
    # Create a request first
    request_data = {"prompt": "Test prompt for retrieval"}
    create_response = client.post("/requests", json=request_data)
    request_id = create_response.json()["id"]

    # Get the request
    response = client.get(f"/requests/{request_id}")
    assert response.status_code == 200
    data = response.json()
    assert data["id"] == request_id
    assert data["prompt"] == "Test prompt for retrieval"


def test_get_nonexistent_request(client):
    """Test getting a request that doesn't exist."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    response = client.get(f"/requests/{fake_id}")
    assert response.status_code == 404


def test_update_request_status(client):
    """Test updating request status."""
    # Create a request first
    request_data = {"prompt": "Test prompt for status update"}
    create_response = client.post("/requests", json=request_data)
    request_id = create_response.json()["id"]

    # Update status
    response = client.put(f"/requests/{request_id}/status?new_status=processing")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "processing"


def test_delete_request(client):
    """Test deleting a request."""
    # Create a request first
    request_data = {"prompt": "Test prompt for deletion"}
    create_response = client.post("/requests", json=request_data)
    request_id = create_response.json()["id"]

    # Delete the request
    response = client.delete(f"/requests/{request_id}")
    assert response.status_code == 204

    # Verify it's gone
    get_response = client.get(f"/requests/{request_id}")
    assert get_response.status_code == 404


def test_request_validation(client):
    """Test request validation with invalid data."""
    # Test with negative width
    invalid_data = {"prompt": "Test", "width": -100}
    response = client.post("/requests", json=invalid_data)
    assert response.status_code == 422

    # Test with too many images
    invalid_data = {"prompt": "Test", "num_images": 100}
    response = client.post("/requests", json=invalid_data)
    assert response.status_code == 422
