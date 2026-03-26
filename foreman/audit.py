"""Audit logging for sensitive operations."""

import logging
from enum import Enum
from typing import Any, Optional

audit_logger = logging.getLogger("foreman.audit")


class AuditEvent(str, Enum):
    """Audit event types."""

    USER_CREATED = "user.created"
    USER_UPDATED = "user.updated"
    USER_DELETED = "user.deleted"
    PROJECT_CREATED = "project.created"
    PROJECT_UPDATED = "project.updated"
    PROJECT_DELETED = "project.deleted"
    GENERATION_CREATED = "generation.created"
    GENERATION_CANCELLED = "generation.cancelled"
    GENERATION_RETRY = "generation.retry"
    GENERATION_FORK = "generation.fork"
    GENERATION_DELETED = "generation.deleted"
    IMAGE_CREATED = "image.created"
    IMAGE_DELETED = "image.deleted"


def log_audit(
    event: AuditEvent,
    user_id: str,
    resource_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    **extra: Any,
) -> None:
    """Log an audit event.

    Args:
        event: The type of audit event
        user_id: The user performing the action
        resource_id: ID of the affected resource
        resource_type: Type of resource (project, generation, etc.)
        **extra: Additional context
    """
    audit_logger.info(
        f"Audit: {event.value}",
        extra={
            "audit_event": event.value,
            "user_id": user_id,
            "resource_id": str(resource_id) if resource_id else None,
            "resource_type": resource_type,
            **extra,
        },
    )
