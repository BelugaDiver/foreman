"""Pydantic schemas for Style HTTP requests and responses."""

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class StyleRead(BaseModel):
    """Properties to return to client."""

    id: uuid.UUID
    name: str
    description: Optional[str]
    example_image_url: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
