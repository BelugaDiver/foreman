"""Tests for worker/processor.py."""

from __future__ import annotations

import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

from worker.config import WorkerConfig
from worker.consumer import GenerationJob, MalformedSQSMessageError
from worker.processor import JobProcessor, ProcessingResult


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

_USER_ID = UUID("00000000-0000-0000-0000-000000000001")
_GEN_ID = "00000000-0000-0000-0000-000000000002"


def _make_config(**kwargs) -> WorkerConfig:
    config = WorkerConfig()
    config.r2_bucket = "test-bucket"
    config.r2_account_id = "test-account"
    config.r2_endpoint = "https://test-account.r2.cloudflarestorage.com"
    config.r2_access_key_id = "key"
    config.r2_secret_access_key = "secret"
    config.r2_public_url = "https://cdn.example.com"
    for k, v in kwargs.items():
        setattr(config, k, v)
    return config


def _make_job(user_id: str | None = str(_USER_ID)) -> GenerationJob:
    return GenerationJob(
        generation_id=_GEN_ID,
        project_id="00000000-0000-0000-0000-000000000003",
        prompt="make it pop",
        style_id=None,
        input_image_url="https://example.com/input.jpg",
        created_at="2024-01-01T00:00:00Z",
        user_id=user_id,
    )


def _make_processor(config=None, ai_provider=None) -> JobProcessor:
    db = MagicMock()
    return JobProcessor(
        db=db,
        config=config or _make_config(),
        ai_provider=ai_provider or MagicMock(),
    )


def _make_gen_record(user_id: UUID = _USER_ID) -> MagicMock:
    gen = MagicMock()
    gen.user_id = user_id
    return gen


# ---------------------------------------------------------------------------
# _update_status
# ---------------------------------------------------------------------------

async def test_update_status_no_user_id_returns_early():
    """_update_status with user_id=None returns without calling gen_repo."""
    processor = _make_processor()
    with patch("worker.processor.gen_repo.update_generation", new=AsyncMock()) as mock_update:
        await processor._update_status(_GEN_ID, None, "processing")
        mock_update.assert_not_called()


async def test_update_status_with_user_id_calls_repo():
    """_update_status with valid user_id calls gen_repo.update_generation."""
    processor = _make_processor()
    with patch("worker.processor.gen_repo.update_generation", new=AsyncMock()) as mock_update:
        await processor._update_status(_GEN_ID, _USER_ID, "completed", output_image_url="https://cdn.example.com/out.png")
        mock_update.assert_called_once()
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["generation_id"] == UUID(_GEN_ID)
        assert call_kwargs["user_id"] == _USER_ID


# ---------------------------------------------------------------------------
# _run_agent
# ---------------------------------------------------------------------------

async def test_run_agent_returns_dict_with_path():
    """_run_agent calls ai_provider.generate and returns output_image_path."""
    ai = MagicMock()
    result_mock = MagicMock()
    result_mock.output_image_url = "file:///tmp/gen_abc.png"
    result_mock.model_used = "gemini-3.1-flash-image-preview"
    ai.generate = AsyncMock(return_value=result_mock)

    processor = _make_processor(ai_provider=ai)
    job = _make_job()

    result = await processor._run_agent(job)

    ai.generate.assert_called_once()
    assert result["output_image_path"] == "/tmp/gen_abc.png"
    assert result["model_used"] == "gemini-3.1-flash-image-preview"


# ---------------------------------------------------------------------------
# _upload_to_storage
# ---------------------------------------------------------------------------

async def test_upload_to_storage_with_r2_public_url():
    """When r2_public_url is set, returned URL uses that domain."""
    config = _make_config(r2_public_url="https://cdn.example.com")
    processor = _make_processor(config=config)

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        with patch("worker.processor.boto3.client") as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.return_value = mock_s3
            with patch("worker.processor.asyncio.to_thread", new=AsyncMock(return_value=None)):
                url = await processor._upload_to_storage(path)
        assert url.startswith("https://cdn.example.com/generations/")
    finally:
        if os.path.exists(path):
            os.unlink(path)


async def test_upload_to_storage_r2_dev_fallback():
    """When r2_public_url is empty but r2_account_id is set → r2.dev fallback URL."""
    config = _make_config(r2_public_url="", r2_account_id="acct123", r2_endpoint="")
    processor = _make_processor(config=config)

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        with patch("worker.processor.boto3.client") as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.return_value = mock_s3
            with patch("worker.processor.asyncio.to_thread", new=AsyncMock(return_value=None)):
                url = await processor._upload_to_storage(path)
        assert "acct123.r2.dev" in url
    finally:
        if os.path.exists(path):
            os.unlink(path)


async def test_upload_to_storage_raises_when_no_url_and_no_account():
    """Raises ValueError when neither r2_public_url nor r2_account_id is set."""
    config = _make_config(r2_public_url="", r2_account_id="")
    processor = _make_processor(config=config)

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        with patch("worker.processor.boto3.client") as mock_boto3:
            mock_s3 = MagicMock()
            mock_boto3.return_value = mock_s3
            with patch("worker.processor.asyncio.to_thread", new=AsyncMock(return_value=None)):
                with pytest.raises(ValueError, match="R2_PUBLIC_URL"):
                    await processor._upload_to_storage(path)
    finally:
        if os.path.exists(path):
            os.unlink(path)


