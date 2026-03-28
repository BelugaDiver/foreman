"""Database CRUD operators for the User resource."""

import uuid

import asyncpg

from foreman.db import Database, sql
from foreman.exceptions import DuplicateResourceError, ResourceNotFoundError
from foreman.logging_config import get_logger
from foreman.models.user import User
from foreman.schemas.user import UserCreate, UserUpdate

logger = get_logger("foreman.repositories.users")

# Fields that callers are permitted to update. Filtering against this set
# prevents unknown column names from being interpolated into the UPDATE query.
ALLOWED_UPDATE_FIELDS: frozenset[str] = frozenset({"email", "full_name"})


async def get_user_by_id(db: Database, user_id: uuid.UUID) -> User:
    """Retrieve an active user from the database."""
    logger.debug("Fetching user by ID", extra={"user_id": str(user_id)})
    stmt = sql("SELECT * FROM users WHERE id=$1 AND is_deleted=FALSE", user_id)
    record = await db.fetchrow(stmt)
    if not record:
        raise ResourceNotFoundError("User", user_id)
    return User(**dict(record))


async def get_user_by_email(db: Database, email: str) -> User | None:
    """Retrieve an active user by email address."""
    stmt = sql("SELECT * FROM users WHERE email=$1 AND is_deleted=FALSE", email)
    record = await db.fetchrow(stmt)
    if not record:
        return None
    return User(**dict(record))


async def ensure_dev_user(db: Database) -> User:
    """Retrieve or create the canonical development test user.

    Should only be called during application startup when DEV_MODE is enabled.
    """
    user = await get_user_by_email(db, "test@example.com")
    if user:
        return user
    stmt = sql(
        "INSERT INTO users (email, full_name) VALUES ($1, $2) RETURNING *",
        "test@example.com",
        "Test User",
    )
    record = await db.fetchrow(stmt)
    if not record:
        raise RuntimeError("Failed to create dev test user")
    return User(**dict(record))


async def create_user(db: Database, user_in: UserCreate) -> User:
    """Create a new user in the database."""
    logger.info("Creating user", extra={"email": user_in.email})
    try:
        stmt = sql(
            """
            INSERT INTO users (email, full_name)
            VALUES ($1, $2)
            RETURNING *
            """,
            user_in.email,
            user_in.full_name,
        )
        record = await db.fetchrow(stmt)
    except asyncpg.UniqueViolationError:
        raise DuplicateResourceError("User", "email", user_in.email)
    if not record:
        raise RuntimeError("Failed to create user record")
    return User(**dict(record))


async def update_user(db: Database, user_id: uuid.UUID, user_in: UserUpdate) -> User | None:
    """Update user fields partially."""
    update_data = {
        k: v
        for k, v in user_in.model_dump(exclude_unset=True).items()
        if k in ALLOWED_UPDATE_FIELDS
    }
    if not update_data:
        return await get_user_by_id(db, user_id)

    logger.debug("Updating user", extra={"user_id": str(user_id)})

    set_clauses = []
    params = []

    for idx, (key, value) in enumerate(update_data.items(), start=1):
        set_clauses.append(f"{key}=${idx}")
        params.append(value)

    # Append user_id as the final parameter for the WHERE clause
    params.append(user_id)

    query = f"""
        UPDATE users
        SET {", ".join(set_clauses)}, updated_at=CURRENT_TIMESTAMP
        WHERE id=${len(params)} AND is_deleted=FALSE
        RETURNING *
    """

    stmt = sql(query, *params)
    record = await db.fetchrow(stmt)
    if not record:
        return None
    return User(**dict(record))


async def soft_delete_user(db: Database, user_id: uuid.UUID) -> bool:
    """Soft delete user marking them inactive and deleted."""
    logger.info("Soft deleting user", extra={"user_id": str(user_id)})
    stmt = sql(
        """
        UPDATE users
        SET is_deleted=TRUE, is_active=FALSE, updated_at=CURRENT_TIMESTAMP
        WHERE id=$1 AND is_deleted=FALSE
        RETURNING id
        """,
        user_id,
    )
    record = await db.fetchrow(stmt)
    return bool(record)
