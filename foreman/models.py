"""Data models for Foreman API."""

from pydantic import BaseModel


class HealthCheck(BaseModel):
    """Health check response."""

    status: str = "healthy"
    version: str = "0.1.0"
    service: str = "foreman"
