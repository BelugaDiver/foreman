"""Main FastAPI application for Foreman."""

import logging
import os
from contextlib import asynccontextmanager
from typing import Dict, List
from uuid import UUID

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware

from foreman import __version__
from foreman.models import (
    HealthCheck,
    ImageGenerationRequest,
    ImageGenerationResponse,
    RequestStatus,
)
from foreman.telemetry import instrument_app, setup_telemetry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# In-memory storage for demo purposes
# WARNING: This is not suitable for production use:
# - Data is lost on application restart
# - Not safe for concurrent access across multiple workers
# - Does not scale across multiple instances
# For production, use a proper database (PostgreSQL, MongoDB, etc.)
requests_store: Dict[UUID, ImageGenerationRequest] = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting Foreman service...")
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    # In production, set OTEL_EXPORTER_OTLP_INSECURE=false for secure connections
    insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"
    setup_telemetry(service_name="foreman", otlp_endpoint=otlp_endpoint, insecure=insecure)
    instrument_app(app)
    logger.info("Foreman service started successfully")
    yield
    # Shutdown
    logger.info("Shutting down Foreman service...")


# Create FastAPI app
app = FastAPI(
    title="Foreman",
    description="Event-driven backend for managing image-generation requests for AI models",
    version=__version__,
    lifespan=lifespan,
)

# Add CORS middleware
# WARNING: allow_origins=["*"] is not secure for production
# Configure CORS_ORIGINS environment variable with specific domains in production
allowed_origins = os.getenv("CORS_ORIGINS", "*").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/", response_model=HealthCheck)
async def root() -> HealthCheck:
    """Root endpoint with health check."""
    return HealthCheck(version=__version__)


@app.get("/health", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    """Health check endpoint."""
    return HealthCheck(version=__version__)


@app.post(
    "/requests",
    response_model=ImageGenerationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_request(request: ImageGenerationRequest) -> ImageGenerationResponse:
    """
    Create a new image generation request.

    This endpoint accepts a request to generate images based on a text prompt.
    The request is stored and can be tracked using its ID.
    """
    logger.info(f"Creating new image generation request: {request.prompt[:50]}...")
    requests_store[request.id] = request
    return ImageGenerationResponse(
        id=request.id,
        status=request.status,
        message="Request created successfully",
    )


@app.get("/requests", response_model=List[ImageGenerationRequest])
async def list_requests() -> List[ImageGenerationRequest]:
    """
    List all image generation requests.

    Returns a list of all requests in the system.
    """
    logger.info(f"Listing {len(requests_store)} requests")
    return list(requests_store.values())


@app.get("/requests/{request_id}", response_model=ImageGenerationRequest)
async def get_request(request_id: UUID) -> ImageGenerationRequest:
    """
    Get a specific image generation request by ID.

    Returns the details of a single request including its current status.
    """
    logger.info(f"Fetching request {request_id}")
    if request_id not in requests_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request {request_id} not found",
        )
    return requests_store[request_id]


@app.put("/requests/{request_id}/status", response_model=ImageGenerationResponse)
async def update_request_status(
    request_id: UUID, new_status: RequestStatus
) -> ImageGenerationResponse:
    """
    Update the status of an image generation request.

    This endpoint allows updating the status of a request (e.g., from pending to processing).
    """
    logger.info(f"Updating request {request_id} status to {new_status}")
    if request_id not in requests_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request {request_id} not found",
        )

    request = requests_store[request_id]
    request.status = new_status
    return ImageGenerationResponse(
        id=request.id,
        status=request.status,
        message=f"Request status updated to {new_status}",
    )


@app.delete("/requests/{request_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_request(request_id: UUID) -> None:
    """
    Delete an image generation request.

    Removes a request from the system.
    """
    logger.info(f"Deleting request {request_id}")
    if request_id not in requests_store:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Request {request_id} not found",
        )
    del requests_store[request_id]
