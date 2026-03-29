# SQS Generation Queue Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add SQS queue integration to publish generation requests when created, enabling background workers to process them asynchronously.

**Architecture:** When a generation is created via API, the endpoint will publish a message to SQS. A separate worker (not part of this plan) will consume from the queue, process the generation, and update the database.

**Tech Stack:** FastAPI, asyncpg, boto3, aiobotocore, Pydantic

---

## File Structure

### New Files
- `foreman/queue/__init__.py` - Queue module exports
- `foreman/queue/protocol.py` - QueueProtocol abstract class
- `foreman/queue/sqs_queue.py` - SQS implementation
- `foreman/queue/settings.py` - SQS configuration dataclass
- `foreman/queue/factory.py` - Queue factory function
- `tests/test_queue/test_sqs_queue.py` - Unit tests for SQS queue

### Modified Files
- `foreman/api/v1/endpoints/projects.py` - Inject queue and publish on generation creation
- `.env.foreman.example` - Add SQS environment variables

---

## Task 1: Create SQS Settings

**Files:**
- Create: `foreman/queue/settings.py`
- Test: N/A (simple dataclass)

- [ ] **Step 1: Create the SQS settings file**

```python
"""SQS queue configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class SQSSettings:
    """AWS SQS configuration."""

    queue_url: Optional[str] = None
    region: str = "us-east-1"
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    max_retries: int = 3
    visibility_timeout_seconds: int = 300

    @classmethod
    def from_env(cls) -> SQSSettings:
        return cls(
            queue_url=os.getenv("SQS_QUEUE_URL"),
            region=os.getenv("AWS_REGION", "us-east-1"),
            access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
            max_retries=int(os.getenv("SQS_MAX_RETRIES", "3")),
            visibility_timeout_seconds=int(os.getenv("SQS_VISIBILITY_TIMEOUT", "300")),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.queue_url)
```

- [ ] **Step 2: Commit**

```bash
git add foreman/queue/settings.py
git commit -m "feat: add SQS settings configuration"
```

---

## Task 2: Create Queue Protocol

**Files:**
- Create: `foreman/queue/protocol.py`
- Test: N/A (abstract interface)

- [ ] **Step 1: Create the queue protocol**

```python
"""Queue protocol for abstracting queue implementations."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class QueueMessage:
    """Represents a message to be sent to the queue."""

    body: dict[str, Any]
    message_attributes: dict[str, Any] | None = None


class QueueProtocol(ABC):
    """Abstract queue interface."""

    @abstractmethod
    async def publish(self, message: QueueMessage) -> str:
        """Publish a message to the queue.
        
        Args:
            message: The message to publish
            
        Returns:
            The message ID from the queue service
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """Close any connections."""
        pass
```

- [ ] **Step 2: Commit**

```bash
git add foreman/queue/protocol.py
git commit -m "feat: add queue protocol interface"
```

---

## Task 3: Create SQS Implementation

**Files:**
- Create: `foreman/queue/sqs_queue.py`
- Modify: `foreman/queue/__init__.py`
- Test: `tests/test_queue/test_sqs_queue.py`

- [ ] **Step 1: Write the failing test**

