"""Extended tests for worker/consumer.py covering poll, _handle_message, stop."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from worker.consumer import GenerationJob, MalformedSQSMessageError, SQSConsumer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_consumer(**kwargs) -> SQSConsumer:
    defaults = dict(
        queue_url="https://sqs.us-east-1.amazonaws.com/123/test",
        process_fn=AsyncMock(),
        concurrency=2,
        max_retries=3,
        poll_interval=1,
        visibility_timeout=60,
        aws_access_key_id="key",
        aws_secret_access_key="secret",
        aws_region="us-east-1",
    )
    defaults.update(kwargs)
    return SQSConsumer(**defaults)


def _make_sqs_msg(body: dict, receipt_handle: str = "rh-1", receive_count: int = 1) -> dict:
    return {
        "Body": json.dumps(body),
        "ReceiptHandle": receipt_handle,
        "Attributes": {"ApproximateReceiveCount": str(receive_count)},
        "MessageAttributes": {
            "user_id": {"StringValue": "00000000-0000-0000-0000-000000000001", "DataType": "String"}
        },
    }


_VALID_BODY = {
    "generation_id": "00000000-0000-0000-0000-000000000002",
    "project_id": "00000000-0000-0000-0000-000000000003",
    "prompt": "paint it blue",
    "input_image_url": "https://example.com/img.jpg",
    "created_at": "2024-01-01T00:00:00Z",
}


# ---------------------------------------------------------------------------
# _get_client
# ---------------------------------------------------------------------------

def test_get_client_calls_boto3():
    """_get_client creates a boto3 SQS client with the right params."""
    consumer = _make_consumer()
    mock_client = MagicMock()
    with patch("worker.consumer.boto3.client", return_value=mock_client) as mock_boto3:
        client = consumer._get_client()
        mock_boto3.assert_called_once()
        call_kwargs = mock_boto3.call_args
        assert call_kwargs.args[0] == "sqs"
        assert call_kwargs.kwargs["region_name"] == "us-east-1"
        assert call_kwargs.kwargs["aws_access_key_id"] == "key"
        assert call_kwargs.kwargs["aws_secret_access_key"] == "secret"
        assert client is mock_client


def test_get_client_caches():
    """_get_client is called only once (lazy init)."""
    consumer = _make_consumer()
    mock_client = MagicMock()
    with patch("worker.consumer.boto3.client", return_value=mock_client) as mock_boto3:
        c1 = consumer._get_client()
        c2 = consumer._get_client()
        assert c1 is c2
        mock_boto3.assert_called_once()


# ---------------------------------------------------------------------------
# poll
# ---------------------------------------------------------------------------

async def test_poll_returns_early_when_no_capacity():
    """poll returns None when _in_flight is at concurrency limit."""
    consumer = _make_consumer(concurrency=1)
    # Fill _in_flight with a dummy never-finishing task
    dummy = asyncio.ensure_future(asyncio.sleep(9999))
    consumer._in_flight.add(dummy)
    try:
        result = await consumer.poll()
        assert result is None
    finally:
        dummy.cancel()
        try:
            await dummy
        except (asyncio.CancelledError, Exception):
            pass


async def test_poll_empty_response_returns_empty_list():
    """poll with no SQS messages returns an empty task list."""
    consumer = _make_consumer()
    mock_sqs = MagicMock()
    mock_sqs.receive_message.return_value = {"Messages": []}
    with patch("worker.consumer.boto3.client", return_value=mock_sqs):
        with patch("worker.consumer.asyncio.to_thread", new=AsyncMock(return_value={"Messages": []})):
            tasks = await consumer.poll()
    assert tasks == []


async def test_poll_creates_tasks_for_messages():
    """poll creates one asyncio.Task per received message."""
    consumer = _make_consumer(concurrency=5)
    msgs = [_make_sqs_msg(_VALID_BODY, receipt_handle=f"rh-{i}") for i in range(2)]
    response = {"Messages": msgs}

    mock_sqs = MagicMock()
    mock_sqs.receive_message.return_value = response

    with patch("worker.consumer.boto3.client", return_value=mock_sqs):
        with patch("worker.consumer.asyncio.to_thread", new=AsyncMock(return_value=response)):
            # Also patch _handle_message so tasks resolve quickly
            consumer._handle_message = AsyncMock()
            tasks = await consumer.poll()

    assert tasks is not None
    assert len(tasks) == 2
    # Clean up
    for t in tasks:
        t.cancel()
        try:
            await t
        except (asyncio.CancelledError, Exception):
            pass


# ---------------------------------------------------------------------------
# _handle_message
# ---------------------------------------------------------------------------

async def test_handle_message_success():
    """Successful message: process_fn called, then delete_message called."""
    process_fn = AsyncMock()
    consumer = _make_consumer(process_fn=process_fn)

    mock_sqs = MagicMock()
    mock_sqs.delete_message = MagicMock()

    with patch("worker.consumer.boto3.client", return_value=mock_sqs):
        with patch("worker.consumer.asyncio.to_thread", new=AsyncMock(return_value=None)):
            await consumer._handle_message(_make_sqs_msg(_VALID_BODY))

    process_fn.assert_called_once()
    job_arg = process_fn.call_args.args[0]
    assert isinstance(job_arg, GenerationJob)


async def test_handle_message_json_error_deletes_immediately():
    """JSONDecodeError → message deleted without retry."""
    process_fn = AsyncMock()
    consumer = _make_consumer(process_fn=process_fn)

    mock_sqs = MagicMock()
    bad_msg = {
        "Body": "not-json",
        "ReceiptHandle": "rh-bad",
        "Attributes": {"ApproximateReceiveCount": "1"},
    }

    deleted = []

    async def fake_to_thread(fn, *args, **kwargs):
        # Capture delete calls
        deleted.append(kwargs)
        return None

    with patch("worker.consumer.boto3.client", return_value=mock_sqs):
        with patch("worker.consumer.asyncio.to_thread", side_effect=fake_to_thread):
            await consumer._handle_message(bad_msg)

    process_fn.assert_not_called()
    # delete_message must have been called
    assert len(deleted) >= 1


async def test_handle_message_malformed_error_deletes_immediately():
    """MalformedSQSMessageError → message deleted without retry."""
    process_fn = AsyncMock()
    consumer = _make_consumer(process_fn=process_fn)

    # Valid JSON but missing critical fields
    bad_body = {"generation_id": "x"}
    msg = _make_sqs_msg(bad_body)

    deleted = []

    async def fake_to_thread(fn, *args, **kwargs):
        deleted.append(kwargs)
        return None

    with patch("worker.consumer.boto3.client", return_value=MagicMock()):
        with patch("worker.consumer.asyncio.to_thread", side_effect=fake_to_thread):
            await consumer._handle_message(msg)

    process_fn.assert_not_called()
    assert len(deleted) >= 1


async def test_handle_message_processing_error_below_max_retries_not_deleted():
    """Generic exception below max_retries → message NOT deleted (SQS retry)."""
    process_fn = AsyncMock(side_effect=RuntimeError("boom"))
    consumer = _make_consumer(process_fn=process_fn, max_retries=3)

    # receive_count=1 → actual_retry=0 which is < max_retries=3
    msg = _make_sqs_msg(_VALID_BODY, receive_count=1)

    deleted = []

    async def fake_to_thread(fn, *args, **kwargs):
        deleted.append(kwargs)
        return None

    with patch("worker.consumer.boto3.client", return_value=MagicMock()):
        with patch("worker.consumer.asyncio.to_thread", side_effect=fake_to_thread):
            await consumer._handle_message(msg)

    # delete_message should NOT have been called (message left for SQS visibility timeout)
    assert len(deleted) == 0


async def test_handle_message_processing_error_at_max_retries_deletes():
    """Generic exception at max_retries → message deleted (discard)."""
    process_fn = AsyncMock(side_effect=RuntimeError("boom"))
    consumer = _make_consumer(process_fn=process_fn, max_retries=3)

    # receive_count=4 → actual_retry=3 which == max_retries=3
    msg = _make_sqs_msg(_VALID_BODY, receive_count=4)

    deleted = []

    async def fake_to_thread(fn, *args, **kwargs):
        deleted.append(kwargs)
        return None

    with patch("worker.consumer.boto3.client", return_value=MagicMock()):
        with patch("worker.consumer.asyncio.to_thread", side_effect=fake_to_thread):
            await consumer._handle_message(msg)

    assert len(deleted) >= 1


# ---------------------------------------------------------------------------
# stop
# ---------------------------------------------------------------------------

async def test_stop_already_stopped_returns_immediately():
    """stop() returns immediately when not running and no in-flight tasks."""
    consumer = _make_consumer()
    assert consumer._running is False
    assert len(consumer._in_flight) == 0
    # Should not block or raise
    await consumer.stop(timeout=1.0)


async def test_stop_cancels_tasks_on_timeout():
    """stop() cancels in-flight tasks when they exceed the timeout."""
    consumer = _make_consumer()
    consumer._running = True

    # Create a long-running task
    long_task = asyncio.ensure_future(asyncio.sleep(9999))
    consumer._in_flight.add(long_task)

    await consumer.stop(timeout=0.05)

    assert long_task.cancelled()


async def test_stop_waits_for_in_flight_tasks():
    """stop() waits for in-flight tasks that finish in time."""
    consumer = _make_consumer()
    consumer._running = True

    finished = []

    async def quick_job():
        await asyncio.sleep(0.01)
        finished.append(True)

    task = asyncio.ensure_future(quick_job())
    consumer._in_flight.add(task)
    task.add_done_callback(consumer._in_flight.discard)

    await consumer.stop(timeout=2.0)

    assert finished == [True]
    assert consumer._running is False
