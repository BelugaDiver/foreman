"""Basic worker tests."""



def test_worker_config():
    """Test config loads from env."""
    from worker.config import WorkerConfig

    config = WorkerConfig()
    assert config.concurrency >= 1
    assert config.max_retries >= 1


def test_consumer_job_parsing():
    """Test parsing SQS message."""
    from worker.consumer import GenerationJob

    body = {
        "generation_id": "abc-123",
        "project_id": "proj-456",
        "prompt": "make it modern",
        "input_image_url": "https://example.com/input.jpg",
        "created_at": "2026-04-07T12:00:00Z",
    }

    job = GenerationJob.from_message(body)
    assert job.generation_id == "abc-123"
    assert job.prompt == "make it modern"
