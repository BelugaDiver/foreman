"""SQS queue implementation."""

from __future__ import annotations

import json
from typing import Any

import aiobotocore.session

from foreman.logging_config import get_logger
from foreman.queue.protocol import QueueMessage, QueueProtocol
from foreman.queue.settings import SQSSettings

logger = get_logger("foreman.queue.sqs")


class SQSQueue(QueueProtocol):
    """AWS SQS queue implementation."""

    def __init__(self, settings: SQSSettings) -> None:
        self._settings = settings
        self._session = aiobotocore.session.get_session()
        self._client = None

    async def _get_client(self):
        """Get or create the SQS client."""
        if self._client is None:
            ctx = self._session.create_client(
                "sqs",
                region_name=self._settings.region,
                aws_access_key_id=self._settings.access_key_id,
                aws_secret_access_key=self._settings.secret_access_key,
            )
            self._client = await ctx.__aenter__()
        return self._client

    async def publish(self, message: QueueMessage) -> str:
        """Publish a message to the SQS queue."""
        client = await self._get_client()

        publish_kwargs: dict[str, Any] = {
            "QueueUrl": self._settings.queue_url,
            "MessageBody": json.dumps(message.body),
        }

        if message.message_attributes:
            publish_kwargs["MessageAttributes"] = {
                key: {"StringValue": value, "DataType": "String"}
                for key, value in message.message_attributes.items()
            }

        try:
            logger.debug(
                "Publishing message to SQS",
                extra={"queue_url": self._settings.queue_url},
            )

            response = await client.send_message(**publish_kwargs)
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
        """Close the SQS client."""
        if self._client is not None:
            await self._client.close()
            self._client = None
