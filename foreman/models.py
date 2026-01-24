"""Data models for image generation requests."""

from datetime import UTC, datetime
from enum import Enum
from typing import Optional
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class RequestStatus(str, Enum):
    """Status of an image generation request."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


class ImageGenerationRequest(BaseModel):
    """Model for an image generation request."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "prompt": "A beautiful sunset over mountains",
                "model": "stable-diffusion-v1",
                "width": 512,
                "height": 512,
                "num_images": 1,
            }
        }
    )

    id: UUID = Field(default_factory=uuid4)
    prompt: str = Field(..., description="Text prompt for image generation")
    model: str = Field(default="stable-diffusion-v1", description="AI model to use")
    width: int = Field(default=512, ge=64, le=2048, description="Image width in pixels")
    height: int = Field(default=512, ge=64, le=2048, description="Image height in pixels")
    num_images: int = Field(default=1, ge=1, le=10, description="Number of images to generate")
    status: RequestStatus = Field(default=RequestStatus.PENDING)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: Optional[datetime] = None
    error_message: Optional[str] = None


class ImageGenerationResponse(BaseModel):
    """Response model for image generation request."""

    id: UUID
    status: RequestStatus
    message: str


class HealthCheck(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = "0.1.0"
    service: str = "foreman"
