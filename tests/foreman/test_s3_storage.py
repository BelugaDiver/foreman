"""Tests for S3 storage."""

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from foreman.storage.s3_storage import S3Storage
from foreman.storage.settings import S3Settings


@pytest.fixture
def configured_settings_with_creds():
    """S3 settings with explicit credentials."""
    return S3Settings(
        bucket="test-bucket",
        region="us-east-1",
        access_key_id="test-key",
        secret_access_key="test-secret",
        public_url=None,
    )


@pytest.fixture
def configured_settings_iam_role():
    """S3 settings for IAM role delegation (no explicit credentials)."""
    return S3Settings(
        bucket="test-bucket",
        region="us-east-1",
        access_key_id=None,
        secret_access_key=None,
        public_url=None,
    )


@pytest.fixture
def unconfigured_settings():
    """S3 settings with incomplete credentials."""
    return S3Settings(
        bucket="test-bucket",
        region="us-east-1",
        access_key_id="test-key",
        secret_access_key=None,  # Missing one credential
        public_url=None,
    )


def test_initialization_with_explicit_creds(configured_settings_with_creds):
    """S3Storage should initialize boto3 client with explicit credentials."""
    with patch("foreman.storage.s3_storage.boto3.client") as mock_client:
        mock_client.return_value = MagicMock()
        storage = S3Storage(configured_settings_with_creds)

        assert storage._client is not None
        mock_client.assert_called_once()
        call_kwargs = mock_client.call_args[1]
        assert call_kwargs["region_name"] == "us-east-1"
        assert call_kwargs["aws_access_key_id"] == "test-key"
        assert call_kwargs["aws_secret_access_key"] == "test-secret"


def test_initialization_with_iam_role(configured_settings_iam_role):
    """S3Storage should initialize boto3 client without explicit credentials (IAM role)."""
    with patch("foreman.storage.s3_storage.boto3.client") as mock_client:
        mock_client.return_value = MagicMock()
        storage = S3Storage(configured_settings_iam_role)

        assert storage._client is not None
        mock_client.assert_called_once()
        call_kwargs = mock_client.call_args[1]
        assert call_kwargs["region_name"] == "us-east-1"
        assert "aws_access_key_id" not in call_kwargs


def test_initialization_unconfigured_logs_warning(unconfigured_settings):
    """S3Storage should log warning and set _client to None when unconfigured."""
    storage = S3Storage(unconfigured_settings)
    assert storage._client is None


def test_ensure_client_raises_value_error_when_unconfigured(unconfigured_settings):
    """_ensure_client should raise ValueError with env var names."""
    storage = S3Storage(unconfigured_settings)
    
    with pytest.raises(ValueError, match="S3_ACCESS_KEY_ID"):
        storage._ensure_client()


@pytest.mark.asyncio
async def test_create_upload_url_returns_upload_intent(configured_settings_with_creds):
    """create_upload_url should return UploadIntent with presigned URL."""
    storage = S3Storage(configured_settings_with_creds)
    storage._client = MagicMock()
    storage._client.generate_presigned_url = MagicMock(return_value="https://upload.url")

    project_id = uuid.uuid4()
    intent = await storage.create_upload_url("test.jpg", "image/jpeg", project_id)

    assert intent.upload_url == "https://upload.url"
    assert intent.file_key.startswith(f"projects/{project_id}/")
    assert intent.file_key.endswith("test.jpg")
    assert intent.expires_at > datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_create_upload_url_key_pattern(configured_settings_with_creds):
    """create_upload_url should generate key matching projects/{id}/{uuid}/{filename}."""
    storage = S3Storage(configured_settings_with_creds)
    storage._client = MagicMock()
    storage._client.generate_presigned_url = MagicMock(return_value="https://upload.url")

    project_id = uuid.uuid4()
    intent = await storage.create_upload_url("image.png", "image/png", project_id)

    parts = intent.file_key.split("/")
    assert parts[0] == "projects"
    assert parts[1] == str(project_id)
    # parts[2] should be a UUID
    assert len(parts[2]) == 36  # UUID length
    assert parts[3] == "image.png"


