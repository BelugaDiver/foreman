"""SQS queue implementation."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import boto3
from botocore.config import Config

from foreman.logging_config import get_logger
from foreman.queue.protocol import QueueMessage, QueueProtocol
from foreman.queue.settings import SQSSettings

logger = get_logger("foreman.queue.sqs")


class SQSQueue(QueueProtocol):
    """AWS SQS queue implementation using boto3."""

    def __init__(self, settings: SQSSettings) -> None:
        self._settings = settings
        self._config = Config(retries={"max_attempts": settings.max_retries, "mode": "standard"})
        self._client = None

    def _get_client(self):
        """Get or create the boto3 SQS client."""
        if self._client is None:
            self._client = boto3.client(
                "sqs",
                region_name=self._settings.region,
                aws_access_key_id=self._settings.access_key_id,
                aws_secret_access_key=self._settings.secret_access_key,
                config=self._config,
            )
        return self._client

    async def publish(self, message: QueueMessage) -> str:
        """Publish a message to the SQS queue (async wrapper around boto3)."""
        client = self._get_client()

        publish_kwargs: dict[str, Any] = {
            "QueueUrl": self._settings.queue_url,
            "MessageBody": json.dumps(message.body),
        }

        if message.message_attributes:
            publish_kwargs["MessageAttributes"] = {
                key: {"StringValue": str(value), "DataType": "String"}
                for key, value in message.message_attributes.items()
            }

        if self._settings.visibility_timeout_seconds > 0:
            publish_kwargs["VisibilityTimeout"] = self._settings.visibility_timeout_seconds

        try:
            logger.debug(
                "Publishing message to SQS",
                extra={"queue_url": self._settings.queue_url},
            )

            response = await asyncio.to_thread(client.send_message, **publish_kwargs)
            message_id = response["MessageId"]

            logger.info(
                "Message published to SQS",
                extra={
                    "message_id": message_id,
                    "queue_url": self._settings.queue_url,
                    "generation_id": message.body.get("generation_id"),
                },
            )

            return message_id
        except Exception:
            logger.exception(
                "Failed to publish message to SQS",
                extra={
                    "queue_url": self._settings.queue_url,
                    "generation_id": message.body.get("generation_id"),
                },
            )
            raise

    async def close(self) -> None:
        """Close the SQS client (no-op for boto3)."""
        self._client = None
