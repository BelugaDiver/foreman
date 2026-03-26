"""Centralized logging configuration for Foreman."""

import logging
import os
import sys

from pythonjsonlogger import jsonlogger


class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        from foreman.context import get_correlation_id

        record.correlation_id = get_correlation_id() or "-"
        return True


def configure_logging() -> None:
    """Configure logging based on LOG_FORMAT environment variable."""
    use_json = os.getenv("LOG_FORMAT", "text").lower() == "json"

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if use_json:
        formatter = jsonlogger.JsonFormatter(
            "%(asctime)s %(name)s %(levelname)s %(message)s %(correlation_id)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s [cid:%(correlation_id)s]",
        )

    if root_logger.handlers:
        for handler in root_logger.handlers:
            if not any(isinstance(f, CorrelationIdFilter) for f in handler.filters):
                handler.addFilter(CorrelationIdFilter())
            if not handler.formatter:
                handler.setFormatter(formatter)
    else:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(formatter)
        root_logger.addHandler(handler)

    logging.getLogger("foreman").setLevel(logging.INFO)
    logging.getLogger("foreman.http").setLevel(logging.INFO)
    logging.getLogger("foreman.audit").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with correlation ID filter."""
    logger = logging.getLogger(name)
    if not any(isinstance(f, CorrelationIdFilter) for f in logger.filters):
        logger.addFilter(CorrelationIdFilter())
    return logger
