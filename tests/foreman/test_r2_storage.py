"""Tests for R2 storage."""

import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from foreman.storage.r2_storage import R2Storage
from foreman.storage.settings import R2Settings


@pytest.fixture
def configured_settings():
    """R2 settings with all required env vars."""
    return R2Settings(
        endpoint="https://example.r2.cloudflarestorage.com",
        access_key_id="test-key",
        secret_access_key="test-secret",
        bucket="test-bucket",
        public_url=None,
    )


@pytest.fixture
def unconfigured_settings():
    """R2 settings missing required env vars."""
    return R2Settings(
        endpoint=None,
        access_key_id=None,
        secret_access_key=None,
        bucket="test-bucket",
    )


def test_lazy_client_initialization(configured_settings):
    """boto3 client should be created during initialization when configured."""
    with patch("foreman.storage.r2_storage.boto3.client") as mock_client:
        mock_client.return_value = MagicMock()
        storage = R2Storage(configured_settings)

        assert storage._client is not None
        mock_client.assert_called_once()


def test_unconfigured_storage_raises_on_operation(unconfigured_settings):
    """Unconfigured storage should raise ValueError on operations."""
    storage = R2Storage(unconfigured_settings)

    with pytest.raises(ValueError, match="not configured"):
        storage._ensure_client()


@pytest.mark.asyncio
async def test_get_download_url_with_public_url(configured_settings):
    """get_download_url should use public_url when available."""
    configured_settings.public_url = "https://cdn.example.com"
    storage = R2Storage(configured_settings)
    storage._client = MagicMock()

    url = await storage.get_download_url("path/to/file.jpg")
    assert url == "https://cdn.example.com/path/to/file.jpg"
    storage._client.generate_presigned_url.assert_not_called()


@pytest.mark.asyncio
async def test_get_download_url_generates_presigned(configured_settings):
    """get_download_url should generate presigned URL when no public_url."""
    configured_settings.public_url = None
    storage = R2Storage(configured_settings)
    storage._client = MagicMock()
    storage._client.generate_presigned_url = MagicMock(return_value="https://presigned.url")

    url = await storage.get_download_url("path/to/file.jpg")
    assert url == "https://presigned.url"
    storage._client.generate_presigned_url.assert_called_once()


@pytest.mark.asyncio
async def test_delete_returns_false_on_exception(configured_settings):
    """delete should return False when boto3 raises exception."""
    storage = R2Storage(configured_settings)
    storage._client = MagicMock()
    storage._client.delete_object = MagicMock(side_effect=Exception("AWS error"))

    result = await storage.delete("some/key")
    assert result is False


@pytest.mark.asyncio
async def test_delete_returns_true_on_success(configured_settings):
    """delete should return True when boto3 succeeds."""
    storage = R2Storage(configured_settings)
    storage._client = MagicMock()
    storage._client.delete_object = MagicMock()

    with patch("foreman.storage.r2_storage.anyio.to_thread.run_sync") as mock_run_sync:
        mock_run_sync.return_value = None
        result = await storage.delete("some/key")

    assert result is True


@pytest.mark.asyncio
async def test_create_upload_url_success(configured_settings):
    """create_upload_url should return UploadIntent with presigned URL."""
    storage = R2Storage(configured_settings)
    storage._client = MagicMock()
    storage._client.generate_presigned_url = MagicMock(return_value="https://upload.url")

    intent = await storage.create_upload_url("test.jpg", "image/jpeg", uuid.uuid4())

    assert intent.upload_url == "https://upload.url"
    assert intent.file_key.startswith("projects/")
    assert intent.expires_at > datetime.now(timezone.utc)
