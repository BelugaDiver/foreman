"""Tests for worker/main.py health and ready endpoints."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from starlette.testclient import TestClient

import worker.main as worker_main
from worker.main import health_app


@pytest.fixture(autouse=True)
def reset_globals():
    """Restore module-level globals after each test."""
    original_db = worker_main._db_instance
    original_consumer = worker_main._consumer_instance
    yield
    worker_main._db_instance = original_db
    worker_main._consumer_instance = original_consumer


# ---------------------------------------------------------------------------
# /health
# ---------------------------------------------------------------------------

def test_health_returns_ok():
    """GET /health → 200 with {"status": "ok"}."""
    client = TestClient(health_app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# /ready – not initialized states
# ---------------------------------------------------------------------------

def test_ready_no_db_no_consumer():
    """GET /ready with no db and no consumer → 503."""
    worker_main._db_instance = None
    worker_main._consumer_instance = None

    client = TestClient(health_app)
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not ready"
    assert body["database"] == "not initialized"
    assert body["consumer"] == "not initialized"


def test_ready_no_db_with_consumer():
    """GET /ready with consumer set but no db → 503."""
    worker_main._db_instance = None
    mock_consumer = MagicMock()
    mock_consumer.is_ready.return_value = True
    worker_main._consumer_instance = mock_consumer

    client = TestClient(health_app)
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["database"] == "not initialized"


def test_ready_with_db_no_consumer():
    """GET /ready with db set but no consumer → 503."""
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock())
    worker_main._db_instance = mock_db
    worker_main._consumer_instance = None

    client = TestClient(health_app)
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["consumer"] == "not initialized"


# ---------------------------------------------------------------------------
# /ready – healthy
# ---------------------------------------------------------------------------

def test_ready_all_healthy():
    """GET /ready with db connected and consumer running → 200."""
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock())
    worker_main._db_instance = mock_db

    mock_consumer = MagicMock()
    mock_consumer.is_ready.return_value = True
    worker_main._consumer_instance = mock_consumer

    client = TestClient(health_app)
    response = client.get("/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["database"] == "connected"
    assert body["consumer"] == "running"


# ---------------------------------------------------------------------------
# /ready – unhealthy sub-states
# ---------------------------------------------------------------------------

def test_ready_db_execute_fails():
    """GET /ready when db.execute raises → 503 with database=disconnected."""
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(side_effect=Exception("db down"))
    worker_main._db_instance = mock_db

    mock_consumer = MagicMock()
    mock_consumer.is_ready.return_value = True
    worker_main._consumer_instance = mock_consumer

    client = TestClient(health_app)
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["database"] == "disconnected"


def test_ready_consumer_not_ready():
    """GET /ready when consumer.is_ready() returns False → 503."""
    mock_db = MagicMock()
    mock_db.execute = AsyncMock(return_value=MagicMock())
    worker_main._db_instance = mock_db

    mock_consumer = MagicMock()
    mock_consumer.is_ready.return_value = False
    worker_main._consumer_instance = mock_consumer

    client = TestClient(health_app)
    response = client.get("/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["consumer"] == "stopped"
