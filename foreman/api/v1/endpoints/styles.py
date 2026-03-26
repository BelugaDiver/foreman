"""Style catalog endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from foreman.api.deps import get_current_user, get_db
from foreman.db import Database
from foreman.logging_config import get_logger
from foreman.models.user import User
from foreman.repositories import postgres_styles_repository as crud
from foreman.schemas.style import StyleRead

router = APIRouter()

logger = get_logger("foreman.endpoints.styles")


@router.get(
    "/",
    response_model=list[StyleRead],
)
async def list_styles(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all available design styles."""
    logger.debug(
        "Listing styles",
        extra={
            "user_id": str(current_user.id),
            "limit": limit,
            "offset": offset,
        },
    )

    styles = await crud.list_styles(db, limit, offset)
    return styles


@router.get(
    "/{style_id}",
    response_model=StyleRead,
)
async def get_style(
    style_id: uuid.UUID,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get style details by ID."""
    style = await crud.get_style_by_id(db, style_id)
    if not style:
        raise HTTPException(status_code=404, detail="Style not found")

    logger.info(
        "Style retrieved",
        extra={"style_id": str(style_id), "user_id": str(current_user.id)},
    )
    return style
