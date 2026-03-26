# Integration Tests Design

## Overview

Create integration tests that run against a real PostgreSQL database using testcontainers-python, with truncate tables for test isolation.

## Architecture

### Directory Structure

```
tests/
├── test_projects.py          # Existing unit tests (mocked)
├── test_users.py             # Existing unit tests
├── test_generations.py       # Existing unit tests
├── test_images.py            # Existing unit tests
├── test_styles.py            # Existing unit tests
├── conftest.py               # Shared fixtures for unit tests
└── integration/
    ├── __init__.py
    ├── conftest.py           # Shared fixtures (testcontainers, db setup)
    ├── test_projects.py      # Integration tests for projects
    ├── test_users.py         # Integration tests for users
    ├── test_generations.py   # Integration tests for generations
    ├── test_images.py        # Integration tests for images
    ├── test_styles.py        # Integration tests for styles
    └── test_health.py        # Health check integration tests
```

## Design Decisions

### 1. Test Database Setup

- **Library**: `testcontainers` (Python library for Docker containers)
- **Container**: `postgres:16-alpine` (matching production)
- **Scope**: Session-scoped fixture - starts postgres container once for entire test run
- **Migrations**: Run alembic migrations once at session start via subprocess

### 2. Truncate Tables Strategy

- After each test completes, truncate all tables to clean up data
- Use correct FK order (children before parents): generations, images, projects, users, styles
- This approach is compatible with the connection-per-operation architecture
- Simpler and more reliable than transaction rollback for this codebase
- Performance impact is minimal (truncate is fast)

### 3. Application Test Instance

- Create a test FastAPI app instance
- Disable default lifespan (we manage DB manually)
- Override the database dependency to use testcontainer connection
- Use same app instance across tests - truncate cleanup per test
- IMPORTANT: Ensure `DEV_MODE` is NOT set to avoid `ensure_dev_user()` running at startup

### 4. Fixtures Required

| Fixture | Scope | Purpose |
|---------|-------|---------|
| `postgres_container` | session | Starts/stops PostgreSQL container |
| `db_dsn` | session | Database connection string |
| `migrated_db` | session | Runs alembic migrations once |
| `db_pool` | session | asyncpg connection pool for tests |
| `test_app` | session | FastAPI app instance for testing |
| `client` | function | TestClient with auth headers |
| `test_user` | function | Creates a test user per test |
| `cleanup_tables` | function | Truncates all tables after each test |

### 5. Test User Management

- Create test users on-the-fly per test using the actual POST /v1/users endpoint
- Store user ID in fixture for use in auth headers
- Truncate tables after each test ensures users are cleaned up

### 6. Endpoint Dependency Chain

Integration tests must respect the dependency graph between resources:

```
User → Project → Generation
     → Image
     → Style (read-only, seeded)
```

**Helper functions to scaffold test data:**

```python
def create_user_via_api(client: TestClient) -> tuple[dict, dict]:
    """Create user via POST /v1/users and return (user_data, auth_headers)."""
    resp = client.post("/v1/users", json={
        "email": f"test-{uuid.uuid4().hex[:8]}@example.com",
        "password": "testpassword123",
        "full_name": "Test User"
    })
    assert resp.status_code == 201
    user = resp.json()
    return user, {"X-User-ID": user["id"]}


def create_project_via_api(client: TestClient, headers: dict, name: str = "Test Project", 
                          image_url: str = "https://example.com/image.jpg") -> dict:
    """Create project via POST /v1/projects/. Requires user first."""
    resp = client.post("/v1/projects/", headers=headers, json={
        "name": name,
        "original_image_url": image_url
    })
    assert resp.status_code == 201
    return resp.json()


def create_generation_via_api(client: TestClient, headers: dict, project_id: str,
                               prompt: str = "modern living room", 
                               style_id: str | None = None) -> dict:
    """Create generation via POST /v1/projects/{id}/generations. Requires project first."""
    resp = client.post(f"/v1/projects/{project_id}/generations", headers=headers, json={
        "prompt": prompt,
        "style_id": style_id,
        "model_used": "dalle-3",
        "attempt": 1
    })
    assert resp.status_code == 202
    return resp.json()


def create_image_via_api(client: TestClient, headers: dict, project_id: str) -> dict:
    """Create image via POST /v1/projects/{id}/images. Requires project first."""
    resp = client.post(f"/v1/projects/{project_id}/images", headers=headers, json={
        "filename": "test.jpg",
        "content_type": "image/jpeg",
        "size_bytes": 1024
    })
    # May return 201 or 500 depending on storage setup
    # For integration tests, we may mock storage
    return resp.json() if resp.status_code == 201 else None
```

**Test data scaffolding strategy:**

1. Each test that needs a user calls `create_user_via_api()`
2. Each test that needs a project calls `create_project_via_api()` (which internally ensures user exists)
3. Each test that needs a generation calls `create_generation_via_api()` (which internally ensures project exists)
4. This creates a natural dependency chain - tests fail fast if upstream data is missing

**Styles are read-only:** The styles table must be seeded before tests run. Add a session-scoped fixture that seeds default styles via direct DB insert (faster than API calls).

### 6. Running Integration Tests

```bash
# Run only integration tests
pytest tests/integration/ -v

# Run all tests (unit + integration)
pytest -v

# Run with coverage
pytest tests/integration/ --cov=foreman --cov-report=html
```

