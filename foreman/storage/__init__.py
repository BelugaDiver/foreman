"""Storage abstraction for cloud object storage."""

from foreman.storage.factory import get_storage, get_storage_sync
from foreman.storage.protocol import StorageProtocol, UploadIntent
from foreman.storage.r2_storage import R2Storage

__all__ = ["StorageProtocol", "UploadIntent", "R2Storage", "get_storage", "get_storage_sync"]
