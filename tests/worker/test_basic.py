"""Worker comprehensive tests."""

import asyncio
import sys
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest

# Save original modules before any mocking
_original_modules = sys.modules.copy()


def setup_module(module):
    """Set up mocks before worker tests."""
    mock_modules = {
        "google": MagicMock(),
        "google.genai": MagicMock(),
        "google.genai.types": MagicMock(),
        "boto3": MagicMock(),
        "botocore": MagicMock(),
        "botocore.config": MagicMock(),
        "opentelemetry": MagicMock(),
        "opentelemetry.trace": MagicMock(),
    }

    for module_name, mock_module in mock_modules.items():
        sys.modules[module_name] = mock_module

    sys.modules["foreman"] = MagicMock()
    sys.modules["foreman.db"] = MagicMock()
    sys.modules["foreman.logging_config"] = MagicMock()
    sys.modules["foreman.logging_config.get_logger"] = MagicMock(return_value=MagicMock())
    sys.modules["foreman.logging_config.configure_logging"] = MagicMock()
    sys.modules["foreman.queue"] = MagicMock()
    sys.modules["foreman.queue.settings"] = MagicMock()
    sys.modules["foreman.telemetry"] = MagicMock()
    sys.modules["foreman.telemetry.setup_telemetry"] = MagicMock()
    sys.modules["foreman.repositories"] = MagicMock()
    sys.modules["foreman.repositories.postgres_generations_repository"] = MagicMock()
    sys.modules["foreman.schemas"] = MagicMock()
    sys.modules["foreman.schemas.generation"] = MagicMock()

    mock_genai = MagicMock()
    mock_types = MagicMock()
    sys.modules["google"].genai = mock_genai
    sys.modules["google.genai"].types = mock_types
    sys.modules["google.genai.types"].Modality = MagicMock()
    sys.modules["google.genai.types"].Part = MagicMock()

    mock_boto3 = MagicMock()
    sys.modules["boto3"].client = MagicMock(return_value=MagicMock())
    sys.modules["boto3"] = mock_boto3

    mock_otel = MagicMock()
    mock_trace = MagicMock()
    mock_otel.trace.get_tracer = MagicMock(return_value=MagicMock())
    sys.modules["opentelemetry"] = mock_otel
    sys.modules["opentelemetry.trace"] = mock_trace


def teardown_module(module):
    """Clean up mocks after worker tests."""
    sys.modules.clear()
    sys.modules.update(_original_modules)


# Now import the worker modules after mocks are set up
from worker.agent import AgentGraph, AgentResult
from worker.config import WorkerConfig, get_worker_config
from worker.consumer import GenerationJob, MalformedSQSMessageError, SQSConsumer


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


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
            model_used="gemini-3.1-flash-image",
        )
    )
    return provider


@pytest.fixture
def mock_config():
    """Mock worker config."""
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

    config = WorkerConfig()
    assert config.r2_bucket == "my-bucket"
    assert config.r2_account_id == "my-account"
    assert config.r2_endpoint == "https://my-endpoint.com"


def test_get_worker_config():
    """Test factory function."""
    config = get_worker_config()
    assert isinstance(config, WorkerConfig)


# ---------------------------------------------------------------------------
# consumer.py tests
# ---------------------------------------------------------------------------


def test_generation_job_from_message_valid():
    """Test parsing valid SQS message."""
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
    """Test agent graph returns result."""
    agent = AgentGraph()

    result = await agent.run(
        input_image_path="/tmp/input.jpg",
        prompt="make it modern",
        style_id="modern",
    )

    assert isinstance(result, AgentResult)
    assert result.output_image_url is not None
    assert result.iterations >= 1


@pytest.mark.asyncio
async def test_agent_graph_without_style():
    """Test agent graph works without style."""
    agent = AgentGraph()

    result = await agent.run(
        input_image_path="/tmp/input.jpg",
        prompt="make it modern",
    )

    assert isinstance(result, AgentResult)
    assert result.metadata is not None
