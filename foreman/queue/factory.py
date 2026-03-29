"""Queue factory for creating queue backends."""

from __future__ import annotations

import os
from functools import lru_cache

from foreman.logging_config import get_logger
from foreman.queue.protocol import QueueProtocol
from foreman.queue.settings import SQSSettings
from foreman.queue.sqs_queue import SQSQueue

logger = get_logger("foreman.queue.factory")


class NoOpQueue(QueueProtocol):
    """No-op queue for when queue is disabled."""

    async def publish(self, message):
        """No-op publish."""
        logger.debug("Queue disabled, skipping publish", extra={"body": message.body})
        return None

    async def close(self):
        """No-op close."""


@lru_cache(maxsize=1)
def get_queue() -> QueueProtocol:
    """Create a queue backend based on QUEUE_PROVIDER env var."""
    provider = os.getenv("QUEUE_PROVIDER", "none").lower()
    logger.debug("Initializing queue", extra={"provider": provider})

    if provider == "none":
        logger.info("Queue disabled")
        return NoOpQueue()

    if provider == "sqs":
        settings = SQSSettings.from_env()
        if not settings.is_configured:
            logger.warning("SQS queue requested but SQS_QUEUE_URL not configured, disabling queue")
            return NoOpQueue()
        queue = SQSQueue(settings)
        logger.info("SQS queue initialized", extra={"queue_url": settings.queue_url})
        return queue

    raise ValueError(f"Unknown QUEUE_PROVIDER: {provider}")
