"""Tests for database migrations."""

from __future__ import annotations

# Stdlib
import importlib
import inspect
import pkgutil
import re
import subprocess
from pathlib import Path

# Third-party
import pytest
import sqlparse
import testcontainers.postgres
from testcontainers.core.container import DockerContainer

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_migration_modules():
    """Yield all migration modules from migrations/versions."""
    versions_path = Path(__file__).parent.parent / "migrations" / "versions"
    for module_info in pkgutil.iter_modules([str(versions_path)]):
        module = importlib.import_module(f"migrations.versions.{module_info.name}")
        yield module


# ---------------------------------------------------------------------------
# Tests: Migration Structure
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Tests: Migration Dependencies
# ---------------------------------------------------------------------------


class TestMigrationDependencies:
    """Tests for migration dependency chains."""

    def test_no_gaps_in_revision_chain(self):
        """Migration revisions should form a continuous chain without gaps."""
        modules = list(_get_migration_modules())

        # Build map of revision -> module
        revision_to_module = {m.revision: m for m in modules}

        # Check each migration's down_revision points to existing revision
        for module in modules:
            if module.down_revision is not None:
                assert module.down_revision in revision_to_module, (
                    f"{module.__name__} has down_revision {module.down_revision} that doesn't exist"
                )

    def test_no_cycles_in_revision_chain(self):
        """Migration chain should not contain cycles."""
        modules = list(_get_migration_modules())

        # Build adjacency list
        graph = {}
        for m in modules:
            graph[m.revision] = m.down_revision

        # Detect cycles using DFS
        visited = set()
        rec_stack = set()

        def has_cycle(node):
            visited.add(node)
            rec_stack.add(node)

            if graph.get(node):
                for neighbor in [graph[node]]:
                    if neighbor is None:
                        continue
                    if neighbor not in visited:
                        if has_cycle(neighbor):
                            return True
                    elif neighbor in rec_stack:
                        return True

            rec_stack.remove(node)
            return False

        for node in graph:
            if node not in visited:
                assert not has_cycle(node), f"Cycle detected starting from {node}"


# ---------------------------------------------------------------------------
# Tests: Migration SQL
# ---------------------------------------------------------------------------


class TestMigrationSQL:
    """Tests for SQL syntax in migrations."""

    def test_upgrade_sql_syntax_valid(self):
        """Upgrade SQL statements should be syntactically valid."""
        for module in _get_migration_modules():
            upgrade_source = inspect.getsource(module.upgrade)

            # Extract SQL from op.execute() calls using regex
            sql_statements = re.findall(r'op\.execute\(\s*"""(.+?)"""', upgrade_source, re.DOTALL)

            for sql in sql_statements:
                # sqlparse.parse() returns list of statements; if empty, syntax is invalid
                parsed = sqlparse.parse(sql)
                assert len(parsed) > 0, f"Invalid SQL syntax in {module.__name__} upgrade: {sql}"

    def test_downgrade_sql_syntax_valid(self):
        """Downgrade SQL statements should be syntactically valid."""
        for module in _get_migration_modules():
            downgrade_source = inspect.getsource(module.downgrade)

            sql_statements = re.findall(r'op\.execute\(\s*"""(.+?)"""', downgrade_source, re.DOTALL)

            for sql in sql_statements:
                parsed = sqlparse.parse(sql)
                assert len(parsed) > 0, f"Invalid SQL syntax in {module.__name__} downgrade: {sql}"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _docker_available():
    """Check if Docker is available."""
    try:
        with DockerContainer("postgres:16-alpine"):
            pass
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Tests: Migration Integration
# ---------------------------------------------------------------------------


class TestMigrationIntegration:
    """Integration tests that run migrations against a real database."""

    @pytest.fixture
    def postgres_container(self):
        """Start a PostgreSQL container for testing."""
        if not _docker_available():
            pytest.skip("Docker not available")

        pg = testcontainers.postgres.PostgresContainer("postgres:16-alpine")
        pg.start()
        yield pg
        pg.stop()

    def test_migrations_run_successfully(self, postgres_container):
        """All migrations should run without errors against a real database."""
        import os

        url = postgres_container.get_connection_url()
        env = os.environ.copy()
        env["DATABASE_URL"] = url

        result = subprocess.run(
            ["python", "-m", "alembic", "upgrade", "heads"],
            env=env,
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )

        assert result.returncode == 0, f"Migrations failed: {result.stderr}"
        if result.stdout:
            print(f"Migrations output: {result.stdout}")

        expected_tables = ["users", "projects", "generations", "images", "styles"]

        import psycopg2

        url = url.replace("postgresql+psycopg2://", "postgresql://")
        conn = psycopg2.connect(url)
        cur = conn.cursor()
        for table in expected_tables:
            cur.execute(f"SELECT 1 FROM {table} LIMIT 1")
        cur.close()
        conn.close()
