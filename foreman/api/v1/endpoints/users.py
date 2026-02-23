"""User management endpoints."""
from fastapi import APIRouter, Depends, HTTPException
from asyncpg.exceptions import UniqueViolationError

from foreman import crud
from foreman.api.deps import get_current_user, get_db
from foreman.db import Database
from foreman.models.user import User
from foreman.schemas.user import UserCreate, UserRead, UserUpdate

router = APIRouter()


@router.post("/", response_model=UserRead, status_code=201)
async def create_user(
    user_in: UserCreate,
    db: Database = Depends(get_db),
):
    """Register a new user."""
    try:
        user = await crud.create_user(db=db, user_in=user_in)
        return user
    except UniqueViolationError:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/me", response_model=UserRead)
async def read_user_me(
    current_user: User = Depends(get_current_user),
):
    """Get current user."""
    return current_user


@router.patch("/me", response_model=UserRead)
async def update_user_me(
    user_in: UserUpdate,
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update current user."""
    try:
        user = await crud.update_user(db=db, user_id=current_user.id, user_in=user_in)
        if not user:
            raise HTTPException(status_code=404, detail="User not found")
        return user
    except UniqueViolationError:
        raise HTTPException(status_code=400, detail="User with this email already exists")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/me", status_code=204)
async def delete_user_me(
    current_user: User = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Soft delete current user."""
    success = await crud.soft_delete_user(db=db, user_id=current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="User not found")
