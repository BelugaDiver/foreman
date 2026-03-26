"""Image model mapping to the database schema."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Image:
    """Internal image representation mirroring the database record."""

    id: uuid.UUID
    project_id: uuid.UUID
    user_id: uuid.UUID
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str
    url: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
