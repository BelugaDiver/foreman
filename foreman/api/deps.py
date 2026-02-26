"""API Dependencies including Authentication hooks."""

import uuid

from fastapi import Depends, Header, HTTPException, Request

from foreman.db import Database
from foreman.models.user import User
from foreman.repositories import postgres_users_repository as crud


def get_db(request: Request) -> Database:
    """Retrieve the global Database connection pool from app state."""
    return request.app.state.database


async def get_current_user(
    x_user_id: str | None = Header(None, description="User UUID mapped by Gateway"),
    db: Database = Depends(get_db),
) -> User:
    """Dependency to retrieve the current user making the API request."""
    if not x_user_id:
        raise HTTPException(status_code=401, detail="X-User-ID header missing")

    try:
        user_uuid = uuid.UUID(x_user_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid X-User-ID format; must be UUID")

    user = await crud.get_user_by_id(db, user_uuid)

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.is_active or user.is_deleted:
        raise HTTPException(status_code=401, detail="User is inactive or deleted")

    return user
