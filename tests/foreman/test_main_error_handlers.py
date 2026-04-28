"""Tests for main.py error handlers."""

from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError, EndpointConnectionError

from foreman.main import storage_error_handler


@pytest.fixture
def mock_request():
    """Create a mock request object."""
    request = MagicMock()
    request.url = MagicMock()
    request.url.__str__ = lambda self: "http://test/health"
    request.method = "GET"
    return request


@pytest.mark.asyncio
async def test_storage_error_handler_transient_slowdown(mock_request):
    """storage_error_handler should return 503 for SlowDown error."""
    error = ClientError({"Error": {"Code": "SlowDown"}}, "PutObject")

    response = await storage_error_handler(mock_request, error)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_storage_error_handler_transient_timeout(mock_request):
    """storage_error_handler should return 503 for RequestTimeout error."""
    error = ClientError({"Error": {"Code": "RequestTimeout"}}, "PutObject")

    response = await storage_error_handler(mock_request, error)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_storage_error_handler_transient_internal_error(mock_request):
    """storage_error_handler should return 503 for InternalError."""
    error = ClientError({"Error": {"Code": "InternalError"}}, "PutObject")

    response = await storage_error_handler(mock_request, error)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_storage_error_handler_transient_service_unavailable(mock_request):
    """storage_error_handler should return 503 for ServiceUnavailable."""
    error = ClientError({"Error": {"Code": "ServiceUnavailable"}}, "PutObject")

    response = await storage_error_handler(mock_request, error)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_storage_error_handler_transient_throttling(mock_request):
    """storage_error_handler should return 503 for Throttling."""
    error = ClientError({"Error": {"Code": "Throttling"}}, "PutObject")

    response = await storage_error_handler(mock_request, error)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_storage_error_handler_non_transient_access_denied(mock_request):
    """storage_error_handler should return 500 for AccessDenied."""
    error = ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")

    response = await storage_error_handler(mock_request, error)
    assert response.status_code == 500


@pytest.mark.asyncio
async def test_storage_error_handler_no_error_code(mock_request):
    """storage_error_handler should return 500 when no error code."""
    error = ClientError({}, "PutObject")

    response = await storage_error_handler(mock_request, error)
    assert response.status_code == 500


@pytest.mark.asyncio
async def test_storage_error_handler_endpoint_connection_error(mock_request):
    """storage_error_handler should handle EndpointConnectionError."""
    error = EndpointConnectionError(endpoint_url="https://example.com")

    response = await storage_error_handler(mock_request, error)
    assert response.status_code == 500
