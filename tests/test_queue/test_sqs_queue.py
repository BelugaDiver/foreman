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
        """Publishing a message should call SQS client via to_thread."""
        message = QueueMessage(
            body={"generation_id": str(uuid.uuid4()), "prompt": "test"},
        )

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = {"MessageId": "test-message-id"}

            result = await sqs_queue.publish(message)

            mock_to_thread.assert_called_once()
            assert result == "test-message-id"

    @pytest.mark.asyncio
    async def test_publish_includes_message_attributes(self, sqs_queue):
        """Publishing with message attributes should include them."""
        message = QueueMessage(
            body={"generation_id": str(uuid.uuid4())},
            message_attributes={"project_id": "abc123"},
        )

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.return_value = {"MessageId": "test-id"}

            await sqs_queue.publish(message)

            call_kwargs = mock_to_thread.call_args.kwargs
            assert "MessageAttributes" in call_kwargs

    @pytest.mark.asyncio
    async def test_publish_handles_exception(self, sqs_queue):
        """Publishing should raise and log on SQS error."""
        message = QueueMessage(body={"generation_id": str(uuid.uuid4())})

        with patch("asyncio.to_thread", new_callable=AsyncMock) as mock_to_thread:
            mock_to_thread.side_effect = Exception("SQS error")

            with pytest.raises(Exception, match="SQS error"):
                await sqs_queue.publish(message)

    @pytest.mark.asyncio
    async def test_close_clears_client(self, sqs_queue):
        """Close should clear the SQS client reference."""
        mock_client = AsyncMock()
        sqs_queue._client = mock_client

        await sqs_queue.close()

        assert sqs_queue._client is None

    @pytest.mark.asyncio
    async def test_close_when_client_is_none(self, sqs_queue):
        """Close should handle None client gracefully."""
        sqs_queue._client = None

        await sqs_queue.close()

        assert sqs_queue._client is None
