"""Main FastAPI application for Foreman."""

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from foreman import __version__
from foreman.api.v1.endpoints import generations, projects, users
from foreman.db import Database, DatabaseSettings
from foreman.repositories import postgres_users_repository as crud
from foreman.schemas.health_check import HealthCheck
from foreman.telemetry import instrument_app, setup_telemetry

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler."""
    # Startup
    logger.info("Starting Foreman service...")
    otlp_endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT")
    # In production, set OTEL_EXPORTER_OTLP_INSECURE=false for secure connections
    insecure = os.getenv("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"
    setup_telemetry(
        service_name="foreman",
        service_version=__version__,
        otlp_endpoint=otlp_endpoint,
        insecure=insecure,
    )
    database = Database(DatabaseSettings.from_env())
    app.state.database = database
    await database.startup()
    if os.getenv("DEV_MODE", "false").lower() == "true":
        try:
            dev_user = await crud.ensure_dev_user(database)
            logger.info("Dev test user ready: id=%s email=%s", dev_user.id, dev_user.email)
        except Exception:
            logger.warning("Could not seed dev test user", exc_info=True)
    logger.info("Foreman service started successfully")
    try:
        yield
    finally:
        # Shutdown
        logger.info("Shutting down Foreman service...")
        try:
            await database.shutdown()
        except Exception:
            logger.exception("Error while shutting down database")


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
instrument_app(app)

# Include API routers
app.include_router(users.router, prefix="/v1/users", tags=["users"])
app.include_router(projects.router, prefix="/v1/projects", tags=["projects"])
app.include_router(generations.router, prefix="/v1/generations", tags=["generations"])


@app.get("/", response_model=HealthCheck)
async def root() -> HealthCheck:
    """Root endpoint with health check."""
    return HealthCheck(version=__version__)


@app.get("/health", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    """Health check endpoint."""
    return HealthCheck(version=__version__)
