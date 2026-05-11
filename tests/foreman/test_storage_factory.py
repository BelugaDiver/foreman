"""Tests for the storage factory."""

from unittest.mock import patch

import pytest

from foreman.storage.factory import get_storage
from foreman.storage.r2_storage import R2Storage
from foreman.storage.s3_storage import S3Storage


@pytest.fixture(autouse=True)
def clear_factory_cache():
    """Clear the factory cache before and after each test."""
    get_storage.cache_clear()
    yield
    get_storage.cache_clear()


def test_factory_returns_r2_storage_by_default():
    """get_storage() returns R2Storage when STORAGE_PROVIDER is not set."""
    with patch.dict("os.environ", {}, clear=False):
        # Ensure STORAGE_PROVIDER is not set (or is "r2" by default)
        if "STORAGE_PROVIDER" in __import__("os").environ:
            del __import__("os").environ["STORAGE_PROVIDER"]
        
        storage = get_storage()
        assert isinstance(storage, R2Storage)


def test_factory_returns_r2_storage_when_set():
    """get_storage() returns R2Storage when STORAGE_PROVIDER=r2."""
    with patch.dict("os.environ", {"STORAGE_PROVIDER": "r2"}):
        storage = get_storage()
        assert isinstance(storage, R2Storage)


def test_factory_returns_s3_storage_when_set():
    """get_storage() returns S3Storage when STORAGE_PROVIDER=s3."""
    with patch.dict("os.environ", {"STORAGE_PROVIDER": "s3"}):
        storage = get_storage()
        assert isinstance(storage, S3Storage)


def test_factory_raises_for_unknown_provider():
    """get_storage() raises ValueError for unknown provider."""
    with patch.dict("os.environ", {"STORAGE_PROVIDER": "gcs"}):
        with pytest.raises(ValueError, match="Unknown STORAGE_PROVIDER.*r2, s3"):
            get_storage()


def test_factory_is_case_insensitive():
    """get_storage() is case-insensitive for provider name."""
    with patch.dict("os.environ", {"STORAGE_PROVIDER": "S3"}):
        storage = get_storage()
        assert isinstance(storage, S3Storage)

    get_storage.cache_clear()
    
    with patch.dict("os.environ", {"STORAGE_PROVIDER": "R2"}):
        storage = get_storage()
        assert isinstance(storage, R2Storage)