```python
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
        
        with patch.object(sqs_queue._client, "send_message", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"MessageId": "test-message-id"}
            
            result = await sqs_queue.publish(message)
            
            mock_send.assert_called_once()
            call_kwargs = mock_send.call_args.kwargs
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
        
        with patch.object(sqs_queue._client, "send_message", new_callable=AsyncMock) as mock_send:
            mock_send.return_value = {"MessageId": "test-id"}
            
            await sqs_queue.publish(message)
            
            call_kwargs = mock_send.call_args.kwargs
            assert "MessageAttributes" in call_kwargs
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_queue/test_sqs_queue.py -v`
Expected: FAIL (import error - module doesn't exist)

- [ ] **Step 3: Create SQS queue implementation**

```python
"""SQS queue implementation."""

from __future__ import annotations

import json
import logging
from typing import Any

import aiobotocore.session

from foreman.logging_config import get_logger
from foreman.queue.protocol import QueueMessage, QueueProtocol
from foreman.queue.settings import SQSSettings

logger = get_logger("foreman.queue.sqs")


class SQSQueue(QueueProtocol):
    """AWS SQS queue implementation."""

    def __init__(self, settings: SQSSettings) -> None:
        self._settings = settings
        self._session = aiobotocore.session.get_session()
        self._client = None

    async def _get_client(self):
        """Get or create the SQS client."""
        if self._client is None:
            ctx = self._session.create_client(
                "sqs",
                region_name=self._settings.region,
                aws_access_key_id=self._settings.access_key_id,
                aws_secret_access_key=self._settings.secret_access_key,
            )
            self._client = await ctx.__aenter__()
        return self._client

    async def publish(self, message: QueueMessage) -> str:
        """Publish a message to the SQS queue."""
        client = await self._get_client()
        
        publish_kwargs: dict[str, Any] = {
            "QueueUrl": self._settings.queue_url,
            "MessageBody": json.dumps(message.body),
        }
        
        if message.message_attributes:
            publish_kwargs["MessageAttributes"] = {
                key: {"StringValue": value, "DataType": "String"}
                for key, value in message.message_attributes.items()
            }
        
        try:
            logger.debug(
                "Publishing message to SQS",
                extra={"queue_url": self._settings.queue_url},
            )
            
            response = await client.send_message(**publish_kwargs)
            message_id = response["MessageId"]
            
            logger.info(
                "Message published to SQS",
                extra={
                    "message_id": message_id,
                    "queue_url": self._settings.queue_url,
                    "generation_id": message.body.get("generation_id"),
                },
            )
            
            return message_id
        except Exception as exc:
            logger.exception(
                "Failed to publish message to SQS",
                extra={
                    "queue_url": self._settings.queue_url,
                    "generation_id": message.body.get("generation_id"),
                },
            )
            raise

    async def close(self) -> None:
        """Close the SQS client."""
        if self._client is not None:
            await self._client.close()
            self._client = None
```

- [ ] **Step 4: Create the module init**

```python
"""Queue module for async message publishing."""

from foreman.queue.protocol import QueueMessage, QueueProtocol
from foreman.queue.sqs_queue import SQSQueue
from foreman.queue.settings import SQSSettings

__all__ = ["QueueMessage", "QueueProtocol", "SQSQueue", "SQSSettings"]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest tests/test_queue/test_sqs_queue.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add foreman/queue/ tests/test_queue/
git commit -m "feat: add SQS queue implementation"
```

---

## Task 4: Create Queue Factory

**Files:**
- Create: `foreman/queue/factory.py`
- Test: N/A (simple factory)

- [ ] **Step 1: Create the queue factory**

```python
"""Queue factory for creating queue backends."""

from __future__ import annotations

import os
from functools import lru_cache

from foreman.logging_config import get_logger
from foreman.queue.protocol import QueueProtocol
from foreman.queue.sqs_queue import SQSQueue
from foreman.queue.settings import SQSSettings

logger = get_logger("foreman.queue.factory")


@lru_cache(maxsize=1)
def get_queue() -> QueueProtocol:
    """Create a queue backend based on QUEUE_PROVIDER env var."""
    provider = os.getenv("QUEUE_PROVIDER", "sqs").lower()
    logger.debug("Initializing queue", extra={"provider": provider})

    if provider == "sqs":
        settings = SQSSettings.from_env()
        if not settings.is_configured:
            raise ValueError("SQS_QUEUE_URL is not configured")
        queue = SQSQueue(settings)
        logger.info("SQS queue initialized", extra={"queue_url": settings.queue_url})
        return queue

    raise ValueError(f"Unknown QUEUE_PROVIDER: {provider}")
```

- [ ] **Step 2: Update module init**

Add to `foreman/queue/__init__.py`:
```python
from foreman.queue.factory import get_queue
```

- [ ] **Step 3: Commit**

```bash
git add foreman/queue/
git commit -m "feat: add queue factory"
```

---

## Task 5: Integrate Queue into Generation Creation

**Files:**
- Modify: `foreman/api/v1/endpoints/projects.py:69-119`
- Test: `tests/test_projects.py` (add integration test)

- [ ] **Step 1: Write the failing test**

Add to `tests/test_projects.py`:

```python
@pytest.mark.asyncio
async def test_create_generation_publishes_to_queue(mock_dependencies, client, headers_a, monkeypatch):
    """Creating a generation should publish a message to SQS."""
    from foreman.api.v1.endpoints import projects as projects_module
    from foreman.queue.protocol import QueueMessage
    
    # Set up project with image
    project_id = uuid.uuid4()
    projects_db[str(project_id)] = {
        "id": str(project_id),
        "user_id": str(USER_A_ID),
        "name": "Test Project",
        "original_image_url": "https://example.com/room.jpg",
        "room_analysis": None,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": None,
    }
    
    # Mock queue
    mock_queue = AsyncMock()
    mock_queue.publish.return_value = "test-message-id"
    monkeypatch.setattr("foreman.api.v1.endpoints.projects.get_queue", lambda: mock_queue)
    
    # Create generation
    resp = client.post(
        f"/v1/projects/{project_id}/generations",
        headers=headers_a,
        json={"prompt": "make it modern", "style_id": str(uuid.uuid4())},
    )
    
    assert resp.status_code == 202
    mock_queue.publish.assert_called_once()
    call_args = mock_queue.publish.call_args[0][0]
    assert isinstance(call_args, QueueMessage)
    assert call_args.body["prompt"] == "make it modern"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_projects.py::test_create_generation_publishes_to_queue -v`
Expected: FAIL (get_queue not imported)

- [ ] **Step 3: Add queue publishing to generation endpoint**

Modify `foreman/api/v1/endpoints/projects.py`:

```python
from foreman.queue.factory import get_queue
from foreman.queue.protocol import QueueMessage
```

Then update the `create_generation` endpoint (around line 107):

```python
        generation = await gen_repo.create_generation(
            db=db,
            project_id=project_id,
            input_image_url=input_image_url,
            generation_in=generation_in,
        )
        
        # Publish to SQS queue for background processing
        try:
            queue = get_queue()
            message = QueueMessage(
                body={
                    "generation_id": str(generation.id),
                    "project_id": str(project_id),
                    "prompt": generation.prompt,
                    "style_id": str(generation.style_id) if generation.style_id else None,
                    "input_image_url": generation.input_image_url,
                    "created_at": generation.created_at.isoformat(),
                },
                message_attributes={
                    "generation_id": str(generation.id),
                    "user_id": str(current_user.id),
                },
            )
            await queue.publish(message)
            logger.info(
                "Generation queued for processing",
                extra={"generation_id": str(generation.id)},
            )
        except Exception as exc:
            # Log but don't fail - generation is created, can be retried manually
            logger.exception(
                "Failed to queue generation for processing",
                extra={"generation_id": str(generation.id)},
            )
        
        response.headers["Location"] = f"/v1/generations/{generation.id}"
        return generation
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_projects.py::test_create_generation_publishes_to_queue -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add foreman/api/v1/endpoints/projects.py tests/test_projects.py
git commit -m "feat: integrate SQS queue into generation creation"
```

---

## Task 6: Update Environment Example

**Files:**
- Modify: `.env.foreman.example`

- [ ] **Step 1: Add SQS environment variables**

Append to `.env.foreman.example`:

```bash
# AWS SQS Queue (for background generation processing)
QUEUE_PROVIDER=sqs
SQS_QUEUE_URL=https://sqs.us-east-1.amazonaws.com/123456789/foreman-generations
AWS_REGION=us-east-1
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
SQS_MAX_RETRIES=3
SQS_VISIBILITY_TIMEOUT=300
```

- [ ] **Step 2: Commit**

```bash
git add .env.foreman.example
git commit -m "docs: add SQS environment variables to example"
```

---

## Summary

This plan adds:
1. **SQS Settings** - Configuration dataclass
2. **Queue Protocol** - Abstract interface for queue implementations
3. **SQS Implementation** - boto3-based SQS client with async support
4. **Queue Factory** - Factory function to create queue backends
5. **API Integration** - Publish to SQS when generation is created
6. **Tests** - Unit tests for SQS queue, integration test for API

After implementation:
- Creating a generation publishes to SQS
- A separate worker (not in scope) would consume from SQS
- Worker processes generation, updates status in DB

---

## Plan complete and saved to `docs/superpowers/plans/2026-03-29-sqs-generation-queue.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?
