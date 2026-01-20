"""Tests for the Foreman FastAPI application."""
import pytest
from fastapi.testclient import TestClient
from foreman.main import create_app
from foreman.dependencies import get_container


@pytest.fixture
def client():
    """Create a test client."""
    app = create_app()
    return TestClient(app)


def test_root_endpoint(client):
    """Test the root endpoint."""
    response = client.get("/")
    assert response.status_code == 200
    data = response.json()
    assert data["service"] == "Foreman"
    assert "description" in data


def test_health_check(client):
    """Test the health check endpoint."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "healthy"


def test_api_status_endpoint(client):
    """Test the API status endpoint with dependency injection."""
    response = client.get("/api/status")
    assert response.status_code == 200
    data = response.json()
    assert "service" in data
    assert "status" in data
    assert data["status"] == "ready"


def test_dependency_container():
    """Test the dependency container."""
    container = get_container()
    assert container is not None
    
    # Test that we can register and resolve dependencies
    from foreman.services import ImageService
    service = container.resolve(ImageService)
    assert service is not None
    
    status = service.get_status()
    assert status["status"] == "ready"