### 7. CI/CD Considerations

- Container starts once per test session (not per test)
- Transaction rollback is fast - minimal overhead
- Total overhead: ~5-10 seconds for container startup + migration
- Can run integration tests in parallel with unit tests

## Endpoints to Cover

### Users (4 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| POST | /v1/users | Register new user |
| GET | /v1/users/me | Get current user |
| PATCH | /v1/users/me | Update current user |
| DELETE | /v1/users/me | Soft delete current user |

### Projects (7 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| GET | /v1/projects/ | List user's projects |
| POST | /v1/projects/ | Create new project |
| GET | /v1/projects/{id} | Get project details |
| PATCH | /v1/projects/{id} | Update project |
| DELETE | /v1/projects/{id} | Delete project |
| POST | /v1/projects/{id}/generations | Create generation for project |
| GET | /v1/projects/{id}/generations | List generations for project |

### Generations (7 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| GET | /v1/generations/ | List all generations |
| GET | /v1/generations/{id} | Get generation details |
| PATCH | /v1/generations/{id} | Update generation |
| DELETE | /v1/generations/{id} | Delete generation |
| POST | /v1/generations/{id}/cancel | Cancel pending/processing generation |
| POST | /v1/generations/{id}/retry | Retry failed/cancelled generation |
| POST | /v1/generations/{id}/fork | Fork generation |

### Images (4 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| POST | /v1/projects/{id}/images | Create upload intent |
| GET | /v1/projects/{id}/images | List images for project |
| GET | /v1/images/{id} | Get image metadata |
| DELETE | /v1/images/{id} | Delete image |

### Styles (2 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| GET | /v1/styles/ | List all styles |
| GET | /v1/styles/{id} | Get style details |

### Health (2 endpoints)

| Method | Path | Description |
|--------|------|-------------|
| GET | / | Root health check |
| GET | /health | Health check endpoint |

## Test Scenarios Per Endpoint

### Mandatory Integration Test Cases

1. **Happy path** - Valid request returns expected status and data
2. **Not found** - Unknown ID returns 404
3. **Unauthorized** - Missing X-User-ID returns 401
4. **Forbidden** - Accessing another user's resource returns 404
5. **Validation** - Invalid payload returns 422
6. **Edge cases** - Empty lists, pagination, etc.

### CI/CD Docker Requirements

- CI runners need Docker-in-Docker (DinD) or Docker socket access
- Ensure at least 2GB RAM available for postgres container
- Add note to CI configuration about required Docker capability

## Dependencies to Add

```toml
# pyproject.toml - add to dev dependencies
testcontainers = "^4.0.0"
pytest-testcontainers = "*"  # optional, fixtures provided manually
```

## Implementation Notes

1. **Database URL**: Use `postgres_container.get_connection_url()` and modify for asyncpg format
2. **Alembic**: Run via subprocess with environment variable set
3. **Async fixtures**: Use `@pytest.fixture` with `async def` - pytest-asyncio handles automatically
4. **Connection cleanup**: Always close connections in fixture teardown
5. **Storage**: Mock or disable R2 storage for image tests (not critical for API testing)

### Truncate Tables Fixture Implementation

```python
# Table order: children first, then parents (respects FK constraints)
# CASCADE handles child table truncation automatically
TABLES_TO_TRUNCATE = [
    "generations",
    "images", 
    "projects",
    "users",
    "styles",
]

@pytest.fixture(autouse=True)
async def cleanup_tables(db_pool):
    """Truncate all tables after each test."""
    yield
    async with db_pool.acquire() as conn:
        # TRUNCATE ... CASCADE handles FK constraints automatically
        for table in TABLES_TO_TRUNCATE:
            await conn.execute(f"TRUNCATE TABLE {table} CASCADE")
```

### Test Database Setup

Since the existing `Database` class uses connection-per-operation, we need to inject the pool directly:

```python
@pytest.fixture
def db_pool(postgres_container):
    """Create connection pool for tests."""
    dsn = postgres_container.get_connection_url().replace("postgresql://", "postgresql+asyncpg://")
    return asyncpg.create_pool(dsn, min_size=1, max_size=5)

@pytest.fixture
async def test_db(db_pool, monkeypatch):
    """Monkeypatch the Database class to use test pool."""
    from foreman import db as db_module
    
    async def get_test_pool():
        return db_pool
    
    # Override the pool property on Database class
    original_pool = None
    
    yield db_pool
    
    # Cleanup happens in db_pool fixture
```

## Trade-offs

| Approach | Pros | Cons |
|----------|------|------|
| Truncate tables | Works with existing DB class architecture | Slight overhead per test |
| Transaction rollback | Fast, no truncate needed | Requires DB class refactoring (incompatible) |
| Per-test container | Complete isolation | Very slow, ~30s overhead |
| Session container | Fast startup | All tests share container lifecycle |

## Recommended Test Execution Order

1. Run unit tests first (fast, no external deps)
2. Run integration tests in CI pipeline
3. Can run in parallel: `pytest -n auto` with pytest-xdist

## Acceptance Criteria

- [ ] Integration tests can be run with `pytest tests/integration/`
- [ ] Each test is isolated - no cross-test pollution
- [ ] Tests run in < 30 seconds total (excluding container startup)
- [ ] Container starts automatically, no manual setup required
- [ ] All endpoints are covered with comprehensive test cases
- [ ] Tests work locally and in CI/CD environment
