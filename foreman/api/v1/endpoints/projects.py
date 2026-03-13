"""Project management endpoints."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from foreman.api.deps import get_current_user, get_db
from foreman.db import Database
from foreman.models.user import User
from foreman.repositories import postgres_projects_repository as crud
from foreman.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/", response_model=list[ProjectRead])
async def list_projects(
    limit: int = Query(20, ge=1, le=100, description="Maximum number of projects to return"),
    offset: int = Query(0, ge=0, description="Number of projects to skip"),
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """List all projects for the current user."""
    return await crud.list_projects(db=db, user_id=current_user.id, limit=limit, offset=offset)


@router.post("/", response_model=ProjectRead, status_code=201)
async def create_project(
    project_in: ProjectCreate,
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Create a new design project."""
    try:
        return await crud.create_project(db=db, user_id=current_user.id, project_in=project_in)
    except Exception as exc:
        logger.exception("Failed to create project", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


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


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: uuid.UUID,
    project_in: ProjectUpdate,
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
        return project
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to update project", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error") from exc


@router.delete("/{project_id}", status_code=204)
async def delete_project(
    project_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Delete a project and all its generations."""
    success = await crud.delete_project(db=db, project_id=project_id, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="Project not found")
