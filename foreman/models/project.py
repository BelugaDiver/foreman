"""Project model mapping to the database schema."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Project:
    """Internal project representation mirroring the database record."""

    id: uuid.UUID
    user_id: uuid.UUID
    name: str
    original_image_url: Optional[str]
    room_analysis: Optional[dict]
    created_at: datetime
    updated_at: Optional[datetime]
