"""Database CRUD operations for the Image resource."""

import uuid
from typing import Optional

from foreman.db import Database, sql
from foreman.logging_config import get_logger
from foreman.models.image import Image
from foreman.schemas.image import ImageCreate, ImageUpdate

logger = get_logger("foreman.repositories.images")

ALLOWED_UPDATE_FIELDS: frozenset[str] = frozenset({"url"})


async def list_images(
    db: Database,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
) -> list[Image]:
    """Return a paginated list of images for a project."""
    logger.debug("Listing images", extra={"project_id": str(project_id), "user_id": str(user_id)})
    stmt = sql(
        """
        SELECT * FROM images
        WHERE project_id=$1 AND user_id=$2
        ORDER BY created_at DESC
        LIMIT $3 OFFSET $4
        """,
        project_id,
        user_id,
        limit,
        offset,
    )
    records = await db.fetch(stmt)
    return [Image(**dict(r)) for r in records]


async def get_image_by_id(
    db: Database,
    image_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Optional[Image]:
    """Retrieve a single image by ID scoped to the owning user."""
    logger.debug("Fetching image", extra={"image_id": str(image_id), "user_id": str(user_id)})
    stmt = sql(
        "SELECT * FROM images WHERE id=$1 AND user_id=$2",
        image_id,
        user_id,
    )
    record = await db.fetchrow(stmt)
    if not record:
        return None
    return Image(**dict(record))


async def create_image(
    db: Database,
    image_in: ImageCreate,
    url: Optional[str] = None,
) -> Image:
    """Insert a new image row and return it."""
    logger.info(
        "Creating image record",
        extra={"project_id": str(image_in.project_id), "filename": image_in.filename},
    )
    stmt = sql(
        """
        INSERT INTO images
            (project_id, user_id, filename, content_type, size_bytes, storage_key, url)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        image_in.project_id,
        image_in.user_id,
        image_in.filename,
        image_in.content_type,
        image_in.size_bytes,
        image_in.storage_key,
        url,
    )
    record = await db.fetchrow(stmt)
    if not record:
        raise RuntimeError("Failed to create image record")
    return Image(**dict(record))


async def update_image(
    db: Database,
    image_id: uuid.UUID,
    user_id: uuid.UUID,
    image_in: ImageUpdate,
) -> Optional[Image]:
    """Partially update an image. Returns None if not found or not owned."""
    update_data = {
        k: v
        for k, v in image_in.model_dump(exclude_unset=True).items()
        if k in ALLOWED_UPDATE_FIELDS
    }

    if not update_data:
        return await get_image_by_id(db, image_id, user_id)

    logger.debug("Updating image", extra={"image_id": str(image_id)})

    set_clauses: list[str] = []
    params: list = []

    for idx, (key, value) in enumerate(update_data.items(), start=1):
        set_clauses.append(f"{key}=${idx}")
        params.append(value)

    params.append(image_id)
    params.append(user_id)

    query = f"""
        UPDATE images
        SET {", ".join(set_clauses)}, updated_at=CURRENT_TIMESTAMP
        WHERE id=${len(params) - 1} AND user_id=${len(params)}
        RETURNING *
    """

    stmt = sql(query, *params)
    record = await db.fetchrow(stmt)
    if not record:
        return None
    return Image(**dict(record))


async def delete_image(
    db: Database,
    image_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Hard-delete an image row. Returns True if a row was deleted."""
    logger.info("Deleting image", extra={"image_id": str(image_id)})
    stmt = sql(
        "DELETE FROM images WHERE id=$1 AND user_id=$2 RETURNING id",
        image_id,
        user_id,
    )
    record = await db.fetchrow(stmt)
    return bool(record)
