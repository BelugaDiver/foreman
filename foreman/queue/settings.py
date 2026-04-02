"""SQS queue configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class SQSSettings:
    """AWS SQS configuration."""

    queue_url: Optional[str] = None
    region: str = "us-east-1"
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    max_retries: int = 3
    delay_seconds: int = 0

    @classmethod
    def from_env(cls) -> SQSSettings:
        return cls(
            queue_url=os.getenv("SQS_QUEUE_URL"),
            region=os.getenv("AWS_REGION", "us-east-1"),
            access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            max_retries=int(os.getenv("SQS_MAX_RETRIES", "3")),
            delay_seconds=int(os.getenv("SQS_DELAY_SECONDS", "0")),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.queue_url)
