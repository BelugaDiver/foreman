"""Example routes demonstrating dependency injection."""
from fastapi import APIRouter, Depends
from foreman.dependencies import DependencyContainer, get_container
from foreman.services import ImageService


router = APIRouter(prefix="/api", tags=["api"])


def get_image_service(
    container: DependencyContainer = Depends(get_container)
) -> ImageService:
    """FastAPI dependency to get the ImageService."""
    return container.resolve(ImageService)


@router.get("/status")
async def get_service_status(
    image_service: ImageService = Depends(get_image_service)
):
    """Get the status of image service through dependency injection."""
    return image_service.get_status()
