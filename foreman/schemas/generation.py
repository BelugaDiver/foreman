"""Pydantic schemas for Generation HTTP requests and responses."""

import uuid
from datetime import datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

GenerationStatus = Literal["pending", "processing", "completed", "failed", "cancelled"]


class GenerationCreate(BaseModel):
    """Properties to receive on generation creation."""

    prompt: str = Field(min_length=1)
    style_id: Optional[str] = None
    parent_id: Optional[uuid.UUID] = None
    model_used: Optional[str] = None
    attempt: Optional[int] = None

    model_config = ConfigDict(extra="forbid")

    @field_validator("prompt")
    @classmethod
    def validate_prompt_not_blank(cls, value: str) -> str:
        """Reject prompts that only contain whitespace."""
        if not value.strip():
            raise ValueError("Prompt cannot be blank")
        return value


class GenerationUpdate(BaseModel):
    """Properties to receive on generation update."""

    status: Optional[GenerationStatus] = None
    output_image_url: Optional[str] = None
    error_message: Optional[str] = None
    processing_time_ms: Optional[int] = None
    metadata: Optional[dict[str, Any]] = None

    model_config = ConfigDict(extra="forbid")


class GenerationRead(BaseModel):
    """Properties to return to client."""

    id: uuid.UUID
    project_id: uuid.UUID
    parent_id: Optional[uuid.UUID]
    status: GenerationStatus
    prompt: str
    style_id: Optional[str]
    model_used: Optional[str]
    input_image_url: str
    output_image_url: Optional[str]
    error_message: Optional[str]
    processing_time_ms: Optional[int]
    attempt: int
    metadata: Optional[dict[str, Any]] = None
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)
