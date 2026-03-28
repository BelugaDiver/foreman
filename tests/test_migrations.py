"""Tests for database migrations."""

from __future__ import annotations

# Stdlib
import importlib
import pkgutil
import re  # noqa: F401 - needed for Task 4 (SQL syntax tests)
from pathlib import Path

# Third-party
import sqlparse  # noqa: F401 - needed for Task 4 (SQL syntax tests)


def _get_migration_modules():
    """Yield all migration modules from migrations/versions."""
    versions_path = Path(__file__).parent.parent / "migrations" / "versions"
    for module_info in pkgutil.iter_modules([str(versions_path)]):
        module = importlib.import_module(f"migrations.versions.{module_info.name}")
        yield module


class TestMigrationStructure:
    """Tests for migration file structure."""

    def test_all_migrations_can_be_imported(self):
        """All migration files should be importable without errors."""
        for module in _get_migration_modules():
            # Just importing should work; if it fails, pytest will show it
            assert module is not None

    def test_all_migrations_have_upgrade_and_downgrade(self):
        """Each migration should define both upgrade and downgrade functions."""
        for module in _get_migration_modules():
            assert hasattr(module, "upgrade"), f"{module.__name__} missing upgrade"
            assert hasattr(module, "downgrade"), f"{module.__name__} missing downgrade"
            assert callable(module.upgrade), f"{module.__name__}.upgrade not callable"
            assert callable(module.downgrade), f"{module.__name__}.downgrade not callable"

    def test_all_migrations_have_revision_id(self):
        """Each migration should define a revision identifier."""
        for module in _get_migration_modules():
            assert hasattr(module, "revision"), f"{module.__name__} missing revision"
            assert module.revision is not None

    def test_all_migrations_have_down_revision(self):
        """Each migration should define a down_revision (or None for first)."""
        for module in _get_migration_modules():
            assert hasattr(module, "down_revision"), f"{module.__name__} missing down_revision"
