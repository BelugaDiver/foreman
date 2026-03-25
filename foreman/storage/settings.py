"""Storage configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class StorageSettings:
    """Base storage configuration."""

    provider: str = "r2"
    bucket: str = "foreman-images"


@dataclass
class R2Settings(StorageSettings):
    """Cloudflare R2 configuration."""

    endpoint: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    public_url: Optional[str] = None

    @classmethod
    def from_env(cls) -> R2Settings:
        return cls(
            provider="r2",
            endpoint=os.getenv("R2_ENDPOINT"),
            access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            bucket=os.getenv("R2_BUCKET", "foreman-images"),
            public_url=os.getenv("R2_PUBLIC_URL"),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.endpoint and self.access_key_id and self.secret_access_key)


@dataclass
class S3Settings(StorageSettings):
    """AWS S3 configuration."""

    region: str = "us-east-1"
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    public_url: Optional[str] = None

    @classmethod
    def from_env(cls) -> S3Settings:
        return cls(
            provider="s3",
            bucket=os.getenv("S3_BUCKET", "foreman-images"),
            region=os.getenv("S3_REGION", "us-east-1"),
            access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
            public_url=os.getenv("S3_PUBLIC_URL"),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.access_key_id and self.secret_access_key)
