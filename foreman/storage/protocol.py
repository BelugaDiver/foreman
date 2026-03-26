"""Storage abstraction layer for cloud object storage."""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime


@dataclass
class UploadIntent:
    """Result of creating an upload intent."""

    upload_url: str
    file_key: str
    expires_at: datetime


class StorageProtocol(ABC):
    """Abstract storage interface."""

    @abstractmethod
    async def create_upload_url(
        self,
        filename: str,
        content_type: str,
        project_id: uuid.UUID,
    ) -> UploadIntent:
        """Generate a presigned URL for direct upload."""

    @abstractmethod
    async def get_download_url(self, storage_key: str) -> str:
        """Get a URL for downloading the file."""

    @abstractmethod
    async def delete(self, storage_key: str) -> bool:
        """Delete a file from storage."""
