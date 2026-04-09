"""Worker tests configuration."""

import sys

import pytest


def pytest_sessionfinish(session, exitstatus):
    """Clean up sys.modules after worker tests to prevent pollution."""
    modules_to_remove = [
        k
        for k in sys.modules.keys()
        if k.startswith("google")
        or k.startswith("botocore")
        or k.startswith("boto3")
        or k.startswith("opentelemetry")
    ]
    for mod in modules_to_remove:
        if mod in sys.modules:
            del sys.modules[mod]

    # Also remove foreman mocks
    modules_to_remove = [
        k for k in sys.modules.keys() if k.startswith("foreman") or k.startswith("worker")
    ]
    for mod in modules_to_remove:
        if mod in sys.modules:
            del sys.modules[mod]


import sys
