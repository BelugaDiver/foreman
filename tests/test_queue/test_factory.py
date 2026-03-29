"""Tests for queue factory."""

import os
from unittest.mock import patch

import pytest


class TestQueueFactory:
    """Tests for get_queue factory function."""

    def test_get_queue_sqs_unconfigured_returns_noop(self):
        """Should return NoOpQueue when SQS is not configured."""
        with patch.dict(os.environ, {"QUEUE_PROVIDER": "sqs"}, clear=False):
            with patch("foreman.queue.factory.SQSSettings") as mock_settings:
                mock_settings.from_env.return_value.is_configured = False
                mock_settings.return_value.queue_url = None

                from foreman.queue.factory import NoOpQueue, get_queue

                get_queue.cache_clear()
                queue = get_queue()
                assert isinstance(queue, NoOpQueue)

    def test_get_queue_unknown_provider_raises(self):
        """Should raise ValueError for unknown provider."""
        with patch.dict(os.environ, {"QUEUE_PROVIDER": "invalid"}, clear=False):
            from foreman.queue.factory import get_queue

            get_queue.cache_clear()
            with pytest.raises(ValueError, match="Unknown QUEUE_PROVIDER"):
                get_queue()

    def test_get_queue_none_default(self):
        """Should return NoOpQueue by default."""
        with patch.dict(os.environ, {"QUEUE_PROVIDER": "none"}, clear=False):
            from foreman.queue.factory import NoOpQueue, get_queue

            get_queue.cache_clear()
            queue = get_queue()
            assert isinstance(queue, NoOpQueue)
