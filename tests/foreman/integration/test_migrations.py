"""Integration migration checks for feature-specific schema changes."""

from __future__ import annotations

import asyncpg
import pytest

from tests.foreman.integration.conftest import get_db_dsn


@pytest.mark.asyncio
async def test_generations_table_has_generated_image_description_column():
    """Migration chain should include generated_image_description on generations."""
    conn = await asyncpg.connect(get_db_dsn())
    try:
        row = await conn.fetchrow(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'generations'
              AND column_name = 'generated_image_description'
            """
        )
    finally:
        await conn.close()

    assert row is not None
