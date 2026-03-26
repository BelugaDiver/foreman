"""Project management endpoints."""

import uuid

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Response

from foreman.api.deps import get_current_user, get_db
from foreman.audit import AuditEvent, log_audit
from foreman.db import Database
from foreman.logging_config import get_logger
from foreman.models.user import User
from foreman.repositories import postgres_generations_repository as gen_repo
from foreman.repositories import postgres_projects_repository as crud
from foreman.schemas.generation import GenerationCreate, GenerationRead
from foreman.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

router = APIRouter()
logger = get_logger("foreman.endpoints.projects")


@router.get("/", response_model=list[ProjectRead])
async def list_projects(
    limit: int = Query(20, ge=1, le=100, description="Maximum number of projects to return"),
    offset: int = Query(0, ge=0, description="Number of projects to skip"),
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """List all projects for the current user."""
    logger.debug(
        "Listing projects",
        extra={"user_id": str(current_user.id), "limit": limit, "offset": offset},
    )
    return await crud.list_projects(db=db, user_id=current_user.id, limit=limit, offset=offset)


@router.post("/", response_model=ProjectRead, status_code=201)
async def create_project(
    project_in: ProjectCreate = Body(...),
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Create a new design project."""
    try:
        project = await crud.create_project(db=db, user_id=current_user.id, project_in=project_in)
        logger.info(
            "Project created",
            extra={"project_id": str(project.id), "user_id": str(current_user.id)},
        )
        return project
    except Exception:
        logger.exception("Error creating project")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get details for a single project."""
    project = await crud.get_project_by_id(db=db, project_id=project_id, user_id=current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@router.post("/{project_id}/generations", response_model=GenerationRead, status_code=202)
async def create_generation(
    project_id: uuid.UUID,
    generation_in: GenerationCreate,
    response: Response,
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Create a generation for a project using root image or a parent generation."""
    try:
        if generation_in.parent_id:
            parent = await gen_repo.get_generation_by_id(
                db=db,
                generation_id=generation_in.parent_id,
                user_id=current_user.id,
            )
            if not parent:
                raise HTTPException(status_code=400, detail="Invalid parent generation")
            if parent.project_id != project_id:
                raise HTTPException(status_code=400, detail="Parent belongs to different project")
            if not parent.output_image_url:
                raise HTTPException(status_code=400, detail="Parent generation has no output image")
            input_image_url = parent.output_image_url
        else:
            project = await crud.get_project_by_id(
                db=db, project_id=project_id, user_id=current_user.id
            )
            if not project:
                raise HTTPException(status_code=404, detail="Project not found")
            if not project.original_image_url:
                raise HTTPException(status_code=400, detail="Project has no original image")
            input_image_url = project.original_image_url

        logger.debug(
            "Creating generation for project",
            extra={"project_id": str(project_id), "user_id": str(current_user.id)},
        )
        generation = await gen_repo.create_generation(
            db=db,
            project_id=project_id,
            input_image_url=input_image_url,
            generation_in=generation_in,
        )
        response.headers["Location"] = f"/v1/generations/{generation.id}"
        return generation
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error creating generation")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/{project_id}/generations", response_model=list[GenerationRead])
async def list_project_generations(
    project_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100, description="Maximum number of generations to return"),
    offset: int = Query(0, ge=0, description="Number of generations to skip"),
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """List generations for a single project scoped to the current user."""
    project = await crud.get_project_by_id(
        db=db,
        project_id=project_id,
        user_id=current_user.id,
    )
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return await gen_repo.list_generations_by_project(
        db=db,
        project_id=project_id,
        user_id=current_user.id,
        limit=limit,
        offset=offset,
    )


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID,
    project_in: ProjectUpdate = Body(...),
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update project metadata."""
    try:
        project = await crud.update_project(
            db=db,
            project_id=project_id,
            user_id=current_user.id,
            project_in=project_in,
        )
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        log_audit(
            AuditEvent.PROJECT_UPDATED,
            str(current_user.id),
            resource_id=str(project_id),
            resource_type="project",
        )
        logger.info("Project updated", extra={"project_id": str(project_id)})
        return project
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error updating project")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Delete a project and all its generations."""
    try:
        success = await crud.delete_project(db=db, project_id=project_id, user_id=current_user.id)
        if not success:
            raise HTTPException(status_code=404, detail="Project not found")
        log_audit(
            AuditEvent.PROJECT_DELETED,
            str(current_user.id),
            resource_id=str(project_id),
            resource_type="project",
        )
        logger.info("Project deleted", extra={"project_id": str(project_id)})
    except HTTPException:
        raise
    except Exception:
        logger.exception("Error deleting project")
        raise HTTPException(status_code=500, detail="Internal server error")
