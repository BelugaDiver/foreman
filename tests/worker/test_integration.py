"""Integration tests for worker SQS processing."""

import json
import os
import sys
from unittest.mock import AsyncMock, MagicMock

import pytest

os.environ["AWS_ACCESS_KEY_ID"] = "test"
os.environ["AWS_SECRET_ACCESS_KEY"] = "test"
os.environ["AWS_REGION"] = "us-east-1"

# Save original modules before any mocking
_original_modules = sys.modules.copy()


def setup_module(module):
    """Set up mock modules before worker tests - but NOT boto3/botocore for moto."""
    # Only mock these - let boto3 be real for moto to work with
    mock_modules = {
        "google": MagicMock(),
        "google.genai": MagicMock(),
        "google.genai.types": MagicMock(),
        "opentelemetry": MagicMock(),
        "opentelemetry.trace": MagicMock(),
    }

    for module_name, mock_module in mock_modules.items():
        sys.modules[module_name] = mock_module

    for mod_name in [
        "foreman",
        "foreman.db",
        "foreman.logging_config",
        "foreman.logging_config.get_logger",
        "foreman.logging_config.configure_logging",
        "foreman.queue",
        "foreman.queue.settings",
        "foreman.telemetry",
        "foreman.telemetry.setup_telemetry",
        "foreman.repositories",
        "foreman.repositories.postgres_generations_repository",
        "foreman.schemas",
        "foreman.schemas.generation",
    ]:
        sys.modules[mod_name] = MagicMock()


def teardown_module(module):
    """Clean up mocks after worker tests."""
    sys.modules.clear()
    sys.modules.update(_original_modules)


@pytest.fixture
def mock_process_fn():
    """Mock function to process jobs."""
    return AsyncMock(return_value={"output_image_url": "https://example.com/output.jpg"})


@pytest.mark.asyncio
async def test_worker_processes_sqs_message(mock_process_fn):
    """Worker should process SQS message and call process function."""
    import moto
    import boto3
    from worker.consumer import SQSConsumer

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
            process_fn=mock_process_fn,
            concurrency=1,
        )

        await consumer.poll()

        assert mock_process_fn.call_count == 1
        call_args = mock_process_fn.call_args
        job = call_args[0][0]
        assert job.generation_id == "123e4567-e89b-12d3-a456-426614174000"
        assert job.prompt == "modern living room"


@pytest.mark.asyncio
async def test_worker_handles_malformed_message():
    """Worker should handle malformed SQS messages gracefully."""
    from worker.consumer import GenerationJob, MalformedSQSMessageError

    with pytest.raises(MalformedSQSMessageError):
        GenerationJob.from_message(
            {"generation_id": "123"},
            {},
        )

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
    from worker.consumer import SQSConsumer

    processed_jobs = []

    async def process_fn(job, retry_count=0):
        processed_jobs.append(job)

    with moto.mock_aws():
        sqs = boto3.client("sqs", region_name="us-east-1")
        queue = sqs.create_queue(QueueName="test-multi-queue")
        queue_url = queue["QueueUrl"]

        for i in range(3):
            message_body = {
                "generation_id": f"gen-{i}",
                "project_id": "proj-1",
                "prompt": f"test prompt {i}",
                "input_image_url": "https://example.com/img.jpg",
                "created_at": "2026-04-16T12:00:00",
            }
            sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(message_body))

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
    from worker.consumer import SQSConsumer

    process_fn = AsyncMock(return_value={"output_image_url": "https://example.com/output.jpg"})

    with moto.mock_aws():
        sqs = boto3.client("sqs", region_name="us-east-1")
        queue = sqs.create_queue(QueueName="test-delete-queue")
        queue_url = queue["QueueUrl"]

        message_body = {
            "generation_id": "gen-1",
            "project_id": "proj-1",
            "prompt": "test",
            "input_image_url": "https://example.com/img.jpg",
            "created_at": "2026-04-16T12:00:00",
        }
        sqs.send_message(QueueUrl=queue_url, MessageBody=json.dumps(message_body))

        consumer = SQSConsumer(
            queue_url=queue_url,
            process_fn=process_fn,
            concurrency=1,
        )

        await consumer.poll()

        response = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)
        assert len(response.get("Messages", [])) == 0
