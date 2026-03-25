Complete Implementation Plan: Images/Uploads with Cloudflare R2
---
Part 1: Terraform Files
terraform/main.tf
terraform {
  required_providers = {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 4.0"
    }
  }
}
provider "cloudflare" {
  api_token = var.cloudflare_api_token
}
resource "cloudflare_r2_bucket" "foreman" {
  account_id = var.cloudflare_account_id
  name       = "foreman-images"
}
resource "cloudflare_r2_custom_domain" "foreman" {
  count      = var.storage_domain != "" ? 1 : 0
  bucket_name = cloudflare_r2_bucket.foreman.name
  domain      = var.storage_domain
}
terraform/variables.tf
variable "cloudflare_account_id" {
  description = "Cloudflare account ID"
  type        = string
}
variable "cloudflare_api_token" {
  description = "Cloudflare API token with R2 write access"
  type        = string
  sensitive   = true
}
variable "storage_domain" {
  description = "Custom domain for R2 (optional)"
  type        = string
  default     = ""
}
terraform/outputs.tf
output "r2_endpoint" {
  description = "R2 bucket endpoint URL"
  value       = cloudflare_r2_bucket.foreman.endpoint
}
output "r2_bucket_name" {
  description = "R2 bucket name"
  value       = cloudflare_r2_bucket.foreman.name
}
output "r2_public_url" {
  description = "Public URL for accessing files"
  value       = var.storage_domain != "" ? "https://${var.storage_domain}" : cloudflare_r2_bucket.foreman.bucket_domain_name
}
---
Part 2: Database Migration
migrations/versions/0005_create_images_table.py
"""Create images table
Revision ID: 0005
Revises: 0004
Create Date: 2026-03-24 12:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
revision: str = "0005"
down_revision: Union[str, None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None
def upgrade() -> None:
    op.execute("""
    CREATE TABLE images (
        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
        project_id UUID NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        user_id UUID NOT NULL REFERENCES users(id),
        filename VARCHAR(512) NOT NULL,
        content_type VARCHAR(100) NOT NULL,
        size_bytes INTEGER NOT NULL,
        storage_key VARCHAR(1024) NOT NULL,
        url VARCHAR(2048),
        created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
    );
    """)
    op.execute("CREATE INDEX idx_images_project_id ON images(project_id);")
    op.execute("CREATE INDEX idx_images_user_id ON images(user_id);")
def downgrade() -> None:
    op.execute("DROP TABLE images;")
---
Part 3: Storage Layer
foreman/storage/init.py
"""Storage abstraction for cloud object storage."""
from foreman.storage.factory import get_storage, get_storage_sync
from foreman.storage.protocol import StorageProtocol, UploadIntent
from foreman.storage.r2_storage import R2Storage
__all__ = ["StorageProtocol", "UploadIntent", "R2Storage", "get_storage", "get_storage_sync"]
foreman/storage/protocol.py
"""Storage abstraction layer for cloud object storage."""
from __future__ import annotations
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
@dataclass
class UploadIntent:
    """Result of creating an upload intent."""
    upload_url: str
    file_key: str
    expires_at: datetime
class StorageProtocol(ABC):
    """Abstract storage interface."""
    @abstractmethod
    async def create_upload_url(
        self,
        filename: str,
        content_type: str,
        project_id: uuid.UUID,
    ) -> UploadIntent:
        """Generate a presigned URL for direct upload."""
    @abstractmethod
    async def get_download_url(self, storage_key: str) -> str:
        """Get a URL for downloading the file."""
    @abstractmethod
    async def delete(self, storage_key: str) -> bool:
        """Delete a file from storage."""
foreman/storage/settings.py
"""Storage configuration."""
from __future__ import annotations
import os
from dataclasses import dataclass
from typing import Optional
@dataclass
class StorageSettings:
    """Base storage configuration."""
    provider: str = "r2"
    bucket: str = "foreman-images"
@dataclass
class R2Settings(StorageSettings):
    """Cloudflare R2 configuration."""
    endpoint: Optional[str] = None
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    public_url: Optional[str] = None
    @classmethod
    def from_env(cls) -> R2Settings:
        return cls(
            provider="r2",
            endpoint=os.getenv("R2_ENDPOINT"),
            access_key_id=os.getenv("R2_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("R2_SECRET_ACCESS_KEY"),
            bucket=os.getenv("R2_BUCKET", "foreman-images"),
            public_url=os.getenv("R2_PUBLIC_URL"),
        )
    @property
    def is_configured(self) -> bool:
        return bool(self.endpoint and self.access_key_id and self.secret_access_key)
@dataclass
class S3Settings(StorageSettings):
    """AWS S3 configuration."""
    region: str = "us-east-1"
    access_key_id: Optional[str] = None
    secret_access_key: Optional[str] = None
    public_url: Optional[str] = None
    @classmethod
    def from_env(cls) -> S3Settings:
        return cls(
            provider="s3",
            bucket=os.getenv("S3_BUCKET", "foreman-images"),
            region=os.getenv("S3_REGION", "us-east-1"),
            access_key_id=os.getenv("S3_ACCESS_KEY_ID"),
            secret_access_key=os.getenv("S3_SECRET_ACCESS_KEY"),
            public_url=os.getenv("S3_PUBLIC_URL"),
        )
    @property
    def is_configured(self) -> bool:
        return bool(self.access_key_id and self.secret_access_key)
foreman/storage/r2_storage.py
"""Cloudflare R2 storage implementation."""
from __future__ import annotations
import uuid
from datetime import datetime, timedelta, timezone
import boto3
from botocore.config import Config
from foreman.storage.protocol import StorageProtocol, UploadIntent
from foreman.storage.settings import R2Settings
class R2Storage(StorageProtocol):
    """Cloudflare R2 storage using S3-compatible API."""
    def __init__(self, settings: R2Settings) -> None:
        if not settings.is_configured:
            raise ValueError("R2Settings is not configured")
        self._settings = settings
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.endpoint,
            aws_access_key_id=settings.access_key_id,
            aws_secret_access_key=settings.secret_access_key,
            config=Config(signature_version="s3v4"),
        )
        self._bucket = settings.bucket
    async def create_upload_url(
        self,
        filename: str,
        content_type: str,
        project_id: uuid.UUID,
    ) -> UploadIntent:
        key = f"projects/{project_id}/{uuid.uuid4()}/{filename}"
        expires = timedelta(hours=1)
        url = self._client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": self._bucket,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=int(expires.total_seconds()),
        )
        return UploadIntent(
            upload_url=url,
            file_key=key,
            expires_at=datetime.now(timezone.utc) + expires,
        )
    async def get_download_url(self, storage_key: str) -> str:
        if self._settings.public_url:
            return f"{self._settings.public_url}/{storage_key}"
        expires = timedelta(hours=1)
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": storage_key},
            ExpiresIn=int(expires.total_seconds()),
        )
    async def delete(self, storage_key: str) -> bool:
        self._client.delete_object(Bucket=self._bucket, Key=storage_key)
        return True
foreman/storage/factory.py
"""Storage factory for creating storage backends."""
from __future__ import annotations
import os
from foreman.storage.protocol import StorageProtocol
from foreman.storage.r2_storage import R2Storage
from foreman.storage.settings import R2Settings, S3Settings
def get_storage() -> StorageProtocol:
    """Create a storage backend based on STORAGE_PROVIDER env var."""
    provider = os.getenv("STORAGE_PROVIDER", "r2").lower()
    if provider == "r2":
        return R2Storage(R2Settings.from_env())
    elif provider == "s3":
        from foreman.storage.s3_storage import S3Storage
        return S3Storage(S3Settings.from_env())
    raise ValueError(f"Unknown STORAGE_PROVIDER: {provider}")
def get_storage_sync() -> StorageProtocol:
    """Synchronous version for use in dependency injection."""
    return get_storage()
---
Part 4: Data Layer
foreman/models/image.py
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
foreman/schemas/image.py
"""Pydantic schemas for the Image resource."""
from datetime import datetime
from typing import Optional
from uuid import UUID
from pydantic import BaseModel, ConfigDict
class ImageCreate(BaseModel):
    """Schema for creating an image record."""
    project_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    storage_key: str
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
foreman/repositories/postgres_images_repository.py
"""Database CRUD operations for the Image resource."""
import uuid
from typing import Optional
from foreman.db import Database, sql
from foreman.models.image import Image
from foreman.schemas.image import ImageCreate, ImageUpdate
ALLOWED_UPDATE_FIELDS: frozenset[str] = frozenset({"url"})
async def list_images(
    db: Database,
    project_id: uuid.UUID,
    user_id: uuid.UUID,
    limit: int = 20,
    offset: int = 0,
) -> list[Image]:
    """Return a paginated list of images for a project."""
    stmt = sql(
        """
        SELECT * FROM images
        WHERE project_id=$1 AND user_id=$2
        ORDER BY created_at DESC
        LIMIT $3 OFFSET $4
        """,
        project_id,
        user_id,
        limit,
        offset,
    )
    records = await db.fetch(stmt)
    return [Image(**dict(r)) for r in records]
async def get_image_by_id(
    db: Database,
    image_id: uuid.UUID,
    user_id: uuid.UUID,
) -> Optional[Image]:
    """Retrieve a single image by ID scoped to the owning user."""
    stmt = sql(
        "SELECT * FROM images WHERE id=$1 AND user_id=$2",
        image_id,
        user_id,
    )
    record = await db.fetchrow(stmt)
    if not record:
        return None
    return Image(**dict(record))
async def create_image(
    db: Database,
    image_in: ImageCreate,
    url: Optional[str] = None,
) -> Image:
    """Insert a new image row and return it."""
    stmt = sql(
        """
        INSERT INTO images (project_id, user_id, filename, content_type, size_bytes, storage_key, url)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        RETURNING *
        """,
        image_in.project_id,
        image_in.user_id,
        image_in.filename,
        image_in.content_type,
        image_in.size_bytes,
        image_in.storage_key,
        url,
    )
    record = await db.fetchrow(stmt)
    if not record:
        raise RuntimeError("Failed to create image record")
    return Image(**dict(record))
async def update_image(
    db: Database,
    image_id: uuid.UUID,
    user_id: uuid.UUID,
    image_in: ImageUpdate,
) -> Optional[Image]:
    """Partially update an image. Returns None if not found or not owned."""
    update_data = {
        k: v
        for k, v in image_in.model_dump(exclude_unset=True).items()
        if k in ALLOWED_UPDATE_FIELDS
    }
    if not update_data:
        return await get_image_by_id(db, image_id, user_id)
    set_clauses: list[str] = []
    params: list = []
    for idx, (key, value) in enumerate(update_data.items(), start=1):
        set_clauses.append(f"{key}=${idx}")
        params.append(value)
    params.append(image_id)
    params.append(user_id)
    query = f"""
        UPDATE images
        SET {", ".join(set_clauses)}, updated_at=CURRENT_TIMESTAMP
        WHERE id=${len(params) - 1} AND user_id=${len(params)}
        RETURNING *
    """
    stmt = sql(query, *params)
    record = await db.fetchrow(stmt)
    if not record:
        return None
    return Image(**dict(record))
async def delete_image(
    db: Database,
    image_id: uuid.UUID,
    user_id: uuid.UUID,
) -> bool:
    """Hard-delete an image row. Returns True if a row was deleted."""
    stmt = sql(
        "DELETE FROM images WHERE id=$1 AND user_id=$2 RETURNING id",
        image_id,
        user_id,
    )
    record = await db.fetchrow(stmt)
    return bool(record)
---
Part 5: API Layer
foreman/api/v1/endpoints/images.py
"""Image management endpoints."""
import uuid
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import ORJSONResponse
from foreman.api.deps import get_current_user, get_db
from foreman.db import Database
from foreman.models.user import User
from foreman.repositories import postgres_images_repository as crud
from foreman.repositories import postgres_projects_repository as project_crud
from foreman.schemas.image import ImageCreate, ImageRead, ImageUpdate, ImageUploadIntent
from foreman.storage import get_storage_sync, StorageProtocol
router = APIRouter()
async def get_storage() -> StorageProtocol:
    """Dependency for injecting storage backend."""
    return get_storage_sync()
@router.post(
    "/projects/{project_id}/images",
    response_class=ORJSONResponse,
    status_code=201,
    response_model=ImageUploadIntent,
)
async def create_upload_intent(
    project_id: uuid.UUID,
    filename: str = Query(..., description="Name of the file"),
    content_type: str = Query(..., description="MIME type of the file"),
    size_bytes: int = Query(..., description="Size of the file in bytes"),
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageProtocol = Depends(get_storage),
):
    """Create an upload intent and return a presigned URL for direct upload to R2."""
    project = await project_crud.get_project_by_id(db, project_id, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    intent = await storage.create_upload_url(filename, content_type, project_id)
    image_in = ImageCreate(
        project_id=project_id,
        user_id=current_user.id,
        filename=filename,
        content_type=content_type,
        size_bytes=size_bytes,
        storage_key=intent.file_key,
    )
    try:
        image = await crud.create_image(db, image_in, url=None)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
    return ImageUploadIntent(
        upload_url=intent.upload_url,
        image_id=image.id,
        file_key=intent.file_key,
        expires_at=intent.expires_at,
    )
@router.get(
    "/projects/{project_id}/images",
    response_class=ORJSONResponse,
    response_model=list[ImageRead],
)
async def list_images(
    project_id: uuid.UUID,
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List all images for a project."""
    project = await project_crud.get_project_by_id(db, project_id, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    images = await crud.list_images(db, project_id, current_user.id, limit, offset)
    return images
@router.get(
    "/images/{image_id}",
    response_class=ORJSONResponse,
    response_model=ImageRead,
)
async def get_image(
    image_id: uuid.UUID,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageProtocol = Depends(get_storage),
):
    """Get image metadata with a signed download URL."""
    image = await crud.get_image_by_id(db, image_id, current_user.id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    download_url = await storage.get_download_url(image.storage_key)
    image.url = download_url
    return image
@router.delete(
    "/images/{image_id}",
    status_code=204,
)
async def delete_image(
    image_id: uuid.UUID,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageProtocol = Depends(get_storage),
):
    """Delete an image from storage and database."""
    image = await crud.get_image_by_id(db, image_id, current_user.id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        await storage.delete(image.storage_key)
    except Exception:
        pass
    try:
        await crud.delete_image(db, image_id, current_user.id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")
---
Part 6: Configuration Updates
Update foreman/main.py
Add import:
from foreman.api.v1.endpoints import generations, images, projects, users
Add router registration:
app.include_router(images.router, prefix="/v1", tags=["images"])
Update .env.foreman.example
# Cloudflare R2 Storage
STORAGE_PROVIDER=r2
R2_ENDPOINT=https://<account>.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=your_access_key
R2_SECRET_ACCESS_KEY=your_secret_key
R2_BUCKET=foreman-images
R2_PUBLIC_URL=https://storage.yourdomain.com  # optional
---
## Part 7: Tests (Reference Only)
See `tests/test_projects.py` for the pattern to follow. Tests would include:
- List images (empty/populated)
- Create upload intent
- Get by ID (found/not found)
- Delete
- Ownership checks
- Unauthenticated access
---
Dependencies to Add
Add to pyproject.toml:
boto3 = "^1.34"
botocore = "^1.34"
---