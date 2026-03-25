"""User model mapping to database schema."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class User:
    """Internal user representation mirroring the database record."""

    id: uuid.UUID
    email: str
    full_name: str
    is_active: bool
    is_deleted: bool
    created_at: datetime
    updated_at: Optional[datetime]
