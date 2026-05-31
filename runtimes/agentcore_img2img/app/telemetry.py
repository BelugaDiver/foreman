from __future__ import annotations

import logging
from typing import Any

from opentelemetry import trace

LOGGER = logging.getLogger("agentcore.runtime")


def emit_runtime_event(event: str, **fields: Any) -> None:
    """Emit structured runtime event fields for audit and operations."""

    span = trace.get_current_span()
    if span is not None:
        for key, value in fields.items():
            if value is not None:
                span.set_attribute(f"runtime.{key}", str(value))
        span.add_event(event)

    log_fields = {"event": event, **{k: v for k, v in fields.items() if v is not None}}
    LOGGER.info("runtime_event", extra=log_fields)
