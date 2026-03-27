"""Generation management endpoints."""

import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query

from foreman.api.deps import get_current_user, get_db
from foreman.audit import AuditEvent, log_audit
from foreman.db import Database
from foreman.exceptions import ResourceNotFoundError
from foreman.logging_config import get_logger
from foreman.models.user import User
from foreman.repositories import postgres_generations_repository as repo
from foreman.schemas.generation import GenerationCreate, GenerationRead, GenerationUpdate

router = APIRouter()
logger = get_logger("foreman.endpoints.generations")


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
    try:
        return await repo.get_generation_by_id(
            db=db,
            generation_id=generation_id,
            user_id=current_user.id,
        )
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Generation not found")


@router.patch("/{generation_id}", response_model=GenerationRead)
async def update_generation(
    generation_id: uuid.UUID,
    generation_in: GenerationUpdate = Body(),
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
            raise ResourceNotFoundError("Generation", str(generation_id))
        return updated
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Generation not found")
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
            raise ResourceNotFoundError("Generation", str(generation_id))
        log_audit(
            AuditEvent.GENERATION_DELETED,
            str(current_user.id),
            resource_id=str(generation_id),
            resource_type="generation",
        )
        logger.info("Generation deleted", extra={"generation_id": str(generation_id)})
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Generation not found")
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
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Generation not found")

    if generation.status not in {"pending", "processing"}:
        raise HTTPException(
            status_code=400,
            detail="Cannot cancel generation in current status",
        )

    try:
        updated = await repo.update_generation(
            db=db,
            generation_id=generation_id,
            user_id=current_user.id,
            generation_in=GenerationUpdate(status="cancelled"),
        )
        if not updated:
            raise ResourceNotFoundError("Generation", str(generation_id))
        log_audit(
            AuditEvent.GENERATION_CANCELLED,
            str(current_user.id),
            resource_id=str(generation_id),
            resource_type="generation",
        )
        logger.info("Generation cancelled", extra={"generation_id": str(generation_id)})
        return updated
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Generation not found")
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
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Generation not found")

    if original.status not in {"failed", "cancelled"}:
        raise HTTPException(
            status_code=400,
            detail="Can only retry failed or cancelled generations",
        )

    try:
        generation_in = GenerationCreate(
            prompt=original.prompt,
            style_id=original.style_id,
            parent_id=original.parent_id,
            model_used=original.model_used,
            attempt=original.attempt + 1,
        )
        generation = await repo.create_generation(
            db=db,
            project_id=original.project_id,
            input_image_url=original.input_image_url,
            generation_in=generation_in,
        )
        log_audit(
            AuditEvent.GENERATION_RETRY,
            str(current_user.id),
            resource_id=str(generation_id),
            resource_type="generation",
        )
        logger.info(
            "Generation retried",
            extra={"generation_id": str(generation_id), "attempt": generation.attempt},
        )
        return generation
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
    except ResourceNotFoundError:
        raise HTTPException(status_code=404, detail="Generation not found")

    if not parent.output_image_url:
        raise HTTPException(
            status_code=400,
            detail="Cannot fork generation without output image",
        )

    try:
        generation_in = GenerationCreate(
            prompt=parent.prompt,
            style_id=parent.style_id,
            parent_id=parent.id,
            model_used=parent.model_used,
        )
        new_generation = await repo.create_generation(
            db=db,
            project_id=parent.project_id,
            input_image_url=parent.output_image_url,
            generation_in=generation_in,
        )
        log_audit(
            AuditEvent.GENERATION_FORK,
            str(current_user.id),
            resource_id=str(new_generation.id),
            resource_type="generation",
        )
        logger.info(
            "Generation forked",
            extra={"original_id": str(generation_id), "new_id": str(new_generation.id)},
        )
        return new_generation
    except Exception:
        logger.exception("Error forking generation")
        raise HTTPException(status_code=500, detail="Internal server error")
