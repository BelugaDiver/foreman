"""Storage abstraction for cloud object storage."""

from foreman.storage.factory import get_storage, get_storage_sync
from foreman.storage.protocol import StorageProtocol, UploadIntent
from foreman.storage.r2_storage import R2Storage
from foreman.storage.s3_storage import S3Storage

__all__ = [
    "StorageProtocol",
    "UploadIntent",
    "R2Storage",
    "S3Storage",
    "get_storage",
    "get_storage_sync",
]
