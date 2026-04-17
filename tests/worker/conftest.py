"""Worker tests configuration."""

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


def pytest_sessionstart(session):
    """Set up mocks before any tests run."""
    # Create foreman as a namespace package
    foreman_pkg = ModuleType("foreman")
    foreman_pkg.__path__ = []
    sys.modules["foreman"] = foreman_pkg

    # Create submodules as proper modules
    for submod_name in [
        "foreman.logging_config",
        "foreman.context",
        "foreman.db",
        "foreman.queue",
        "foreman.queue.settings",
        "foreman.telemetry",
        "foreman.telemetry.setup_telemetry",
        "foreman.repositories",
        "foreman.repositories.postgres_generations_repository",
        "foreman.schemas",
        "foreman.schemas.generation",
    ]:
        mod = ModuleType(submod_name)
        sys.modules[submod_name] = mod

    # Set up attributes on logging_config
    logging_mod = sys.modules["foreman.logging_config"]
    logging_mod.get_logger = MagicMock(return_value=MagicMock())
    logging_mod.configure_logging = MagicMock()
    logging_mod.CorrelationIdFilter = type(
        "CorrelationIdFilter", (), {"filter": lambda self, record: True}
    )

    # External mocks (includes boto3/botocore for test_basic compatibility)
    for module_name, mock_module in [
        ("google", MagicMock()),
        ("google.genai", MagicMock()),
        ("google.genai.types", MagicMock()),
        ("boto3", MagicMock()),
        ("botocore", MagicMock()),
        ("botocore.config", MagicMock()),
        ("opentelemetry", MagicMock()),
        ("opentelemetry.trace", MagicMock()),
    ]:
        sys.modules[module_name] = mock_module


def pytest_sessionfinish(session, exitstatus):
    """Clean up mocks after all tests run."""
    modules_to_remove = [
        k
        for k in list(sys.modules.keys())
        if k.startswith("google")
        or k.startswith("botocore")
        or k.startswith("boto3")
        or k.startswith("opentelemetry")
        or k.startswith("foreman")
        or k.startswith("worker")
    ]
    for mod in modules_to_remove:
        del sys.modules[mod]
