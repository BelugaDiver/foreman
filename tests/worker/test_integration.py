"""Integration tests for worker SQS processing using moto.

These tests require real boto3 for moto to work and must run in isolation from test_basic.
In CI, run as: pytest tests/worker/test_integration.py
"""

import json
import os
from unittest.mock import AsyncMock

import pytest

# Set up environment
os.environ["AWS_ACCESS_KEY_ID"] = "test"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
os.environ["AWS_REGION"] = "us-east-1"


@pytest.fixture
def mock_process_fn():
    """Mock function to process jobs."""
    return AsyncMock(return_value={"output_image_url": "https://example.com/output.jpg"})


# Import worker modules (conftest provides basic mocks for foreman)
from worker.consumer import GenerationJob, MalformedSQSMessageError, SQSConsumer


@pytest.mark.asyncio
async def test_worker_processes_sqs_message(mock_process_fn):
    """Worker should process SQS message and call process function."""
    import moto
    import boto3

    call_count = 0
    processed_jobs = []

    async def tracking_fn(job, retry_count=0):
        nonlocal call_count
        call_count += 1
        processed_jobs.append(job)

    with moto.mock_aws():
        sqs = boto3.client("sqs", region_name="us-east-1")
        queue = sqs.create_queue(QueueName="test-queue")
        queue_url = queue["QueueUrl"]

        message_body = {
            "generation_id": "123e4567-e89b-12d3-a456-426614174000",
            "project_id": "123e4567-e89b-12d3-a456-426614174001",
            "prompt": "modern living room",
            "style_id": None,
            "input_image_url": "https://example.com/input.jpg",
            "created_at": "2026-04-16T12:00:00",
        }
        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(message_body),
            MessageAttributes={
                "generation_id": {
                    "StringValue": "123e4567-e89b-12d3-a456-426614174000",
                    "DataType": "String",
                },
            },
        )

        consumer = SQSConsumer(
            queue_url=queue_url,
            process_fn=tracking_fn,
            concurrency=1,
        )

        await consumer.poll()

    assert call_count == 1, f"Expected 1 call, got {call_count}"
    assert len(processed_jobs) == 1
    assert processed_jobs[0].generation_id == "123e4567-e89b-12d3-a456-426614174000"
    assert processed_jobs[0].prompt == "modern living room"


@pytest.mark.asyncio
async def test_worker_handles_malformed_message():
    """Worker should handle malformed SQS messages gracefully."""
    with pytest.raises(MalformedSQSMessageError):
        GenerationJob.from_message({"generation_id": "123"}, {})

    job = GenerationJob.from_message(
        {
            "generation_id": "gen-1",
            "project_id": "proj-1",
            "prompt": "test",
            "input_image_url": "https://example.com/img.jpg",
            "created_at": "2026-04-16T12:00:00",
        },
        {},
    )
    assert job.generation_id == "gen-1"
    assert job.prompt == "test"


@pytest.mark.asyncio
async def test_worker_processes_multiple_messages():
    """Worker should process multiple SQS messages concurrently."""
    import moto
    import boto3

    processed_jobs = []

    async def process_fn(job, retry_count=0):
        processed_jobs.append(job)

    with moto.mock_aws():
        sqs = boto3.client("sqs", region_name="us-east-1")
        queue = sqs.create_queue(QueueName="test-multi-queue")
        queue_url = queue["QueueUrl"]

        for i in range(3):
            sqs.send_message(
                QueueUrl=queue_url,
                MessageBody=json.dumps(
                    {
                        "generation_id": f"gen-{i}",
                        "project_id": "proj-1",
                        "prompt": f"test prompt {i}",
                        "input_image_url": "https://example.com/img.jpg",
                        "created_at": "2026-04-16T12:00:00",
                    }
                ),
            )

        consumer = SQSConsumer(
            queue_url=queue_url,
            process_fn=process_fn,
            concurrency=3,
        )

        await consumer.poll()

    assert len(processed_jobs) == 3


@pytest.mark.asyncio
async def test_worker_deletes_message_after_processing():
    """Worker should delete SQS message after successful processing."""
    import moto
    import boto3

    process_fn = AsyncMock(return_value={"output_image_url": "https://example.com/output.jpg"})

    with moto.mock_aws():
        sqs = boto3.client("sqs", region_name="us-east-1")
        queue = sqs.create_queue(QueueName="test-delete-queue")
        queue_url = queue["QueueUrl"]

        sqs.send_message(
            QueueUrl=queue_url,
            MessageBody=json.dumps(
                {
                    "generation_id": "gen-1",
                    "project_id": "proj-1",
                    "prompt": "test",
                    "input_image_url": "https://example.com/img.jpg",
                    "created_at": "2026-04-16T12:00:00",
                }
            ),
        )

        consumer = SQSConsumer(queue_url=queue_url, process_fn=process_fn, concurrency=1)

        await consumer.poll()

        response = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)
        assert len(response.get("Messages", [])) == 0
