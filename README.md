# Foreman

Foreman is the event-driven backend for managing image-generation requests for AI models.

## Features

- **FastAPI Framework**: Modern, fast web framework for building APIs
- **Dependency Injection**: Clean interfaces for manageable dependency injection
- **Barebones Architecture**: Minimal setup with clear extension points

## Installation

Install dependencies using pip:

```bash
pip install -e .
```

Or with development dependencies:

```bash
pip install -e ".[dev]"
```

## Running the Application

Run the FastAPI application using uvicorn:

```bash
uvicorn foreman.main:app --reload
```

The application will be available at `http://localhost:8000`.

## API Documentation

FastAPI automatically generates interactive API documentation:

- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

## Endpoints

- `GET /`: Root endpoint with service information
- `GET /health`: Health check endpoint
- `GET /api/status`: Example endpoint demonstrating dependency injection

## Dependency Injection

The application uses a simple dependency injection container for managing services.

### Registering Dependencies

In `foreman/main.py`, dependencies are registered in the `setup_dependencies` function:

```python
def setup_dependencies(container: DependencyContainer) -> None:
    """Register all dependencies in the container."""
    container.register(ImageService, DefaultImageService, singleton=True)
```

### Using Dependencies in Routes

Dependencies are injected into route handlers using FastAPI's dependency injection:

```python
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
```

### Creating New Services

1. Define an abstract interface in `foreman/services.py`:

```python
class MyService(ABC):
    @abstractmethod
    def my_method(self) -> dict:
        pass
```

2. Create a concrete implementation:

```python
class MyServiceImpl(MyService):
    def my_method(self) -> dict:
        return {"result": "success"}
```

3. Register it in `setup_dependencies`:

```python
container.register(MyService, MyServiceImpl, singleton=True)
```

4. Use it in routes with dependency injection:

```python
def get_my_service(
    container: DependencyContainer = Depends(get_container)
) -> MyService:
    return container.resolve(MyService)
```

## Testing

Run tests using pytest:

```bash
pytest
```

## Architecture

```
foreman/
├── __init__.py          # Package exports
├── main.py              # FastAPI application and setup
├── dependencies.py      # Dependency injection container
├── services.py          # Service interfaces and implementations
└── routes.py            # API route handlers
```

