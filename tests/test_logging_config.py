"""Tests for logging configuration."""

import logging
import os
from unittest.mock import MagicMock, patch

from foreman.logging_config import (
    CorrelationIdFilter,
    configure_logging,
    get_logger,
)


def test_configure_logging_json_format():
    """configure_logging should use JsonFormatter when LOG_FORMAT=json."""
    with patch.dict(os.environ, {"LOG_FORMAT": "json"}):
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers.copy()
        root_logger.handlers.clear()

        try:
            configure_logging()

            assert len(root_logger.handlers) > 0
            handler = root_logger.handlers[0]
            from pythonjsonlogger.json import JsonFormatter

            assert isinstance(handler.formatter, JsonFormatter)
        finally:
            root_logger.handlers = original_handlers


def test_configure_logging_no_existing_handlers():
    """configure_logging should create new handler when none exist."""
    with patch.dict(os.environ, {"LOG_FORMAT": "text"}):
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers.copy()
        root_logger.handlers.clear()

        try:
            configure_logging()

            assert len(root_logger.handlers) > 0
        finally:
            root_logger.handlers = original_handlers


def test_configure_logging_with_existing_handlers_no_filter():
    """configure_logging should add filter to existing handlers."""
    with patch.dict(os.environ, {"LOG_FORMAT": "text"}):
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers.copy()
        root_logger.handlers.clear()

        handler = logging.StreamHandler(MagicMock())
        root_logger.handlers = [handler]

        try:
            configure_logging()

            assert any(isinstance(f, CorrelationIdFilter) for f in handler.filters)
        finally:
            root_logger.handlers = original_handlers


def test_configure_logging_with_existing_handler_no_formatter():
    """configure_logging should set formatter on existing handler."""
    with patch.dict(os.environ, {"LOG_FORMAT": "text"}):
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers.copy()
        root_logger.handlers.clear()

        handler = logging.StreamHandler(MagicMock())
        handler.formatter = None
        root_logger.handlers = [handler]

        try:
            configure_logging()

            assert handler.formatter is not None
        finally:
            root_logger.handlers = original_handlers


def test_get_logger_adds_filter():
    """get_logger should add CorrelationIdFilter if not present."""
    with patch.dict(os.environ, {"LOG_FORMAT": "text"}):
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers.copy()
        root_logger.handlers.clear()

        handler = logging.StreamHandler(MagicMock())
        root_logger.handlers = [handler]

        try:
            configure_logging()

            logger = get_logger("test.logger")
            assert any(isinstance(f, CorrelationIdFilter) for f in logger.filters)
        finally:
            root_logger.handlers = original_handlers


def test_correlation_id_filter():
    """CorrelationIdFilter should add correlation_id to records."""
    with patch.dict(os.environ, {"LOG_FORMAT": "text"}):
        root_logger = logging.getLogger()
        original_handlers = root_logger.handlers.copy()
        root_logger.handlers.clear()

        try:
            configure_logging()

            with patch("foreman.context.get_correlation_id", return_value="test-correlation-id"):
                filter_obj = CorrelationIdFilter()
                record = logging.LogRecord(
                    name="test",
                    level=logging.INFO,
                    pathname="test.py",
                    lineno=1,
                    msg="test",
                    args=(),
                    exc_info=None,
                )

                result = filter_obj.filter(record)
                assert result is True
                assert record.correlation_id == "test-correlation-id"
        finally:
            root_logger.handlers = original_handlers
