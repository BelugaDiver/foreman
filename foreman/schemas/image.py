"""Pydantic schemas for the Image resource."""

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp", "image/gif"}


class ImageCreate(BaseModel):
    """Schema for creating an image record."""

    project_id: UUID
    user_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str


class ImageUploadRequest(BaseModel):
    """Schema for requesting an upload intent."""

    filename: str = Field(..., min_length=1)
    content_type: str = Field(..., pattern=r"^image/(jpeg|png|gif|webp)$")
    size_bytes: int = Field(..., gt=0)

    model_config = ConfigDict(extra="forbid")

    @field_validator("filename")
    @classmethod
    def filename_no_path_separators(cls, v: str) -> str:
        if not v:
            raise ValueError("Filename cannot be empty")
        if "/" in v or "\\" in v:
            raise ValueError("Filename cannot contain path separators")
        if ".." in v:
            raise ValueError("Filename cannot contain '..'")
        return v

    @field_validator("content_type")
    @classmethod
    def content_type_allowed(cls, v: str) -> str:
        if v.lower() not in ALLOWED_CONTENT_TYPES:
            raise ValueError(f"content_type must be one of: {ALLOWED_CONTENT_TYPES}")
        return v.lower()

    @field_validator("size_bytes")
    @classmethod
    def size_bytes_positive(cls, v: int) -> int:
        if v <= 0:
            raise ValueError("size_bytes must be positive")
        if v > 50_000_000:  # 50MB limit
            raise ValueError("size_bytes cannot exceed 50MB")
        return v


class ImageUpdate(BaseModel):
    """Schema for updating an image (partial)."""

    url: Optional[str] = None

    model_config = ConfigDict(extra="forbid")


class ImageRead(BaseModel):
    """Schema for reading an image (response)."""

    id: UUID
    project_id: UUID
    user_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str
    url: Optional[str]
    created_at: datetime
    updated_at: Optional[datetime]

    model_config = ConfigDict(from_attributes=True)


class ImageUploadIntent(BaseModel):
    """Response schema for upload intent."""

    upload_url: str
    image_id: UUID
    file_key: str
    expires_at: datetime
