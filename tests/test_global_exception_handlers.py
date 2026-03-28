"""Tests for global exception handlers."""

import pytest
from unittest.mock import patch, MagicMock
from starlette.requests import Request
from starlette.responses import JSONResponse


class TestGlobalExceptionHandlers:
    """Test global exception handlers return correct status codes."""

    def test_storage_transient_error_returns_503(self):
        """S3 transient error should return 503."""
        from foreman.main import storage_error_handler
        from botocore.exceptions import ClientError
        from starlette.datastructures import URL

        request = MagicMock(spec=Request)
        request.url = URL("https://s3.example.com/bucket/key")
        request.method = "GET"

        exc = ClientError({"Error": {"Code": "SlowDown"}}, "PutObject")

        import asyncio

        response = asyncio.run(storage_error_handler(request, exc))

        assert response.status_code == 503

    def test_storage_non_transient_error_returns_500(self):
        """S3 non-transient error should return 500."""
        from foreman.main import storage_error_handler
        from botocore.exceptions import ClientError
        from starlette.datastructures import URL

        request = MagicMock(spec=Request)
        request.url = URL("https://s3.example.com/bucket/key")
        request.method = "GET"

        exc = ClientError({"Error": {"Code": "AccessDenied"}}, "PutObject")

        import asyncio

        response = asyncio.run(storage_error_handler(request, exc))

        assert response.status_code == 500

    def test_connection_failure_returns_503(self):
        """Database connection failure should return 503."""
        from foreman.main import connection_failure_handler
        from asyncpg import ConnectionFailureError
        from starlette.datastructures import URL

        request = MagicMock(spec=Request)
        request.url = URL("http://testserver/v1/users")

        exc = ConnectionFailureError("connection failed")

        import asyncio

        response = asyncio.run(connection_failure_handler(request, exc))

        assert response.status_code == 503

    def test_timeout_returns_503(self):
        """Timeout error should return 503."""
        from foreman.main import timeout_error_handler
        from starlette.datastructures import URL

        request = MagicMock(spec=Request)
        request.url = URL("http://testserver/v1/users")

        exc = TimeoutError()

        import asyncio

        response = asyncio.run(timeout_error_handler(request, exc))

        assert response.status_code == 503

    def test_query_canceled_returns_503(self):
        """Query canceled should return 503."""
        from foreman.main import query_canceled_handler
        from asyncpg import QueryCanceledError
        from starlette.datastructures import URL

        request = MagicMock(spec=Request)
        request.url = URL("http://testserver/v1/users")

        exc = QueryCanceledError("query cancelled")

        import asyncio

        response = asyncio.run(query_canceled_handler(request, exc))

        assert response.status_code == 503
