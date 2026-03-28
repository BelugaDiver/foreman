# Migration Tests Design

## Overview

Add comprehensive migration tests using testcontainers to spin up a real PostgreSQL instance.

## Components

**New file:** `tests/test_migrations.py`

**Test cases:**

1. **Import test** — verify all migration files can be imported without errors
2. **SQL syntax test** — use `sqlparse` to validate SQL in migration files
3. **Dependency chain test** — verify `down_revision` references form a valid chain (no gaps, no cycles)
4. **Upgrade/downgrade structure test** — each migration has both functions
5. **Integration test** — use testcontainers to run all migrations against a real PostgreSQL, then verify tables exist

## Data Flow

```
test_migrations.py → testcontainers.postgres.Postgres() → run alembic upgrade → assert tables exist
```

## Testing Approach

- **Fast tests (1-4):** Run locally without DB
- **Integration test (5):** Uses testcontainers; skip locally if Docker unavailable, run on CI

## Error Handling

- If testcontainers fails to start (no Docker), skip integration test gracefully
- Catch SQL syntax errors early in static tests
