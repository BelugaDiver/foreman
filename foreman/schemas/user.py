"""Pydantic schemas for User HTTP requests and responses."""
import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserBase(BaseModel):
    """Shared properties."""
    email: str
    full_name: str


class UserCreate(UserBase):
    """Properties to receive on user creation."""
    pass


class UserUpdate(BaseModel):
    """Properties to receive on user update."""
    email: Optional[str] = None
    full_name: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class UserRead(BaseModel):
    """Properties to return to client."""
    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
