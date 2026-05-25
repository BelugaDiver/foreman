"""Integration tests for generation lifecycle/idempotent redelivery behavior."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock

import asyncpg
import pytest

from tests.foreman.integration.conftest import get_db_dsn
from worker.consumer import GenerationJob
from worker.processor import JobProcessor


class _DirectDb:
    """Small asyncpg-backed DB shim for repository compatibility in tests."""

    async def fetchrow(self, statement):
        conn = await asyncpg.connect(get_db_dsn())
        try:
            return await conn.fetchrow(statement.text, *statement.params)
        finally:
            await conn.close()

    async def fetch(self, statement):
        conn = await asyncpg.connect(get_db_dsn())
        try:
            return await conn.fetch(statement.text, *statement.params)
        finally:
            await conn.close()

    async def execute(self, statement):
        conn = await asyncpg.connect(get_db_dsn())
        try:
            return await conn.execute(statement.text, *statement.params)
        finally:
            await conn.close()


@pytest.mark.asyncio
async def test_terminal_redelivery_is_idempotent_noop():
    """Completed generation redelivery should no-op and avoid provider execution."""
    conn = await asyncpg.connect(get_db_dsn())
    try:
        user_id = uuid.uuid4()
        project_id = uuid.uuid4()
        generation_id = uuid.uuid4()

        await conn.execute(
            "INSERT INTO users (id, email, full_name) VALUES ($1, $2, $3)",
            user_id,
            f"user-{user_id.hex[:6]}@example.com",
            "Integration User",
        )
        await conn.execute(
            "INSERT INTO projects (id, user_id, name, original_image_url) VALUES ($1, $2, $3, $4)",
            project_id,
            user_id,
            "Integration Project",
            "https://example.com/original.jpg",
        )
        await conn.execute(
            """
            INSERT INTO generations (
                id, project_id, status, prompt, input_image_url, output_image_url
            )
            VALUES ($1, $2, 'completed', $3, $4, $5)
            """,
            generation_id,
            project_id,
            "make it warm",
            "https://example.com/input.jpg",
            "https://cdn.example.com/existing.png",
        )
    finally:
        await conn.close()

    ai_provider = MagicMock()
    ai_provider.generate = AsyncMock(side_effect=AssertionError("provider should not run"))
    storage = MagicMock()
    storage.upload_file = AsyncMock()
    storage.get_download_url = AsyncMock()

    config = MagicMock()
    config.runtime_session_prefix = "proj"

    processor = JobProcessor(_DirectDb(), config, ai_provider, storage)

    result = await processor.process(
        GenerationJob(
            generation_id=str(generation_id),
            project_id=str(project_id),
            prompt="make it warm",
            style_id=None,
            input_image_url="https://example.com/input.jpg",
            created_at="2026-05-23T00:00:00Z",
            user_id=str(user_id),
            retry_count=1,
        ),
        retry_count=1,
    )

    assert result.success is True
    assert result.idempotent_noop is True
    assert result.output_image_url == "https://cdn.example.com/existing.png"
