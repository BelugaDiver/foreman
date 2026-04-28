"""SQS consumer for processing generation jobs."""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Callable

import boto3
from botocore.config import Config
from opentelemetry import trace

from foreman.logging_config import get_logger

logger = get_logger("worker.consumer")

tracer = trace.get_tracer(__name__)


class MalformedSQSMessageError(Exception):
    """Raised when an SQS message is missing critical fields or is malformed."""


@dataclass
class GenerationJob:
    """Represents a generation job from SQS."""

    generation_id: str
    project_id: str
    prompt: str
    style_id: str | None
    input_image_url: str
    created_at: str
    user_id: str | None
    retry_count: int = 0

    @classmethod
    def from_message(cls, body: dict, message_attributes: dict | None = None) -> "GenerationJob":
        """Construct a GenerationJob with validation of critical fields."""
        generation_id = body.get("generation_id")
        project_id = body.get("project_id")
        prompt = body.get("prompt")
        input_image_url = body.get("input_image_url")
        created_at = body.get("created_at")

        if not all([generation_id, project_id, prompt, input_image_url, created_at]):
            missing = [
                k
                for k in ["generation_id", "project_id", "prompt", "input_image_url", "created_at"]
                if not body.get(k)
            ]
            raise MalformedSQSMessageError(f"Missing critical fields: {', '.join(missing)}")

        user_id = None
        if message_attributes:
            user_id_attr = message_attributes.get("user_id", {})
            user_id = user_id_attr.get("StringValue")

        return cls(
            generation_id=generation_id,
            project_id=project_id,
            prompt=prompt,
            style_id=body.get("style_id"),
            input_image_url=input_image_url,
            created_at=created_at,
            user_id=user_id,
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
        poll_interval: int = 10,
        visibility_timeout: int = 300,
        aws_access_key_id: str | None = None,
        aws_secret_access_key: str | None = None,
        aws_region: str = "us-east-1",
    ):
        self.queue_url = queue_url
        self.process_fn = process_fn
        self.concurrency = concurrency
        self.max_retries = max_retries
        self.poll_interval = poll_interval
        self.visibility_timeout = visibility_timeout
        self.aws_access_key_id = aws_access_key_id
        self.aws_secret_access_key = aws_secret_access_key
        self.aws_region = aws_region
        self._client = None
        self._running = False
        self._semaphore = asyncio.Semaphore(concurrency)
        self._in_flight: set[asyncio.Task] = set()

    def _get_client(self):
        if self._client is None:
            self._client = boto3.client(
                "sqs",
                region_name=self.aws_region,
                aws_access_key_id=self.aws_access_key_id,
                aws_secret_access_key=self.aws_secret_access_key,
                config=Config(retries={"max_attempts": 3, "mode": "standard"}),
            )
        return self._client

    async def poll(self):
        """Poll for messages and process them concurrently."""
        with tracer.start_as_current_span("poll_sqs") as span:
            # Calculate available capacity to avoid pulling more than we can handle
            in_flight_count = len(self._in_flight)
            available_slots = self.concurrency - in_flight_count

            if available_slots <= 0:
                return

            client = self._get_client()
            batch_size = min(available_slots, 10)
            span.set_attribute("batch_size", batch_size)

            response = await asyncio.to_thread(
                client.receive_message,
                QueueUrl=self.queue_url,
                MaxNumberOfMessages=batch_size,
                WaitTimeSeconds=self.poll_interval,
                VisibilityTimeout=self.visibility_timeout,
                AttributeNames=["ApproximateReceiveCount"],
                MessageAttributeNames=["All"],
            )

            messages = response.get("Messages", [])
            span.set_attribute("message_count", len(messages))

            tasks = []
            for msg in messages:
                task = asyncio.create_task(self._handle_message(msg))
                self._in_flight.add(task)
                task.add_done_callback(self._in_flight.discard)
                tasks.append(task)
            return tasks

    async def _handle_message(self, msg: dict):
        """Handle a single SQS message with semaphore protection."""
        async with self._semaphore:
            client = self._get_client()
            actual_retry = 0
            body = {}
            try:
                body = json.loads(msg["Body"])
                message_attributes = msg.get("MessageAttributes")
                job = GenerationJob.from_message(body, message_attributes)

                receive_count = int(msg.get("Attributes", {}).get("ApproximateReceiveCount", 1))
                actual_retry = max(0, receive_count - 1)

                logger.info(
                    "Received job",
                    extra={
                        "generation_id": job.generation_id,
                        "retry": actual_retry,
                        "user_id": job.user_id,
                    },
                )

                await self.process_fn(job, retry_count=actual_retry)

                await asyncio.to_thread(
                    client.delete_message,
                    QueueUrl=self.queue_url,
                    ReceiptHandle=msg["ReceiptHandle"],
                )
                logger.info("Job completed", extra={"generation_id": job.generation_id})

            except (json.JSONDecodeError, MalformedSQSMessageError) as exc:
                logger.error("Unrecoverable malformed message", extra={"error": str(exc)})
                # Delete immediately - cannot be processed even with retries
                await asyncio.to_thread(
                    client.delete_message,
                    QueueUrl=self.queue_url,
                    ReceiptHandle=msg["ReceiptHandle"],
                )

            except Exception:
                logger.exception("Failed to process message", extra={"retry": actual_retry})

                if actual_retry >= self.max_retries:
                    logger.error(
                        "Max retries exceeded, discarding message",
                        extra={"generation_id": body.get("generation_id") if body else "unknown"},
                    )
                    await asyncio.to_thread(
                        client.delete_message,
                        QueueUrl=self.queue_url,
                        ReceiptHandle=msg["ReceiptHandle"],
                    )

    async def start(self):
        """Run the consumer loop."""
        self._running = True
        logger.info("Starting SQS consumer", extra={"queue_url": self.queue_url})

        while self._running:
            try:
                await self.poll()

                # If we are at capacity, wait for at least one task to finish
                # before polling again. This avoids a tight loop.
                if len(self._in_flight) >= self.concurrency:
                    if self._in_flight:
                        await asyncio.wait(self._in_flight, return_when=asyncio.FIRST_COMPLETED)
                else:
                    # Small sleep to prevent tight loop when no messages are available
                    await asyncio.sleep(0.1)
            except Exception:
                logger.exception("Error in consumer loop")
                await asyncio.sleep(5)

    async def stop(self, timeout: float = 30.0):
        """Stop the consumer gracefully, waiting for in-flight jobs."""
        if not self._running and not self._in_flight:
            return  # already stopped
        logger.info("Stopping consumer...")
        self._running = False

        if self._in_flight:
            try:
                await asyncio.wait_for(
                    asyncio.gather(*self._in_flight, return_exceptions=True),
                    timeout=timeout,
                )
            except asyncio.TimeoutError:
                logger.warning("Shutdown timeout, cancelling in-flight tasks")
                for task in self._in_flight:
                    task.cancel()
                if self._in_flight:
                    await asyncio.gather(*self._in_flight, return_exceptions=True)
        logger.info("Consumer stopped")

    def is_ready(self) -> bool:
        """Health check - returns True if consumer is running."""
        return self._running
