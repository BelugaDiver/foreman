"""Example service demonstrating dependency injection pattern."""
from abc import ABC, abstractmethod


class ImageService(ABC):
    """Abstract base class for image services."""
    
    @abstractmethod
    def get_status(self) -> dict:
        """Get the status of the image service."""
        pass


class DefaultImageService(ImageService):
    """Default implementation of ImageService."""
    
    def get_status(self) -> dict:
        """Get the status of the image service."""
        return {
            "service": "DefaultImageService",
            "status": "ready",
            "queue_size": 0
        }
