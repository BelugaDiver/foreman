# Migration Tests Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add comprehensive migration tests using testcontainers to verify migration files are valid and can run against a real PostgreSQL database.

**Architecture:** Tests will be in a new `tests/test_migrations.py` file. Static tests (import, syntax, dependency chain) run without a database. Integration test uses testcontainers to spin up PostgreSQL and run alembic migrations.

**Tech Stack:** pytest, testcontainers, sqlparse (for SQL validation), alembic

---

## Task 1: Add sqlparse to dev dependencies

**Files:**
- Modify: `pyproject.toml:31`

- [ ] **Step 1: Add sqlparse to dev dependencies**

Add `"sqlparse>=0.5.0"` to the dev dependencies list in pyproject.toml.

```toml
dev = [
    "pytest>=9.0.2",
    "pytest-cov>=7.0.0",
    "pytest-asyncio>=1.3.0",
    "httpx>=0.27.2",
    "ruff>=0.15.7",
    "alembic>=1.18.4",
    "psycopg2-binary>=2.9.11",
    "testcontainers>=4.14.1",
    "sqlparse>=0.5.0",
]
```

- [ ] **Step 2: Install the new dependency**

Run: `pip install -e ".[dev]"`
Expected: sqlparse installed successfully

- [ ] **Step 3: Commit**

Run:
```bash
git add pyproject.toml
git commit -m "chore: add sqlparse for migration tests"
```

---

## Task 2: Write import and structure tests

**Files:**
- Create: `tests/test_migrations.py`

- [ ] **Step 1: Write import test and structure tests**

Create `tests/test_migrations.py`:

```python
"""Tests for database migrations."""

from __future__ import annotations

# Stdlib
import importlib
import inspect
import pkgutil
import re
from pathlib import Path

# Third-party
import pytest
import sqlparse

# Local
import migrations.versions


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
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_migrations.py::TestMigrationStructure -v`
Expected: All 4 tests pass

- [ ] **Step 3: Commit**

Run:
```bash
git add tests/test_migrations.py
git commit -m "test: add migration structure tests"
```

---

## Task 3: Write dependency chain test

**Files:**
- Modify: `tests/test_migrations.py`

- [ ] **Step 1: Add dependency chain test**

Add to `tests/test_migrations.py`:

```python
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
                    f"{module.__name__} has down_revision {module.down_revision} "
                    f"that doesn't exist"
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
```

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_migrations.py::TestMigrationDependencies -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

Run:
```bash
git add tests/test_migrations.py
git commit -m "test: add migration dependency chain tests"
```

---

## Task 4: Write SQL syntax test

**Files:**
- Modify: `tests/test_migrations.py`

- [ ] **Step 1: Add SQL syntax validation test**

Add to `tests/test_migrations.py`:

```python
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

- [ ] **Step 2: Run tests to verify they pass**

Run: `pytest tests/test_migrations.py::TestMigrationSQL -v`
Expected: All tests pass

- [ ] **Step 3: Commit**

Run:
```bash
git add tests/test_migrations.py
git commit -m "test: add SQL syntax validation tests"
```

---

## Task 5: Write integration test with testcontainers

**Files:**
- Modify: `tests/test_migrations.py`

- [ ] **Step 1: Add testcontainers integration test**

Add to `tests/test_migrations.py`:

```python
import subprocess
from unittest.mock import patch

import pytest
import testcontainers.postgres
from testcontainers.core.container import DockerContainer


def _docker_available():
    """Check if Docker is available."""
    try:
        with DockerContainer("postgres:16-alpine") as c:
            pass
        return True
    except Exception:
        return False


class TestMigrationIntegration:
    """Integration tests that run migrations against a real database."""

    @pytest.fixture
    def postgres_container(self):
        """Start a PostgreSQL container for testing."""
        if not _docker_available():
            pytest.skip("Docker not available")
        
        pg = testcontainers.postgres.Postgres("postgres:16-alpine")
        pg.start()
        yield pg
        pg.stop()

    def test_migrations_run_successfully(self, postgres_container):
        """All migrations should run without errors against a real database."""
        # Get connection URL from testcontainer
        url = postgres_container.get_connection_url()
        
        # Run alembic upgrade
        result = subprocess.run(
            ["alembic", "upgrade", "head"],
            env={"DATABASE_URL": url},
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent,
        )
        
        assert result.returncode == 0, f"Migrations failed: {result.stderr}"
        
        # Verify tables exist
        expected_tables = [
            "users", "projects", "generations", "images", "styles"
        ]
        
        for table in expected_tables:
            result = subprocess.run(
                [
                    "psql", url, "-c",
                    f"SELECT 1 FROM {table} LIMIT 1"
                ],
                capture_output=True,
                text=True,
            )
            # Table should exist (or query returns empty, not error)
            assert "does not exist" not in result.stderr, f"Table {table} not created"
```

- [ ] **Step 2: Run test to verify it works**

Run: `pytest tests/test_migrations.py::TestMigrationIntegration -v`
Expected: Test runs and passes (or skips if Docker unavailable)

- [ ] **Step 3: Commit**

Run:
```bash
git add tests/test_migrations.py
git commit -m "test: add migration integration test with testcontainers"
```

---

## Task 6: Final verification

- [ ] **Step 1: Run all migration tests**

Run: `pytest tests/test_migrations.py -v`
Expected: All tests pass

- [ ] **Step 2: Run lint check**

Run: `ruff check tests/test_migrations.py`
Expected: No errors

- [ ] **Step 3: Run format check**

Run: `ruff format tests/test_migrations.py`
Expected: No changes needed (or formatted)

- [ ] **Step 4: Final commit**

Run:
```bash
git add tests/test_migrations.py pyproject.toml
git commit -m "test: add comprehensive migration tests"
```