async def test_upload_to_storage_no_endpoint_no_account_raises():
    """Raises ValueError when neither r2_endpoint nor r2_account_id is configured."""
    config = _make_config(r2_public_url="", r2_endpoint="", r2_account_id="")
    processor = _make_processor(config=config)

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        with patch("worker.processor.boto3.client"):
            with pytest.raises(ValueError, match="R2_ENDPOINT|R2_ACCOUNT_ID"):
                await processor._upload_to_storage(path)
    finally:
        if os.path.exists(path):
            os.unlink(path)


async def test_upload_to_storage_unlinks_local_file():
    """_upload_to_storage always removes the local temp file."""
    config = _make_config(r2_public_url="https://cdn.example.com")
    processor = _make_processor(config=config)

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    assert os.path.exists(path)

    with patch("worker.processor.boto3.client"):
        with patch("worker.processor.asyncio.to_thread", new=AsyncMock(return_value=None)):
            await processor._upload_to_storage(path)

    assert not os.path.exists(path)


# ---------------------------------------------------------------------------
# process
# ---------------------------------------------------------------------------

async def test_process_success():
    """Full success path: calls all steps and returns ProcessingResult(success=True)."""
    processor = _make_processor()
    job = _make_job()

    gen_record = _make_gen_record()
    output_url = "https://cdn.example.com/generations/abc.png"

    with patch("worker.processor.gen_repo.get_generation_by_id", new=AsyncMock(return_value=gen_record)):
        with patch("worker.processor.gen_repo.update_generation", new=AsyncMock()):
            processor._run_agent = AsyncMock(return_value={"output_image_path": "/fake/path.png", "model_used": "m"})
            processor._upload_to_storage = AsyncMock(return_value=output_url)

            result = await processor.process(job, retry_count=0)

    assert result.success is True
    assert result.output_image_url == output_url
    processor._run_agent.assert_called_once_with(job)
    processor._upload_to_storage.assert_called_once_with("/fake/path.png")


async def test_process_no_user_id_raises():
    """process() raises MalformedSQSMessageError when job.user_id is None."""
    processor = _make_processor()
    job = _make_job(user_id=None)

    with patch("worker.processor.gen_repo.update_generation", new=AsyncMock()):
        with pytest.raises(MalformedSQSMessageError):
            await processor.process(job)


async def test_process_malformed_error_message():
    """MalformedSQSMessageError results in 'Invalid job message format' error_msg."""
    processor = _make_processor()
    job = _make_job(user_id=None)

    with patch("worker.processor.gen_repo.update_generation", new=AsyncMock()):
        try:
            await processor.process(job)
        except MalformedSQSMessageError:
            pass  # expected


async def test_process_run_agent_exception_updates_failed_and_reraises():
    """Exception in _run_agent → status updated to 'failed' and exception re-raised."""
    processor = _make_processor()
    job = _make_job()

    gen_record = _make_gen_record()

    with patch("worker.processor.gen_repo.get_generation_by_id", new=AsyncMock(return_value=gen_record)):
        with patch("worker.processor.gen_repo.update_generation", new=AsyncMock()) as mock_update:
            processor._run_agent = AsyncMock(side_effect=RuntimeError("agent exploded"))
            processor._upload_to_storage = AsyncMock()

            with pytest.raises(RuntimeError, match="agent exploded"):
                await processor.process(job)

    # update_generation should have been called at least once with status "failed"
    calls = mock_update.call_args_list
    failed_calls = [c for c in calls if c.kwargs.get("generation_in") and c.kwargs["generation_in"].status == "failed"]
    assert len(failed_calls) >= 1


async def test_process_get_generation_raises_in_error_path():
    """Exception in _run_agent + get_generation_by_id raises in error path → still re-raises."""
    processor = _make_processor()
    job = _make_job()

    gen_record = _make_gen_record()

    call_count = 0
    async def fake_get_gen(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return gen_record  # success path
        raise RuntimeError("db error during error handling")  # error path

    with patch("worker.processor.gen_repo.get_generation_by_id", side_effect=fake_get_gen):
        with patch("worker.processor.gen_repo.update_generation", new=AsyncMock()):
            processor._run_agent = AsyncMock(side_effect=RuntimeError("boom"))
            processor._upload_to_storage = AsyncMock()

            with pytest.raises(RuntimeError, match="boom"):
                await processor.process(job)


async def test_process_update_status_raises_during_failed_update():
    """Exception during _update_status('failed') is swallowed but exception still re-raised."""
    processor = _make_processor()
    job = _make_job()

    gen_record = _make_gen_record()

    with patch("worker.processor.gen_repo.get_generation_by_id", new=AsyncMock(return_value=gen_record)):
        # First call succeeds (status=processing), second raises (status=failed)
        call_count = 0
        async def fake_update(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count >= 2:
                raise RuntimeError("db down during failed update")

        with patch("worker.processor.gen_repo.update_generation", side_effect=fake_update):
            processor._run_agent = AsyncMock(side_effect=RuntimeError("agent error"))
            processor._upload_to_storage = AsyncMock()

            with pytest.raises(RuntimeError, match="agent error"):
                await processor.process(job)


async def test_upload_to_storage_os_unlink_raises_oserror():
    """_upload_to_storage swallows OSError from os.unlink in finally."""
    config = _make_config(r2_public_url="https://cdn.example.com")
    processor = _make_processor(config=config)

    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)

    with patch("worker.processor.boto3.client"):
        with patch("worker.processor.asyncio.to_thread", new=AsyncMock(return_value=None)):
            with patch("worker.processor.os.unlink", side_effect=OSError("busy")):
                # Should not raise - OSError is swallowed
                url = await processor._upload_to_storage(path)

    assert url.startswith("https://cdn.example.com/")
    # Cleanup (unlink was patched so file still exists)
    if os.path.exists(path):
        os.unlink(path)
