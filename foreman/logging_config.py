"""Centralized logging configuration for Foreman."""

import logging

from pythonjsonlogger.json import JsonFormatter


class CorrelationIdFilter(logging.Filter):
    """Add correlation ID to all log records."""

    def filter(self, record: logging.LogRecord) -> bool:
        from foreman.context import get_correlation_id

        record.correlation_id = get_correlation_id() or "-"
        return True


def configure_logging() -> None:
    """Configure logging based on LOG_FORMAT environment variable."""
    root_logger = logging.getLogger()

    json_formatter = JsonFormatter(
        fmt="%(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )

    # Configure existing handlers without duplicates
    for handler in root_logger.handlers:
        if not any(isinstance(f, CorrelationIdFilter) for f in handler.filters):
            handler.addFilter(CorrelationIdFilter())
        if handler.formatter is None:
            handler.setFormatter(json_formatter)

    # Ensure root logger has at least one handler with our config
    if not root_logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(json_formatter)
        handler.addFilter(CorrelationIdFilter())
        root_logger.addHandler(handler)

    root_logger.setLevel(logging.INFO)

    logging.getLogger("foreman").setLevel(logging.INFO)
    logging.getLogger("foreman.http").setLevel(logging.INFO)
    logging.getLogger("foreman.audit").setLevel(logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Get a logger instance with correlation ID filter."""
    logger = logging.getLogger(name)
    if not any(isinstance(f, CorrelationIdFilter) for f in logger.filters):
        logger.addFilter(CorrelationIdFilter())
    return logger
