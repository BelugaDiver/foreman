"""Main FastAPI application for Foreman."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

from asyncpg import ConnectionFailureError, QueryCanceledError
from botocore.exceptions import ClientError, EndpointConnectionError
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from foreman import __version__
from foreman.api.v1.endpoints import generations, images, projects, styles, users
from foreman.db import Database, DatabaseSettings
from foreman.logging_config import configure_logging
from foreman.middleware.request_logging import RequestLoggingMiddleware
from foreman.repositories import postgres_users_repository as crud
from foreman.schemas.health_check import HealthCheck
from foreman.telemetry import instrument_app, setup_telemetry

configure_logging()
logger = logging.getLogger(__name__)
error_logger = logging.getLogger("foreman.errors")


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
app.add_middleware(RequestLoggingMiddleware)


async def connection_failure_handler(request: Request, exc: Exception):
    error_logger.exception(
        "Database connection failed",
        extra={"url": str(request.url), "method": request.method},
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database temporarily unavailable"},
    )


async def query_canceled_handler(request: Request, exc: Exception):
    error_logger.exception(
        "Database query cancelled",
        extra={"url": str(request.url), "method": request.method},
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Database temporarily unavailable"},
    )


async def timeout_error_handler(request: Request, exc: Exception):
    error_logger.exception(
        "Request timeout",
        extra={"url": str(request.url), "method": request.method},
    )
    return JSONResponse(
        status_code=503,
        content={"detail": "Service temporarily unavailable"},
    )


async def storage_error_handler(request: Request, exc: Exception):
    error_code = None
    if isinstance(exc, ClientError):
        try:
            error_code = exc.response.get("Error", {}).get("Code")  # type: ignore[union-attr]
        except Exception:
            error_code = None

    error_logger.exception(
        "Storage operation failed",
        extra={
            "url": str(request.url),
            "method": request.method,
            "error_type": type(exc).__name__,
            "error_code": error_code,
        },
    )

    transient_error_codes = {
        "SlowDown",
        "RequestTimeout",
        "InternalError",
        "ServiceUnavailable",
        "Throttling",
        "RequestLimitExceeded",
    }

    if error_code in transient_error_codes:
        status_code = 503
        detail = "Storage service temporarily unavailable"
    else:
        status_code = 500
        detail = "Storage service error"

    return JSONResponse(
        status_code=status_code,
        content={"detail": detail},
    )


app.add_exception_handler(ConnectionFailureError, connection_failure_handler)
app.add_exception_handler(QueryCanceledError, query_canceled_handler)
app.add_exception_handler(asyncio.TimeoutError, timeout_error_handler)
app.add_exception_handler(ClientError, storage_error_handler)
app.add_exception_handler(EndpointConnectionError, storage_error_handler)

# Include API routers
app.include_router(users.router, prefix="/v1/users", tags=["users"])
app.include_router(projects.router, prefix="/v1/projects", tags=["projects"])
app.include_router(generations.router, prefix="/v1/generations", tags=["generations"])
app.include_router(images.router, prefix="/v1", tags=["images"])
app.include_router(styles.router, prefix="/v1/styles", tags=["styles"])


@app.get("/", response_model=HealthCheck)
async def root() -> HealthCheck:
    """Root endpoint with health check."""
    return HealthCheck(version=__version__)


@app.get("/health", response_model=HealthCheck)
async def health_check() -> HealthCheck:
    """Health check endpoint."""
    return HealthCheck(version=__version__)
