"""Generation model mapping to the database schema."""

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Any


@dataclass
class Generation:
    """Internal generation representation mirroring the database record."""

    id: uuid.UUID
    project_id: uuid.UUID
    parent_id: Optional[uuid.UUID]
    status: str
    prompt: str
    style_id: Optional[str]
    input_image_url: str
    output_image_url: Optional[str]
    error_message: Optional[str]
    model_used: Optional[str]
    processing_time_ms: Optional[int]
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: Optional[datetime]
