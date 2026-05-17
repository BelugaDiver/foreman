"""Amazon S3 storage implementation."""

from __future__ import annotations

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

import boto3
from botocore.exceptions import ClientError
from opentelemetry import trace

from foreman.logging_config import get_logger
from foreman.storage.protocol import StorageProtocol, UploadIntent
from foreman.storage.settings import S3Settings

logger = get_logger("foreman.storage.s3")
tracer = trace.get_tracer(__name__)


class S3Storage(StorageProtocol):
    """Amazon S3 storage implementation."""

    def __init__(self, settings: S3Settings) -> None:
        """Initialize S3 storage with the given settings.

        Args:
            settings: S3Settings object with bucket, region, and optional credentials.
        """
        self._settings = settings
        self._client = None
        self._bucket = settings.bucket if settings.is_configured else None

        if settings.is_configured:
            self._client = self._create_client()
            logger.info(
                "S3 Storage initialized",
                extra={"bucket": self._bucket, "region": settings.region},
            )
        else:
            logger.warning("S3 Storage not configured - operations will fail if attempted")

    def _create_client(self):
        """Create a boto3 S3 client with the configured settings.

        Uses the explicit regional endpoint to avoid 301 redirects for buckets
        outside us-east-1. Without this, boto3 generates presigned URLs pointing
        to the global s3.amazonaws.com endpoint, which redirects non-us-east-1
        buckets. Browsers abort CORS preflights on redirects, causing upload failures.
        """
        from botocore.config import Config

        client_kwargs = {
            "region_name": self._settings.region,
            "endpoint_url": f"https://s3.{self._settings.region}.amazonaws.com",
            "config": Config(s3={"addressing_style": "virtual"}),
        }
        if self._settings.access_key_id:
            client_kwargs["aws_access_key_id"] = self._settings.access_key_id
            client_kwargs["aws_secret_access_key"] = self._settings.secret_access_key
        return boto3.client("s3", **client_kwargs)

    def _ensure_client(self) -> None:
        """Ensure the boto3 client is initialized.

        Raises:
            ValueError: If S3 storage is not configured.
        """
        if self._client is None:
            raise ValueError(
                "S3Storage is not configured. Set S3_ACCESS_KEY_ID, S3_SECRET_ACCESS_KEY "
                "(or use IAM roles), S3_BUCKET, and S3_REGION environment variables."
            )

    async def create_upload_url(
        self,
        filename: str,
        content_type: str,
        project_id: uuid.UUID,
    ) -> UploadIntent:
        """Generate a presigned PUT URL for direct browser upload.

        Args:
            filename: Original filename for the S3 key.
            content_type: MIME type of the file.
            project_id: Project ID for key organization.

        Returns:
            UploadIntent with presigned URL, file key, and expiry time.

        Raises:
            ValueError: If storage is not configured.
        """
        self._ensure_client()

        with tracer.start_as_current_span("s3_create_upload_url") as span:
            key = f"projects/{project_id}/{uuid.uuid4()}/{filename}"
            span.set_attribute("storage_key", key)
            span.set_attribute("bucket", self._bucket)

            expires = timedelta(hours=1)
            logger.debug(
                "Generating presigned upload URL",
                extra={
                    "file_name": filename,
                    "content_type": content_type,
                    "project_id": str(project_id),
                },
            )

            try:
                url = self._client.generate_presigned_url(
                    "put_object",
                    Params={
                        "Bucket": self._bucket,
                        "Key": key,
                        "ContentType": content_type,
                    },
                    ExpiresIn=int(expires.total_seconds()),
                )
                span.set_attribute("outcome", "success")
                return UploadIntent(
                    upload_url=url,
                    file_key=key,
                    expires_at=datetime.now(timezone.utc) + expires,
                )
            except Exception as e:
                span.set_attribute("outcome", "error")
                span.record_exception(e)
                logger.exception("Failed to generate upload URL")
                raise

    async def get_download_url(self, storage_key: str) -> str:
        """Get a URL for downloading the file from storage.

        If S3_PUBLIC_URL is configured, returns a direct URL without presigning.
        Otherwise, generates a 1-hour presigned GET URL.

        Args:
            storage_key: The storage key of the file.

        Returns:
            A URL for downloading the file.

        Raises:
            ValueError: If storage is not configured.
        """
        self._ensure_client()

        with tracer.start_as_current_span("s3_get_download_url") as span:
            span.set_attribute("storage_key", storage_key)
            span.set_attribute("bucket", self._bucket)

            logger.debug("Getting download URL", extra={"storage_key": storage_key})

            try:
                if self._settings.public_url:
                    url = f"{self._settings.public_url}/{storage_key}"
                    span.set_attribute("outcome", "public_url")
                    return url

                expires = timedelta(hours=1)
                url = self._client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self._bucket, "Key": storage_key},
                    ExpiresIn=int(expires.total_seconds()),
                )
                span.set_attribute("outcome", "presigned")
                return url
            except Exception as e:
                span.set_attribute("outcome", "error")
                span.record_exception(e)
                logger.exception("Failed to get download URL")
                raise

    async def delete(self, storage_key: str) -> bool:
        """Delete a file from S3 storage.

        Args:
            storage_key: The storage key of the file to delete.

        Returns:
            True if deletion succeeded, False if it failed (logged but not raised).
        """
        self._ensure_client()

        with tracer.start_as_current_span("s3_delete") as span:
            span.set_attribute("storage_key", storage_key)
            span.set_attribute("bucket", self._bucket)

            logger.info("Deleting object from S3", extra={"storage_key": storage_key})
            try:
                await asyncio.to_thread(
                    self._client.delete_object,
                    Bucket=self._bucket,
                    Key=storage_key,
                )
                span.set_attribute("outcome", "success")
                return True
            except ClientError as e:
                span.set_attribute("outcome", "error")
                span.record_exception(e)
                logger.exception("Failed to delete object from S3", extra={"storage_key": storage_key})
                return False

    async def upload_file(self, local_path: str, storage_key: str) -> None:
        """Upload a local file directly to S3 at the given key.

        Args:
            local_path: Absolute path of the local file to upload.
            storage_key: Destination key in the S3 bucket.

        Raises:
            ValueError: If storage is not configured.
        """
        self._ensure_client()

        with tracer.start_as_current_span("s3_upload_file") as span:
            span.set_attribute("storage_key", storage_key)
            span.set_attribute("bucket", self._bucket)

            logger.debug("Uploading file to S3", extra={"storage_key": storage_key})
            try:
                with open(local_path, "rb") as f:
                    await asyncio.to_thread(
                        self._client.upload_fileobj,
                        f,
                        self._bucket,
                        storage_key,
                        ExtraArgs={"ContentType": "image/png"},
                    )
                span.set_attribute("outcome", "success")
                logger.info("Uploaded file to S3", extra={"storage_key": storage_key})
            except Exception as e:
                span.set_attribute("outcome", "error")
                span.record_exception(e)
                logger.exception("Failed to upload file to S3", extra={"storage_key": storage_key})
                raise
