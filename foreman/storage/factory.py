"""Storage factory for creating storage backends."""

from __future__ import annotations

import os

from foreman.storage.protocol import StorageProtocol
from foreman.storage.r2_storage import R2Storage
from foreman.storage.settings import R2Settings, S3Settings


def get_storage() -> StorageProtocol:
    """Create a storage backend based on STORAGE_PROVIDER env var."""
    provider = os.getenv("STORAGE_PROVIDER", "r2").lower()

    if provider == "r2":
        return R2Storage(R2Settings.from_env())
    elif provider == "s3":
        from foreman.storage.s3_storage import S3Storage

        return S3Storage(S3Settings.from_env())

    raise ValueError(f"Unknown STORAGE_PROVIDER: {provider}")


def get_storage_sync() -> StorageProtocol:
    """Synchronous version for use in dependency injection."""
    return get_storage()
