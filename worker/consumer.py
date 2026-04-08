"""SQS consumer for processing generation jobs."""

from __future__ import annotations

import asyncio
import json
import logging
import os
from dataclasses import dataclass
from typing import Callable

import boto3
from botocore.config import Config

logger = logging.getLogger("worker.consumer")


@dataclass
class GenerationJob:
    """Represents a generation job from SQS."""

    generation_id: str
    project_id: str
    prompt: str
    style_id: str | None
    input_image_url: str
    created_at: str
    retry_count: int = 0

    @classmethod
    def from_message(cls, body: dict) -> "GenerationJob":
        return cls(
            generation_id=body["generation_id"],
            project_id=body["project_id"],
            prompt=body["prompt"],
            style_id=body.get("style_id"),
            input_image_url=body["input_image_url"],
            created_at=body["created_at"],
            retry_count=body.get("retry_count", 0),
        )


class SQSConsumer:
    """Consumes messages from SQS queue with concurrency control."""

    def __init__(
        self,
        queue_url: str,
        process_fn: Callable,
        concurrency: int = 1,
        max_retries: int = 3,
    ):
        self.queue_url = queue_url
        self.process_fn = process_fn
        self.concurrency = concurrency
        self.max_retries = max_retries
        self._client = None
        self._running = False
        self._semaphore = asyncio.Semaphore(concurrency)
        self._in_flight: set[asyncio.Task] = set()

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "sqs",
                region_name=os.getenv("AWS_REGION", "us-east-1"),
                aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
                aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
                config=Config(retries={"max_attempts": 3, "mode": "standard"}),
            )
        return self._client

    async def poll(self):
        """Poll for messages and process them concurrently."""
        client = self._get_client()

        batch_size = min(self.concurrency, 10)

        response = await asyncio.to_thread(
            client.receive_message,
            QueueUrl=self.queue_url,
            MaxNumberOfMessages=batch_size,
            WaitTimeSeconds=10,
            VisibilityTimeout=300,
            AttributeNames=["ApproximateReceiveCount"],
        )

        messages = response.get("Messages", [])
        tasks = []
        for msg in messages:
            task = asyncio.create_task(self._handle_message(msg))
            self._in_flight.add(task)
            task.add_done_callback(self._in_flight.discard)

        if tasks:
            await asyncio.gather(*tasks)

    async def _handle_message(self, msg: dict, retry_count: int = 0):
        """Handle a single SQS message with semaphore protection."""
        async with self._semaphore:
            client = self._get_client()
            try:
                body = json.loads(msg["Body"])
                job = GenerationJob.from_message(body)

                receive_count = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", 1))
                actual_retry = max(0, receive_count - 1)

                logger.info(
                    "Received job",
                    extra={"generation_id": job.generation_id, "retry": actual_retry},
                )

                await self.process_fn(job, retry_count=actual_retry)

                await asyncio.to_thread(
                    client.delete_message,
                    QueueUrl=self.queue_url,
                    ReceiptHandle=msg["ReceiptHandle"],
                )
                logger.info("Job completed", extra={"generation_id": job.generation_id})

            except Exception:
                logger.exception("Failed to process message", extra={"retry": retry_count})

                if retry_count >= self.max_retries:
                    logger.error(
                        "Max retries exceeded, discarding message",
                        extra={"generation_id": job.generation_id},
                    )
                    await asyncio.to_thread(
                        client.delete_message,
                        QueueUrl=self.queue_url,
                        ReceiptHandle=msg["ReceiptHandle"],
                    )
                else:
                    raise

    async def start(self):
        """Run the consumer loop."""
        self._running = True
        logger.info("Starting SQS consumer", extra={"queue_url": self.queue_url})

        while self._running:
            try:
                await self.poll()
                await asyncio.sleep(1)
            except Exception:
                logger.exception("Error in consumer loop")
                await asyncio.sleep(5)

    async def stop(self, timeout: float = 30.0):
        """Stop the consumer gracefully, waiting for in-flight jobs."""
        logger.info("Stopping consumer...")
        self._running = False

        if self._in_flight:
            await asyncio.wait_for(
                asyncio.gather(*self._in_flight, return_exceptions=True),
                timeout=timeout,
            )
        logger.info("Consumer stopped")

    def is_ready(self) -> bool:
        """Health check - returns True if consumer is running."""
        return self._running
