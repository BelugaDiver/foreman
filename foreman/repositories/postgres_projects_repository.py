"""Database CRUD operations for the Project resource."""

import json
import uuid

from foreman.db import Database, sql
from foreman.logging_config import get_logger
from foreman.models.project import Project
from foreman.schemas.project import ProjectCreate, ProjectUpdate

logger = get_logger("foreman.repositories.projects")

# Fields callers are permitted to update. Guards against column-name injection
# in the dynamically built UPDATE query.
ALLOWED_UPDATE_FIELDS: frozenset[str] = frozenset({"name", "original_image_url", "room_analysis"})


async def list_projects(
    db: Database,
    user_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
) -> list[Project]:
    """Return a paginated list of projects owned by *user_id*."""
    logger.debug(
        "Listing projects", extra={"user_id": str(user_id), "limit": limit, "offset": offset}
    )
    stmt = sql(
        """
        SELECT * FROM projects
        WHERE user_id=$1
        ORDER BY created_at DESC
        LIMIT $2 OFFSET $3
        """,
        user_id,
        limit,
        offset,
    )
    records = await db.fetch(stmt)
    return [Project(**dict(r)) for r in records]


async def get_project_by_id(
    db: Database,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Project | None:
    """Retrieve a single project by ID scoped to the owning user."""
    logger.debug("Fetching project", extra={"project_id": str(project_id), "user_id": str(user_id)})
    stmt = sql(
        "SELECT * FROM projects WHERE id=$1 AND user_id=$2",
        project_id,
        user_id,
    )
    record = await db.fetchrow(stmt)
    if not record:
        return None
    return Project(**dict(record))


async def create_project(
    db: Database,
    user_id: uuid.UUID,
    project_in: ProjectCreate,
) -> Project:
    """Insert a new project row and return it."""
    logger.info(
        "Creating project", extra={"user_id": str(user_id), "project_name": project_in.name}
    )
    stmt = sql(
        """
        INSERT INTO projects (user_id, name, original_image_url)
        VALUES ($1, $2, $3)
        RETURNING *
        """,
        user_id,
        project_in.name,
        project_in.original_image_url,
    )
    record = await db.fetchrow(stmt)
    if not record:
        raise RuntimeError("Failed to create project record")
    return Project(**dict(record))


async def update_project(
    db: Database,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    project_in: ProjectUpdate,
) -> Project | None:
    """Partially update a project. Returns None if not found or not owned."""
    update_data = {
        k: v
        for k, v in project_in.model_dump(exclude_unset=True).items()
        if k in ALLOWED_UPDATE_FIELDS
    }

    if not update_data:
        # Nothing to change — return current state
        return await get_project_by_id(db, project_id, user_id)

    logger.debug("Updating project", extra={"project_id": str(project_id)})

    set_clauses: list[str] = []
    params: list = []

    for idx, (key, value) in enumerate(update_data.items(), start=1):
        # JSONB columns in PostgreSQL require string values cast to jsonb
        if key == "room_analysis" and isinstance(value, dict):
            set_clauses.append(f"{key}=${idx}::jsonb")
            params.append(json.dumps(value))
        else:
            set_clauses.append(f"{key}=${idx}")
            params.append(value)

    # project_id and user_id are the final two parameters
    params.append(project_id)
    params.append(user_id)
    where_project_id = len(params) - 1
    where_user_id = len(params)

    query = f"""
        UPDATE projects
        SET {", ".join(set_clauses)}, updated_at=CURRENT_TIMESTAMP
        WHERE id=${where_project_id} AND user_id=${where_user_id}
        RETURNING *
    """

    stmt = sql(query, *params)
    record = await db.fetchrow(stmt)
    if not record:
        return None

    # Convert JSONB columns back to dict
    record_dict = dict(record)
    if "room_analysis" in record_dict and isinstance(record_dict["room_analysis"], str):
        record_dict["room_analysis"] = json.loads(record_dict["room_analysis"])

    return Project(**record_dict)


async def delete_project(
    db: Database,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Hard-delete a project row. Returns True if a row was deleted."""
    logger.info("Deleting project", extra={"project_id": str(project_id)})
    stmt = sql(
        "DELETE FROM projects WHERE id=$1 AND user_id=$2 RETURNING id",
        project_id,
        user_id,
    )
    record = await db.fetchrow(stmt)
    return bool(record)
