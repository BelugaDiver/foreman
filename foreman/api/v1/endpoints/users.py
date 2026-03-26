"""User management endpoints."""

from asyncpg.exceptions import UniqueViolationError
from fastapi import APIRouter, Body, Depends, HTTPException

from foreman.api.deps import get_current_user, get_db
from foreman.audit import AuditEvent, log_audit
from foreman.db import Database
from foreman.logging_config import get_logger
from foreman.models.user import User
from foreman.repositories import postgres_users_repository as crud
from foreman.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter()
logger = get_logger("foreman.endpoints.users")


@router.post("/", response_model=UserRead, status_code=201)
async def create_user(
    user_in: UserCreate = Body(...),
    db: Database = Depends(get_db),
):
    """Register a new user."""
    try:
        user = await crud.create_user(db=db, user_in=user_in)
        logger.info("User created", extra={"user_id": str(user.id), "email": user.email})
        return user
    except UniqueViolationError:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    except Exception:
        logger.exception("Error creating user")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.get("/me", response_model=UserRead)
async def read_user_me(
    current_user: User = Depends(get_current_user),
):
    """Get current user."""
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_user_me(
    user_in: UserUpdate = Body(...),
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update current user."""
    try:
        user = await crud.update_user(db=db, user_id=current_user.id, user_in=user_in)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        log_audit(
            AuditEvent.USER_UPDATED,
            str(current_user.id),
            resource_id=str(current_user.id),
            resource_type="user",
        )
        return user
    except UniqueViolationError:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    except Exception:
        logger.exception("Error updating user")
        raise HTTPException(status_code=500, detail="Internal server error")


@router.delete("/me", status_code=204)
async def delete_user_me(
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Soft delete current user."""
    try:
        success = await crud.soft_delete_user(db=db, user_id=current_user.id)
        if not success:
            raise HTTPException(status_code=404, detail="User not found")
        log_audit(
            AuditEvent.USER_DELETED,
            str(current_user.id),
            resource_id=str(current_user.id),
            resource_type="user",
        )
        logger.info("User deleted", extra={"user_id": str(current_user.id)})
    except Exception:
        logger.exception("Error deleting user")
        raise HTTPException(status_code=500, detail="Internal server error")
