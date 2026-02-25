"""Database CRUD operators for the User resource."""
import uuid

from foreman.db import Database, sql
from foreman.models.user import User
from foreman.schemas.user import UserCreate, UserUpdate


async def get_user_by_id(db: Database, user_id: uuid.UUID) -> User | None:
    """Retrieve an active user from the database."""
    stmt = sql("SELECT * FROM users WHERE id=$1 AND is_deleted=FALSE", user_id)
    record = await db.fetchrow(stmt)
    if not record:
        return None
    return User(**dict(record))


async def create_user(db: Database, user_in: UserCreate) -> User:
    """Create a new user in the database."""
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
    if not record:
        raise RuntimeError("Failed to create user record")
    return User(**dict(record))


async def update_user(
    db: Database, user_id: uuid.UUID, user_in: UserUpdate
) -> User | None:
    """Update user fields partially."""
    update_data = user_in.model_dump(exclude_unset=True)
    if not update_data:
        return await get_user_by_id(db, user_id)

    set_clauses = []
    params = []

    for idx, (key, value) in enumerate(update_data.items(), start=1):
        set_clauses.append(f"{key}=${idx}")
        params.append(value)

    # Append user_id as the final parameter for the WHERE clause
    params.append(user_id)

    query = f"""
        UPDATE users
        SET {', '.join(set_clauses)}, updated_at=CURRENT_TIMESTAMP
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
