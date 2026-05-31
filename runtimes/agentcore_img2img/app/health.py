from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class HealthStatus:
    """Health response model used by /ping endpoint."""

    status: str
    dependency_status: str


def get_health_status(dependency_ok: bool = True) -> HealthStatus:
    """Return process and dependency-aware health state."""

    if dependency_ok:
        return HealthStatus(status="Healthy", dependency_status="ok")
    return HealthStatus(status="Degraded", dependency_status="dependency_error")
