"""Worker tests configuration — module-level mock installation."""

import sys
from types import ModuleType
from unittest.mock import MagicMock

import pytest


def _install_mocks() -> None:
    """Install sys.modules stubs for external and foreman dependencies.

    Called at import time so that mocks are present before any worker.*
    module is imported during pytest collection.
    """
    # Create foreman as a namespace package
    foreman_pkg = ModuleType("foreman")
    foreman_pkg.__path__ = []
    sys.modules.setdefault("foreman", foreman_pkg)

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
        if submod_name not in sys.modules:
            mod = ModuleType(submod_name)
            sys.modules[submod_name] = mod

    # Set up attributes on logging_config
    logging_mod = sys.modules["foreman.logging_config"]
    if not hasattr(logging_mod, "get_logger"):
        logging_mod.get_logger = MagicMock(return_value=MagicMock())
        logging_mod.configure_logging = MagicMock()
        logging_mod.CorrelationIdFilter = type(
            "CorrelationIdFilter", (), {"filter": lambda self, record: True}
        )

    for module_name in [
        "google",
        "google.genai",
        "google.genai.types",
        "boto3",
        "botocore",
        "botocore.config",
        "opentelemetry",
        "opentelemetry.trace",
    ]:
        sys.modules.setdefault(module_name, MagicMock())


# Install mocks at import time — this runs before any worker.* module is
# imported during collection, regardless of conftest loading order.
_install_mocks()


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
