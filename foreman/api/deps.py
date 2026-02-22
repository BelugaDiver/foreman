"""API Dependencies including Authentication hooks."""
import os
import uuid

from fastapi import Depends, Header, HTTPException, Request

from foreman.db import Database, sql
from foreman.models.user import User


def get_db(request: Request) -> Database:
    """Retrieve the global Database connection pool from app state."""
    return request.app.state.database


async def get_current_user(
    x_user_id: str | None = Header(None, description="User UUID mapped by Gateway"),
    db: Database = Depends(get_db),
) -> User:
    """Dependency to retrieve the current user making the API request."""
    dev_mode = os.getenv("DEV_MODE", "false").lower() == "true"

    if not x_user_id:
        if dev_mode:
            # Fetch a default test user or create one if it doesn't exist
            stmt = sql("SELECT * FROM users WHERE email='test@example.com' LIMIT 1")
            record = await db.fetchrow(stmt)
            if not record:
                stmt_insert = sql(
                    "INSERT INTO users (email, full_name) VALUES ('test@example.com', 'Test User') RETURNING *"
                )
                record = await db.fetchrow(stmt_insert)
                if not record:
                    raise HTTPException(status_code=500, detail="Failed to create DEV Test User")
        else:
            raise HTTPException(status_code=401, detail="X-User-ID header missing")
    else:
        try:
            user_uuid = uuid.UUID(x_user_id)
        except ValueError:
            raise HTTPException(status_code=401, detail="Invalid X-User-ID format; must be UUID")

        stmt = sql("SELECT * FROM users WHERE id=$1", user_uuid)
        record = await db.fetchrow(stmt)

    if not record:
        raise HTTPException(status_code=401, detail="User not found")

    user = User(**dict(record))
    if not user.is_active or user.is_deleted:
        raise HTTPException(status_code=401, detail="User is inactive or deleted")

    return user
