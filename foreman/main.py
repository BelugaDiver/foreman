"""Main FastAPI application."""
from fastapi import FastAPI, Depends
from foreman.dependencies import get_container, DependencyContainer
from foreman.services import ImageService, DefaultImageService
from foreman.routes import router


def setup_dependencies(container: DependencyContainer) -> None:
    """Register all dependencies in the container."""
    # Register ImageService with its default implementation
    container.register(ImageService, DefaultImageService, singleton=True)


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="Foreman",
        description="Event-driven backend for managing image-generation requests for AI models",
        version="0.1.0",
    )
    
    # Set up dependencies
    setup_dependencies(get_container())
    
    # Include routers
    app.include_router(router)
    
    @app.get("/health")
    async def health_check():
        """Health check endpoint."""
        return {"status": "healthy"}
    
    @app.get("/")
    async def root():
        """Root endpoint."""
        return {
            "service": "Foreman",
            "description": "Event-driven backend for managing image-generation requests for AI models"
        }
    
    return app


# Create app instance
app = create_app()


def get_dependency_container() -> DependencyContainer:
    """FastAPI dependency to get the container instance."""
    return get_container()
