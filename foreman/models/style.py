"""Style model mapping to the database schema."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Style:
    """Internal style representation mirroring the database record."""

    id: uuid.UUID
    name: str
    description: Optional[str]
    example_image_url: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]
