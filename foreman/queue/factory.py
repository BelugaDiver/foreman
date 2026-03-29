"""Queue factory for creating queue backends."""

from __future__ import annotations

import os
from functools import lru_cache

from foreman.logging_config import get_logger
from foreman.queue.protocol import QueueProtocol
from foreman.queue.sqs_queue import SQSQueue
from foreman.queue.settings import SQSSettings

logger = get_logger("foreman.queue.factory")


@lru_cache(maxsize=1)
def get_queue() -> QueueProtocol:
    """Create a queue backend based on QUEUE_PROVIDER env var."""
    provider = os.getenv("QUEUE_PROVIDER", "sqs").lower()
    logger.debug("Initializing queue", extra={"provider": provider})

    if provider == "sqs":
        settings = SQSSettings.from_env()
        if not settings.is_configured:
            raise ValueError("SQS_QUEUE_URL is not configured")
        queue = SQSQueue(settings)
        logger.info("SQS queue initialized", extra={"queue_url": settings.queue_url})
        return queue

    raise ValueError(f"Unknown QUEUE_PROVIDER: {provider}")
