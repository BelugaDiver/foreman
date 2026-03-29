"""Tests for SQS queue implementation."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest

from foreman.queue.protocol import QueueMessage
from foreman.queue.sqs_queue import SQSQueue


class TestSQSQueue:
    """Tests for SQSQueue."""

    @pytest.fixture
    def sqs_queue(self):
        """Create SQS queue with test settings."""
        from foreman.queue.settings import SQSSettings

        settings = SQSSettings(
            queue_url="https://sqs.us-east-1.amazonaws.com/123456789/test-queue",
            region="us-east-1",
            access_key_id="test-key",
            secret_access_key="test-secret",
        )
        return SQSQueue(settings)

    @pytest.mark.asyncio
    async def test_publish_sends_message(self, sqs_queue):
        """Publishing a message should call SQS client."""
        message = QueueMessage(
            body={"generation_id": str(uuid.uuid4()), "prompt": "test"},
        )

        mock_client = AsyncMock()
        mock_client.send_message = AsyncMock(return_value={"MessageId": "test-message-id"})

        with patch.object(sqs_queue, "_get_client", new_callable=AsyncMock) as mock_get_client:
            mock_get_client.return_value = mock_client

            result = await sqs_queue.publish(message)

            mock_client.send_message.assert_called_once()
            call_kwargs = mock_client.send_message.call_args.kwargs
            assert call_kwargs["QueueUrl"] == sqs_queue._settings.queue_url
            assert "MessageBody" in call_kwargs
            assert result == "test-message-id"

    @pytest.mark.asyncio
    async def test_publish_includes_message_attributes(self, sqs_queue):
        """Publishing with message attributes should include them."""
        message = QueueMessage(
            body={"generation_id": str(uuid.uuid4())},
            message_attributes={"project_id": "abc123"},
        )

        mock_client = AsyncMock()
        mock_client.send_message = AsyncMock(return_value={"MessageId": "test-id"})

        with patch.object(sqs_queue, "_get_client", new_callable=AsyncMock) as mock_get_client:
            mock_get_client.return_value = mock_client

            await sqs_queue.publish(message)

            call_kwargs = mock_client.send_message.call_args.kwargs
            assert "MessageAttributes" in call_kwargs
