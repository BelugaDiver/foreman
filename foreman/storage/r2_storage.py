"""Cloudflare R2 storage implementation."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import anyio
import boto3
from botocore.config import Config

from foreman.logging_config import get_logger
from foreman.storage.protocol import StorageProtocol, UploadIntent
from foreman.storage.settings import R2Settings

logger = get_logger("foreman.storage.r2")


class R2Storage(StorageProtocol):
    """Cloudflare R2 storage using S3-compatible API."""

    def __init__(self, settings: R2Settings) -> None:
        if not settings.is_configured:
            raise ValueError("R2Settings is not configured")

        self._settings = settings
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
            config=Config(signature_version="s3v4"),
        )
        self._bucket = settings.bucket
        logger.info("R2 Storage initialized", extra={"bucket": self._bucket})

    async def create_upload_url(
        self,
        filename: str,
        content_type: str,
        project_id: uuid.UUID,
    ) -> UploadIntent:
        logger.debug(
            "Generating presigned upload URL",
            extra={
                "file_name": filename,
                "content_type": content_type,
                "project_id": str(project_id),
            },
        )
        key = f"projects/{project_id}/{uuid.uuid4()}/{filename}"
        expires = timedelta(hours=1)

        url = self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=int(expires.total_seconds()),
        )

        return UploadIntent(
            upload_url=url,
            file_key=key,
            expires_at=datetime.now(timezone.utc) + expires,
        )

    async def get_download_url(self, storage_key: str) -> str:
        logger.debug("Generating presigned download URL", extra={"storage_key": storage_key})
        if self._settings.public_url:
            return f"{self._settings.public_url}/{storage_key}"

        expires = timedelta(hours=1)
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": storage_key},
            ExpiresIn=int(expires.total_seconds()),
        )

    async def delete(self, storage_key: str) -> bool:
        logger.info("Deleting object from R2", extra={"storage_key": storage_key})
        try:
            await anyio.to_thread.run_sync(
                self._client.delete_object,
                Bucket=self._bucket,
                Key=storage_key,
            )
            return True
        except Exception as e:
            logger.error(
                "Failed to delete object from R2",
                extra={"storage_key": storage_key, "error": str(e)},
            )
            return False
