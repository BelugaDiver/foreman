"""Integration tests for SQS queue publishing."""

import json

import boto3
import httpx
import moto
import pytest

from foreman.queue import factory
from tests.foreman.integration.conftest import create_project_via_api, create_user_via_api


@pytest.fixture(autouse=True)
def _aws_env(monkeypatch):
    """Set AWS environment variables and clear queue cache for each test."""
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "test")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "test")
    monkeypatch.setenv("AWS_REGION", "us-east-1")
    monkeypatch.setenv("QUEUE_PROVIDER", "sqs")
    factory.get_queue.cache_clear()
    yield
    factory.get_queue.cache_clear()



@pytest.mark.asyncio
async def test_create_generation_publishes_to_sqs(client: httpx.AsyncClient, monkeypatch):
    """Creating a generation should publish a message to SQS."""
    # Set up mocked SQS
    with moto.mock_aws():
        sqs = boto3.client("sqs", region_name="us-east-1")
        queue = sqs.create_queue(QueueName="foreman-generations")
        queue_url = queue["QueueUrl"]

        monkeypatch.setenv("SQS_QUEUE_URL", queue_url)

        # Need to reload the factory to pick up the new queue URL

        # Create user and project
        _, headers = await create_user_via_api(client, "sqs-test@example.com")
        project = await create_project_via_api(client, headers, "SQS Test")

        # Create generation
        resp = await client.post(
            f"/v1/projects/{project['id']}/generations",
            headers=headers,
            json={
                "prompt": "a modern living room",
                "model_used": "dalle-3",
                "attempt": 1,
            },
        )
        assert resp.status_code == 202

        # Verify message was published to SQS
        messages = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=10)
        assert len(messages["Messages"]) == 1

        body = json.loads(messages["Messages"][0]["Body"])
        assert "generation_id" in body
        assert body["prompt"] == "a modern living room"


@pytest.mark.asyncio
async def test_create_generation_queue_failure_doesnt_fail_request(client: httpx.AsyncClient, monkeypatch):
    """If SQS fails, the generation should still be created successfully."""
    monkeypatch.setenv("SQS_QUEUE_URL", "https://invalid-queue-url-that-does-not-exist.fake.com")

    _, headers = await create_user_via_api(client, "queue-fail@example.com")
    project = await create_project_via_api(client, headers, "Queue Fail Test")

    # Should still succeed - queue failure is logged but doesn't break the request
    resp = await client.post(
        f"/v1/projects/{project['id']}/generations",
        headers=headers,
        json={
            "prompt": "test prompt",
            "model_used": "dalle-3",
            "attempt": 1,
        },
    )
    assert resp.status_code == 202
