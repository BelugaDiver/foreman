"""Database CRUD operations for the Generation resource."""

import json
import uuid

from foreman.db import Database, sql
from foreman.logging_config import get_logger
from foreman.models.generation import Generation
from foreman.schemas.generation import GenerationCreate, GenerationUpdate

logger = get_logger("foreman.repositories.generations")

# Fields callers are permitted to update. Guards against column-name injection
# in the dynamically built UPDATE query.
ALLOWED_UPDATE_FIELDS: frozenset[str] = frozenset(
    {"status", "output_image_url", "error_message", "processing_time_ms", "metadata"}
)


def _parse_generation_record(record: dict) -> Generation:
    """Convert database record to Generation model, parsing JSON fields."""
    record_dict = dict(record)
    if "metadata" in record_dict and isinstance(record_dict.get("metadata"), str):
        record_dict["metadata"] = json.loads(record_dict["metadata"])
    return Generation(**record_dict)


async def create_generation(
    db: Database,
    project_id: uuid.UUID,
    input_image_url: str,
    generation_in: GenerationCreate,
) -> Generation:
    """Insert a new generation row and return it."""
    logger.info("Creating generation", extra={"project_id": str(project_id)})
    attempt = generation_in.attempt if generation_in.attempt is not None else 1
    stmt = sql(
        """
        INSERT INTO generations (
            project_id, parent_id, prompt, style_id, model_used, input_image_url, attempt
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        project_id,
        generation_in.parent_id,
        generation_in.prompt,
        generation_in.style_id,
        generation_in.model_used,
        input_image_url,
        attempt,
    )
    record = await db.fetchrow(stmt)
    if not record:
        raise RuntimeError("Failed to create generation record")
    return _parse_generation_record(record)


async def get_generation_by_id(
    db: Database,
    generation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Generation | None:
    """Retrieve a generation by ID, scoped to the owning user."""
    logger.debug(
        "Fetching generation", extra={"generation_id": str(generation_id), "user_id": str(user_id)}
    )
    stmt = sql(
        """
        SELECT g.*
        FROM generations g
        JOIN projects p ON g.project_id = p.id
        WHERE g.id=$1 AND p.user_id=$2
        """,
        generation_id,
        user_id,
    )
    record = await db.fetchrow(stmt)
    if not record:
        return None
    return _parse_generation_record(record)


async def list_generations_by_project(
    db: Database,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
) -> list[Generation]:
    """Return a paginated list of generations for a project owned by *user_id*."""
    stmt = sql(
        """
        SELECT g.*
        FROM generations g
        JOIN projects p ON g.project_id = p.id
        WHERE g.project_id=$1 AND p.user_id=$2
        ORDER BY g.created_at DESC
        LIMIT $3 OFFSET $4
        """,
        project_id,
        user_id,
        limit,
        offset,
    )
    records = await db.fetch(stmt)
    return [_parse_generation_record(record) for record in records]


async def list_generations(
    db: Database,
    user_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
) -> list[Generation]:
    """Return a paginated list of all generations owned by *user_id*."""
    stmt = sql(
        """
        SELECT g.*
        FROM generations g
        JOIN projects p ON g.project_id = p.id
        WHERE p.user_id=$1
        ORDER BY g.created_at DESC
        LIMIT $2 OFFSET $3
        """,
        user_id,
        limit,
        offset,
    )
    records = await db.fetch(stmt)
    return [_parse_generation_record(record) for record in records]


async def update_generation(
    db: Database,
    generation_id: uuid.UUID,
    user_id: uuid.UUID,
    generation_in: GenerationUpdate,
) -> Generation | None:
    """Partially update a generation. Returns None if missing or not owned."""
    update_data = {
        key: value
        for key, value in generation_in.model_dump(exclude_unset=True).items()
        if key in ALLOWED_UPDATE_FIELDS
    }

    if not update_data:
        return await get_generation_by_id(db, generation_id, user_id)

    logger.debug("Updating generation", extra={"generation_id": str(generation_id)})

    set_clauses: list[str] = []
    params: list = []

    for idx, (key, value) in enumerate(update_data.items(), start=1):
        set_clauses.append(f"{key}=${idx}")
        params.append(value)

    # generation_id and user_id are the final two parameters.
    params.append(generation_id)
    params.append(user_id)
    where_generation_id = len(params) - 1
    where_user_id = len(params)

    query = f"""
        UPDATE generations AS g
        SET {", ".join(set_clauses)}, updated_at=CURRENT_TIMESTAMP
        FROM projects AS p
        WHERE g.id=${where_generation_id}
          AND g.project_id=p.id
          AND p.user_id=${where_user_id}
        RETURNING g.*
    """

    stmt = sql(query, *params)
    record = await db.fetchrow(stmt)
    if not record:
        return None
    return _parse_generation_record(record)


async def delete_generation(
    db: Database,
    generation_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Hard-delete a generation row. Returns True if a row was deleted."""
    logger.info("Deleting generation", extra={"generation_id": str(generation_id)})
    stmt = sql(
        """
        DELETE FROM generations AS g
        USING projects AS p
        WHERE g.id=$1
          AND g.project_id=p.id
          AND p.user_id=$2
        RETURNING g.id
        """,
        generation_id,
        user_id,
    )
    record = await db.fetchrow(stmt)
    return bool(record)
