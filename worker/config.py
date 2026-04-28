"""Worker configuration."""

from __future__ import annotations

import os
import urllib.parse
from dataclasses import dataclass, field


@dataclass
class WorkerConfig:
    """Worker-specific configuration.

    Reuses SQS settings from foreman.queue.settings.
    """

    concurrency: int = field(default_factory=lambda: int(os.getenv("WORKER_CONCURRENCY", "1")))
    max_retries: int = field(default_factory=lambda: int(os.getenv("WORKER_MAX_RETRIES", "3")))
    poll_interval: int = field(default_factory=lambda: int(os.getenv("WORKER_POLL_INTERVAL", "10")))
    visibility_timeout: int = field(
        default_factory=lambda: int(os.getenv("WORKER_VISIBILITY_TIMEOUT", "300"))
    )

    database_url: str = field(
        default_factory=lambda: os.getenv("DATABASE_URL", "postgresql://localhost/foreman")
    )

    ai_provider: str = field(default_factory=lambda: os.getenv("AI_PROVIDER", "vertex"))
    google_project_id: str | None = field(default_factory=lambda: os.getenv("GOOGLE_PROJECT_ID"))
    google_location: str = field(
        default_factory=lambda: os.getenv("GOOGLE_LOCATION", "us-central1")
    )
    gemini_image_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview")
    )
    gemini_enhancement_model: str = field(
        default_factory=lambda: os.getenv("GEMINI_ENHANCEMENT_MODEL", "gemini-2.0-flash")
    )

    r2_bucket: str = field(default_factory=lambda: os.getenv("R2_BUCKET", "foreman-assets"))
    r2_account_id: str = field(default_factory=lambda: os.getenv("R2_ACCOUNT_ID", ""))
    r2_endpoint: str = field(default_factory=lambda: os.getenv("R2_ENDPOINT", ""))
    r2_public_url: str = field(default_factory=lambda: os.getenv("R2_PUBLIC_URL", ""))
    r2_access_key_id: str = field(default_factory=lambda: os.getenv("R2_ACCESS_KEY_ID", ""))
    r2_secret_access_key: str = field(default_factory=lambda: os.getenv("R2_SECRET_ACCESS_KEY", ""))

    aws_access_key_id: str | None = field(
        default_factory=lambda: os.getenv("AWS_ACCESS_KEY_ID")
    )
    aws_secret_access_key: str | None = field(
        default_factory=lambda: os.getenv("AWS_SECRET_ACCESS_KEY")
    )
    aws_region: str = field(
        default_factory=lambda: os.getenv("AWS_REGION", "us-east-1")
    )

    @classmethod
    def from_env(cls) -> "WorkerConfig":
        return cls()

    def get_allowed_image_domains(self) -> set[str]:
        """Get allowed domains for input image downloads (SSRF protection)."""
        domains = set()
        if self.r2_public_url:
            parsed = urllib.parse.urlparse(self.r2_public_url)
            if parsed.hostname:
                domains.add(parsed.hostname)
        if self.r2_endpoint:
            parsed = urllib.parse.urlparse(self.r2_endpoint)
            if parsed.hostname:
                domains.add(parsed.hostname)
        return domains


def get_worker_config() -> WorkerConfig:
    return WorkerConfig.from_env()
