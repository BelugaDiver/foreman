"""Worker comprehensive tests."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from worker.consumer import GenerationJob


@pytest.fixture
def mock_db():
    """Mock database connection."""
    db = MagicMock()
    db.execute = AsyncMock(return_value=MagicMock())
    return db


@pytest.fixture
def mock_ai_provider():
    """Mock AI provider."""
    provider = MagicMock()
    provider.generate = AsyncMock(
        return_value=MagicMock(
            output_image_url="file:///tmp/test.png",
            model_used="gemini-3.1-flash-image-preview",
        )
    )
    return provider


@pytest.fixture
def mock_config():
    """Mock worker config."""
    from worker.config import WorkerConfig

    config = WorkerConfig()
    config.concurrency = 1
    config.max_retries = 3
    config.r2_bucket = "test-bucket"
    config.r2_account_id = "test-account"
    config.r2_endpoint = ""
    config.r2_access_key_id = "test-key"
    config.r2_secret_access_key = "test-secret"
    return config


@pytest.fixture
def sample_job():
    """Sample generation job."""
    return GenerationJob(
        generation_id="gen-123",
        project_id="proj-456",
        prompt="make it modern",
        style_id="modern",
        input_image_url="https://example.com/input.jpg",
        created_at="2026-04-07T12:00:00Z",
        user_id="user-123",
        retry_count=0,
    )


# ---------------------------------------------------------------------------
# config.py tests
# ---------------------------------------------------------------------------


def test_worker_config_defaults():
    """Test config has sensible defaults."""
    from worker.config import WorkerConfig

    config = WorkerConfig()
    assert config.concurrency == 1
    assert config.max_retries == 3
    assert config.poll_interval == 10
    assert config.visibility_timeout == 300


def test_worker_config_from_env(monkeypatch):
    """Test config loads from environment variables."""
    monkeypatch.setenv("WORKER_CONCURRENCY", "5")
    monkeypatch.setenv("WORKER_MAX_RETRIES", "10")
    monkeypatch.setenv("GOOGLE_PROJECT_ID", "test-project")
    monkeypatch.setenv("GEMINI_IMAGE_MODEL", "gemini-2.0-flash")

    from worker.config import WorkerConfig

    config = WorkerConfig()
    assert config.concurrency == 5
    assert config.max_retries == 10
    assert config.google_project_id == "test-project"
    assert config.gemini_image_model == "gemini-2.0-flash"


def test_worker_config_r2_settings(monkeypatch):
    """Test R2 configuration."""
    monkeypatch.setenv("R2_BUCKET", "my-bucket")
    monkeypatch.setenv("R2_ACCOUNT_ID", "my-account")
    monkeypatch.setenv("R2_ENDPOINT", "https://my-endpoint.com")

    from worker.config import WorkerConfig

    config = WorkerConfig()
    assert config.r2_bucket == "my-bucket"
    assert config.r2_account_id == "my-account"
    assert config.r2_endpoint == "https://my-endpoint.com"


def test_get_worker_config():
    """Test factory function."""
    from worker.config import get_worker_config

    config = get_worker_config()
    assert isinstance(config, get_worker_config().__class__)


# ---------------------------------------------------------------------------
# consumer.py tests
# ---------------------------------------------------------------------------


def test_generation_job_from_message_valid():
    """Test parsing valid SQS message."""
    from worker.consumer import GenerationJob

    body = {
        "generation_id": "gen-123",
        "project_id": "proj-456",
        "prompt": "make it modern",
        "input_image_url": "https://example.com/input.jpg",
        "created_at": "2026-04-07T12:00:00Z",
    }
    message_attrs = {
        "user_id": {"StringValue": "user-123", "DataType": "String"},
    }

    job = GenerationJob.from_message(body, message_attrs)
    assert job.generation_id == "gen-123"
    assert job.project_id == "proj-456"
    assert job.prompt == "make it modern"
    assert job.style_id is None
    assert job.user_id == "user-123"


def test_generation_job_from_message_with_optional_fields():
    """Test parsing with optional fields."""
    from worker.consumer import GenerationJob

    body = {
        "generation_id": "gen-123",
        "project_id": "proj-456",
        "prompt": "make it modern",
        "style_id": "modern",
        "input_image_url": "https://example.com/input.jpg",
        "created_at": "2026-04-07T12:00:00Z",
        "retry_count": 2,
    }
    message_attrs = {
        "user_id": {"StringValue": "user-456", "DataType": "String"},
    }

    job = GenerationJob.from_message(body, message_attrs)
    assert job.style_id == "modern"
    assert job.retry_count == 2
    assert job.user_id == "user-456"


def test_generation_job_from_message_no_user_id():
    """Test parsing without message attributes."""
    from worker.consumer import GenerationJob

    body = {
        "generation_id": "gen-123",
        "project_id": "proj-456",
        "prompt": "make it modern",
        "input_image_url": "https://example.com/input.jpg",
        "created_at": "2026-04-07T12:00:00Z",
    }

    job = GenerationJob.from_message(body)
    assert job.user_id is None


def test_generation_job_from_message_missing_required():
    """Test parsing with missing required fields raises error."""
    from worker.consumer import GenerationJob, MalformedSQSMessageError

    body = {
        "generation_id": "gen-123",
        "prompt": "make it modern",
    }
    message_attrs = {
        "user_id": {"StringValue": "user-123", "DataType": "String"},
    }

    with pytest.raises(MalformedSQSMessageError) as excinfo:
        GenerationJob.from_message(body, message_attrs)

    assert "project_id" in str(excinfo.value)
    assert "input_image_url" in str(excinfo.value)
    assert "created_at" in str(excinfo.value)


def test_generation_job_from_message_empty_string():
    """Test empty string is treated as missing."""
    from worker.consumer import GenerationJob, MalformedSQSMessageError

    body = {
        "generation_id": "gen-123",
        "project_id": "",
        "prompt": "make it modern",
        "input_image_url": "https://example.com/input.jpg",
        "created_at": "2026-04-07T12:00:00Z",
    }

    with pytest.raises(MalformedSQSMessageError):
        GenerationJob.from_message(body)


@pytest.mark.asyncio
async def test_sqs_consumer_initialization():
    """Test SQS consumer initializes correctly."""
    from worker.consumer import SQSConsumer

    process_fn = AsyncMock()
    consumer = SQSConsumer(
        queue_url="https://sqs.test.com/queue",
        process_fn=process_fn,
        concurrency=2,
        max_retries=5,
    )

    assert consumer.queue_url == "https://sqs.test.com/queue"
    assert consumer.process_fn == process_fn
    assert consumer.concurrency == 2
    assert consumer.max_retries == 5
    assert consumer._running is False
    assert consumer.is_ready() is False


@pytest.mark.asyncio
async def test_sqs_consumer_start_stop():
    """Test consumer can be started and stopped."""
    from worker.consumer import SQSConsumer

    process_fn = AsyncMock()
    consumer = SQSConsumer(
        queue_url="https://sqs.test.com/queue",
        process_fn=process_fn,
        concurrency=1,
        max_retries=3,
    )

    task = asyncio.create_task(consumer.start())
    await asyncio.sleep(0.1)

    assert consumer.is_ready() is True

    await consumer.stop(timeout=1.0)
    await task

    assert consumer.is_ready() is False


@pytest.mark.asyncio
async def test_sqs_consumer_handles_gracefully():
    """Test consumer handles exceptions in loop."""
    from worker.consumer import SQSConsumer

    process_fn = AsyncMock()
    consumer = SQSConsumer(
        queue_url="https://sqs.test.com/queue",
        process_fn=process_fn,
        concurrency=1,
        max_retries=3,
    )

    task = asyncio.create_task(consumer.start())
    await asyncio.sleep(0.05)
    await consumer.stop(timeout=1.0)
    await task


# ---------------------------------------------------------------------------
# agent.py tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_graph_run():
    """Test agent graph raises NotImplementedError."""
    from worker.agent import AgentGraph

    agent = AgentGraph()

    with pytest.raises(NotImplementedError, match="AgentGraph.run\\(\\) is not yet implemented"):
        await agent.run(
            input_image_path="/tmp/input.jpg",
            prompt="make it modern",
            style_id="modern",
        )


@pytest.mark.asyncio
async def test_agent_graph_without_style():
    """Test agent graph raises NotImplementedError without style."""
    from worker.agent import AgentGraph

    agent = AgentGraph()

    with pytest.raises(NotImplementedError, match="AgentGraph.run\\(\\) is not yet implemented"):
        await agent.run(
            input_image_path="/tmp/input.jpg",
            prompt="make it modern",
        )
