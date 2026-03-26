"""Storage factory for creating storage backends."""

from __future__ import annotations

import os
from functools import lru_cache

from foreman.logging_config import get_logger
from foreman.storage.protocol import StorageProtocol
from foreman.storage.r2_storage import R2Storage
from foreman.storage.settings import R2Settings

logger = get_logger("foreman.storage")


@lru_cache(maxsize=1)
def get_storage() -> StorageProtocol:
    """Create a storage backend based on STORAGE_PROVIDER env var."""
    provider = os.getenv("STORAGE_PROVIDER", "r2").lower()
    logger.debug("Initializing storage", extra={"provider": provider})

    if provider == "r2":
        storage = R2Storage(R2Settings.from_env())
        logger.info("Storage initialized", extra={"provider": provider})
        return storage

    raise ValueError(f"Unknown STORAGE_PROVIDER: {provider}")


def get_storage_sync() -> StorageProtocol:
    """Synchronous version for use in dependency injection."""
    return get_storage()