@pytest.mark.asyncio
async def test_create_upload_url_binds_content_type(configured_settings_with_creds):
    """create_upload_url should include ContentType in presigned URL call."""
    storage = S3Storage(configured_settings_with_creds)
    storage._client = MagicMock()
    storage._client.generate_presigned_url = MagicMock(return_value="https://upload.url")

    await storage.create_upload_url("test.jpg", "image/jpeg", uuid.uuid4())

    call_args = storage._client.generate_presigned_url.call_args
    assert call_args[1]["Params"]["ContentType"] == "image/jpeg"


@pytest.mark.asyncio
async def test_get_download_url_uses_public_url(configured_settings_with_creds):
    """get_download_url should use public_url when configured."""
    configured_settings_with_creds.public_url = "https://cdn.example.com"
    storage = S3Storage(configured_settings_with_creds)
    storage._client = MagicMock()

    url = await storage.get_download_url("path/to/file.jpg")

    assert url == "https://cdn.example.com/path/to/file.jpg"
    storage._client.generate_presigned_url.assert_not_called()


@pytest.mark.asyncio
async def test_get_download_url_generates_presigned(configured_settings_with_creds):
    """get_download_url should generate presigned URL when public_url not set."""
    configured_settings_with_creds.public_url = None
    storage = S3Storage(configured_settings_with_creds)
    storage._client = MagicMock()
    storage._client.generate_presigned_url = MagicMock(return_value="https://presigned.url")

    url = await storage.get_download_url("path/to/file.jpg")

    assert url == "https://presigned.url"
    storage._client.generate_presigned_url.assert_called_once_with(
        "get_object",
        Params={"Bucket": "test-bucket", "Key": "path/to/file.jpg"},
        ExpiresIn=3600,
    )


@pytest.mark.asyncio
async def test_delete_returns_true_on_success(configured_settings_with_creds):
    """delete should return True when deletion succeeds."""
    storage = S3Storage(configured_settings_with_creds)
    storage._client = MagicMock()
    storage._client.delete_object = MagicMock()

    with patch("foreman.storage.s3_storage.asyncio.to_thread") as mock_to_thread:
        mock_to_thread.return_value = None
        result = await storage.delete("some/key")

    assert result is True


@pytest.mark.asyncio
async def test_delete_returns_false_on_client_error(configured_settings_with_creds):
    """delete should return False on ClientError without raising."""
    from botocore.exceptions import ClientError
    
    storage = S3Storage(configured_settings_with_creds)
    storage._client = MagicMock()
    
    error = ClientError({"Error": {"Code": "NoSuchKey"}}, "DeleteObject")
    with patch("foreman.storage.s3_storage.asyncio.to_thread") as mock_to_thread:
        mock_to_thread.side_effect = error
        result = await storage.delete("some/key")

    assert result is False


@pytest.mark.asyncio
async def test_upload_file_calls_upload_fileobj_via_thread(configured_settings_with_creds):
    """upload_file should call upload_fileobj via asyncio.to_thread."""
    storage = S3Storage(configured_settings_with_creds)
    storage._client = MagicMock()

    with patch("foreman.storage.s3_storage.asyncio.to_thread") as mock_to_thread:
        mock_to_thread.return_value = None
        with patch("builtins.open", create=True) as mock_open:
            mock_open.return_value.__enter__ = MagicMock()
            mock_open.return_value.__exit__ = MagicMock(return_value=False)
            
            await storage.upload_file("/tmp/test.png", "generations/test.png")

    # Verify asyncio.to_thread was called
    mock_to_thread.assert_called_once()


@pytest.mark.asyncio
async def test_upload_file_raises_when_unconfigured(unconfigured_settings):
    """upload_file should raise ValueError when storage is not configured."""
    storage = S3Storage(unconfigured_settings)

    with pytest.raises(ValueError, match="not configured"):
        await storage.upload_file("/tmp/test.png", "generations/test.png")
