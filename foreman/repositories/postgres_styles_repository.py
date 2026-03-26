"""Database CRUD operations for the Style resource."""

import uuid
from typing import Optional

from foreman.db import Database, sql
from foreman.logging_config import get_logger
from foreman.models.style import Style

logger = get_logger("foreman.repositories.styles")


async def list_styles(
    db: Database,
    limit: int = 20,
    offset: int = 0,
) -> list[Style]:
    """Return a paginated list of all styles."""
    logger.debug("Listing styles", extra={"limit": limit, "offset": offset})
    stmt = sql(
        """
        SELECT * FROM styles
        ORDER BY name ASC
        LIMIT $1 OFFSET $2
        """,
        limit,
        offset,
    )
    records = await db.fetch(stmt)
    return [Style(**dict(r)) for r in records]


async def get_style_by_id(
    db: Database,
    style_id: uuid.UUID,
) -> Optional[Style]:
    """Retrieve a single style by ID."""
    logger.debug("Fetching style", extra={"style_id": str(style_id)})
    stmt = sql(
        "SELECT * FROM styles WHERE id=$1",
        style_id,
    )
    record = await db.fetchrow(stmt)
    if not record:
        return None
    return Style(**dict(record))
