"""Pydantic schemas for Project HTTP requests and responses."""

import uuid
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ProjectCreate(BaseModel):
    """Properties to receive on project creation."""

    name: str
    original_image_url: Optional[str] = None


class ProjectUpdate(BaseModel):
    """Properties to receive on project update."""

    name: Optional[str] = None
    original_image_url: Optional[str] = None
    room_analysis: Optional[dict[str, Any]] = None

    model_config = ConfigDict(extra="forbid")


class ProjectRead(BaseModel):
    """Properties to return to client."""

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    original_image_url: Optional[str]
    room_analysis: Optional[dict[str, Any]]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
