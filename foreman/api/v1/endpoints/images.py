"""Image management endpoints."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query

from foreman.api.deps import get_current_user, get_db
from foreman.audit import AuditEvent, log_audit
from foreman.db import Database
from foreman.logging_config import get_logger
from foreman.models.user import User
from foreman.repositories import postgres_images_repository as crud
from foreman.repositories import postgres_projects_repository as project_crud
from foreman.schemas.image import ImageCreate, ImageRead, ImageUploadIntent, ImageUploadRequest
from foreman.storage import StorageProtocol, get_storage_sync

router = APIRouter()
logger = get_logger("foreman.endpoints.images")


async def get_storage() -> StorageProtocol:
    """Dependency for injecting storage backend."""
    return get_storage_sync()


@router.post(
    "/projects/{project_id}/images",
    status_code=201,
    response_model=ImageUploadIntent,
)
async def create_upload_intent(
    project_id: uuid.UUID,
    request: ImageUploadRequest,
    db: Database = Depends(get_db),
    current_user: User = Depends(get_current_user),
    storage: StorageProtocol = Depends(get_storage),
):
    """Create an upload intent and return a presigned URL for direct upload to R2."""
    project = await project_crud.get_project_by_id(db, project_id, current_user.id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    logger.info(
        "Creating upload intent",
        extra={
            "project_id": str(project_id),
            "filename": request.filename,
            "content_type": request.content_type,
        },
    )

    intent = await storage.create_upload_url(request.filename, request.content_type, project_id)

    image_in = ImageCreate(
        project_id=project_id,
        user_id=current_user.id,
        filename=request.filename,
        content_type=request.content_type,
        size_bytes=request.size_bytes,
        storage_key=intent.file_key,
    )

    try:
        image = await crud.create_image(db, image_in, url=None)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

    logger.info(
        "Upload intent created",
        extra={
            "image_id": str(image.id),
            "project_id": str(project_id),
        },
    )

    return ImageUploadIntent(
        upload_url=intent.upload_url,
        image_id=image.id,
        file_key=intent.file_key,
        expires_at=intent.expires_at,
    )


@router.get(
    "/projects/{project_id}/images",
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

    logger.debug(
        "Listing images",
        extra={
            "project_id": str(project_id),
            "user_id": str(current_user.id),
            "limit": limit,
            "offset": offset,
        },
    )

    images = await crud.list_images(db, project_id, current_user.id, limit, offset)
    return images


@router.get(
    "/images/{image_id}",
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

    logger.info(
        "Image retrieved",
        extra={"image_id": str(image_id), "user_id": str(current_user.id)},
    )

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
        logger.warning(
            "Storage delete failed, proceeding with DB delete",
            extra={"image_id": str(image_id), "storage_key": image.storage_key},
            exc_info=True,
        )

    try:
        await crud.delete_image(db, image_id, current_user.id)
    except Exception:
        raise HTTPException(status_code=500, detail="Internal server error")

    log_audit(
        AuditEvent.IMAGE_DELETED,
        str(current_user.id),
        resource_id=str(image_id),
        resource_type="image",
    )
    logger.info("Image deleted", extra={"image_id": str(image_id)})
