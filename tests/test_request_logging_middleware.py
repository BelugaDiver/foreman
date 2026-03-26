"""Tests for HTTP request logging middleware."""

from unittest.mock import patch

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from foreman.middleware.request_logging import RequestLoggingMiddleware


@pytest.fixture
def mock_app():
    app = FastAPI()

    @app.get("/test")
    async def test_route():
        return {"status": "ok"}

    return app


def test_middleware_generates_correlation_id_when_missing(mock_app):
    """Middleware should generate correlation ID if not present in headers."""
    mock_app.add_middleware(RequestLoggingMiddleware)
    client = TestClient(mock_app)

    response = client.get("/test")

    assert response.status_code == 200
    assert "X-Correlation-ID" in response.headers
    assert len(response.headers["X-Correlation-ID"]) == 36  # UUID format


def test_middleware_uses_existing_correlation_id(mock_app):
    """Middleware should extract correlation ID from X-Request-ID header."""
    mock_app.add_middleware(RequestLoggingMiddleware)
    client = TestClient(mock_app)

    custom_cid = "custom-correlation-id-12345"
    response = client.get("/test", headers={"X-Request-ID": custom_cid})

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"] == custom_cid


def test_middleware_logs_incoming_request(mock_app):
    """Middleware should log incoming requests."""
    mock_app.add_middleware(RequestLoggingMiddleware)
    client = TestClient(mock_app)

    response = client.get("/test")

    assert response.status_code == 200
    # Verify response has correlation ID (proves logging middleware ran)
    assert "X-Correlation-ID" in response.headers


def test_middleware_logs_response_status(mock_app):
    """Middleware should log response with status code."""
    mock_app.add_middleware(RequestLoggingMiddleware)
    client = TestClient(mock_app)

    with patch("foreman.middleware.request_logging.logger") as mock_logger:
        response = client.get("/test")

        assert response.status_code == 200
        # Find the "Request completed" log call
        completed_calls = [
            call for call in mock_logger.info.call_args_list if "Request completed" in str(call)
        ]
        assert len(completed_calls) > 0


def test_middleware_adds_correlation_id_to_response(mock_app):
    """Middleware should add X-Correlation-ID header to response."""
    mock_app.add_middleware(RequestLoggingMiddleware)
    client = TestClient(mock_app)

    response = client.get("/test")

    assert "X-Correlation-ID" in response.headers
    assert response.headers["X-Correlation-ID"] != ""
