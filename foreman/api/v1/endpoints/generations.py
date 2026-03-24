"""Generation management endpoints."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from foreman.api.deps import get_current_user, get_db
from foreman.db import Database
from foreman.models.user import User
from foreman.repositories import postgres_generations_repository as repo
from foreman.schemas.generation import GenerationCreate, GenerationRead, GenerationUpdate

router = APIRouter()
logger = logging.getLogger(__name__)


@router.get("/", response_model=list[GenerationRead])
async def list_generations(
    limit: int = Query(20, ge=1, le=100, description="Maximum number of generations to return"),
    offset: int = Query(0, ge=0, description="Number of generations to skip"),
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """List all generations for the current user."""
    try:
        return await repo.list_generations(
            db=db,
            user_id=current_user.id,
            limit=limit,
            offset=offset,
        )
    except Exception:
        logger.exception("Error listing generations")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{generation_id}", response_model=GenerationRead)
async def get_generation(
    generation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get details for a single generation."""
    generation = await repo.get_generation_by_id(
        db=db,
        generation_id=generation_id,
        user_id=current_user.id,
    )
    if not generation:
        raise HTTPException(status_code=404, detail="Generation not found")
    return generation


@router.patch("/{generation_id}", response_model=GenerationRead)
async def update_generation(
    generation_id: uuid.UUID,
    generation_in: GenerationUpdate,
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update a generation owned by the current user."""
    try:
        updated = await repo.update_generation(
            db=db,
            generation_id=generation_id,
            user_id=current_user.id,
            generation_in=generation_in,
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Generation not found")
        return updated
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error updating generation")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{generation_id}", status_code=204)
async def delete_generation(
    generation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Delete a generation owned by the current user."""
    try:
        success = await repo.delete_generation(
            db=db,
            generation_id=generation_id,
            user_id=current_user.id,
        )
        if not success:
            raise HTTPException(status_code=404, detail="Generation not found")
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error deleting generation")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{generation_id}/cancel", response_model=GenerationRead)
async def cancel_generation(
    generation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Cancel a generation if it is still pending or processing."""
    try:
        generation = await repo.get_generation_by_id(
            db=db,
            generation_id=generation_id,
            user_id=current_user.id,
        )
        if not generation:
            raise HTTPException(status_code=404, detail="Generation not found")
        if generation.status not in {"pending", "processing"}:
            raise HTTPException(
                status_code=400,
                detail="Cannot cancel generation in current status",
            )

        updated = await repo.update_generation(
            db=db,
            generation_id=generation_id,
            user_id=current_user.id,
            generation_in=GenerationUpdate(status="cancelled"),
        )
        if not updated:
            raise HTTPException(status_code=404, detail="Generation not found")
        return updated
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error cancelling generation")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{generation_id}/retry", response_model=GenerationRead, status_code=201)
async def retry_generation(
    generation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Create a new generation using the same source inputs as the original."""
    try:
        original = await repo.get_generation_by_id(
            db=db,
            generation_id=generation_id,
            user_id=current_user.id,
        )
        if not original:
            raise HTTPException(status_code=404, detail="Generation not found")

        generation_in = GenerationCreate(
            prompt=original.prompt,
            style_id=original.style_id,
            parent_id=original.parent_id,
            model_used=original.model_used,
        )
        return await repo.create_generation(
            db=db,
            project_id=original.project_id,
            input_image_url=original.input_image_url,
            generation_in=generation_in,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error retrying generation")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/{generation_id}/fork", response_model=GenerationRead, status_code=201)
async def fork_generation(
    generation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Create a child generation using the current generation output as input."""
    try:
        parent = await repo.get_generation_by_id(
            db=db,
            generation_id=generation_id,
            user_id=current_user.id,
        )
        if not parent:
            raise HTTPException(status_code=404, detail="Generation not found")
        if not parent.output_image_url:
            raise HTTPException(
                status_code=400,
                detail="Cannot fork generation without output image",
            )

        generation_in = GenerationCreate(
            prompt=parent.prompt,
            style_id=parent.style_id,
            parent_id=parent.id,
            model_used=parent.model_used,
        )
        return await repo.create_generation(
            db=db,
            project_id=parent.project_id,
            input_image_url=parent.output_image_url,
            generation_in=generation_in,
        )
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error forking generation")
        raise HTTPException(status_code=500, detail="Internal server error")
