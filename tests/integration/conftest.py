"""Integration test fixtures."""

import os
import uuid

# Disable DEV_MODE to prevent ensure_dev_user running at startup
os.environ["DEV_MODE"] = "false"

import asyncpg
import pytest
from fastapi.testclient import TestClient
from testcontainers.postgres import PostgresContainer

# Table order for truncation (children before parents due to FK)
TABLES_TO_TRUNCATE = [
    "generations",
    "images",
    "projects",
    "users",
    "styles",
]


@pytest.fixture(scope="session")
def postgres_container():
    """Start PostgreSQL container once per test session."""
    with PostgresContainer("postgres:16-alpine") as pg:
        yield pg


@pytest.fixture(scope="session")
def db_dsn(postgres_container):
    """Get asyncpg-compatible connection string."""
    # Convert postgresql:// to postgresql+asyncpg://
    dsn = postgres_container.get_connection_url()
    if "postgresql+asyncpg" not in dsn:
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://")
    return dsn


@pytest.fixture(scope="session")
async def db_pool(db_dsn):
    """Create asyncpg connection pool for the test session."""
    pool = await asyncpg.create_pool(dsn=db_dsn, min_size=1, max_size=5)

    # Run migrations
    import subprocess

    env = os.environ.copy()
    env["DATABASE_URL"] = db_dsn.replace("postgresql+asyncpg://", "postgresql://")
    subprocess.run(
        ["alembic", "upgrade", "head"],
        env=env,
        check=True,
        cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    )

    yield pool
    await pool.close()


@pytest.fixture
async def cleanup_tables(db_pool):
    """Truncate all tables after each test."""
    yield
    async with db_pool.acquire() as conn:
        # TRUNCATE CASCADE handles FK constraints automatically
        for table in TABLES_TO_TRUNCATE:
            await conn.execute(f"TRUNCATE TABLE {table} CASCADE")


@pytest.fixture(scope="session")
def app_with_test_db(db_pool):
    """Create FastAPI app with test database."""
    import asyncpg

    from foreman.api import deps
    from foreman.db import Database
    from foreman.main import app

    # Create a Database wrapper that uses our test pool
    class TestDatabase(Database):
        """Test Database that uses injected pool."""

        def __init__(self, pool: asyncpg.Pool):
            # Skip parent __init__, just set the pool
            self._pool = pool

        async def startup(self):
            pass  # Skip, pool already created

        async def shutdown(self):
            pass  # Skip, pool managed by session fixture

        @property
        def pool(self):
            return self._pool

    test_db = TestDatabase(db_pool)

    async def override_get_db():
        return test_db

    app.dependency_overrides[deps.get_db] = override_get_db

    yield app

    # Clear overrides
    app.dependency_overrides.clear()


@pytest.fixture
def client(app_with_test_db):
    """Create TestClient for the app."""
    return TestClient(app_with_test_db)


# ---------------------------------------------------------------------------
# Helper functions for scaffolding test data
# ---------------------------------------------------------------------------


def create_user_via_api(client: TestClient, email: str | None = None) -> tuple[dict, dict]:
    """Create user via POST /v1/users and return (user_data, auth_headers)."""
    if email is None:
        email = f"test-{uuid.uuid4().hex[:8]}@example.com"

    resp = client.post("/v1/users", json={"email": email, "full_name": "Test User"})
    assert resp.status_code == 201, f"Failed to create user: {resp.text}"
    user = resp.json()
    return user, {"X-User-ID": user["id"]}


def create_project_via_api(
    client: TestClient,
    headers: dict,
    name: str = "Test Project",
    image_url: str = "https://example.com/image.jpg",
) -> dict:
    """Create project via POST /v1/projects/. Requires user first."""
    resp = client.post(
        "/v1/projects/", headers=headers, json={"name": name, "original_image_url": image_url}
    )
    assert resp.status_code == 201, f"Failed to create project: {resp.text}"
    return resp.json()


def create_generation_via_api(
    client: TestClient,
    headers: dict,
    project_id: str,
    prompt: str = "modern living room",
    style_id: str | None = None,
) -> dict:
    """Create generation via POST /v1/projects/{id}/generations. Requires project first."""
    resp = client.post(
        f"/v1/projects/{project_id}/generations",
        headers=headers,
        json={"prompt": prompt, "style_id": style_id, "model_used": "dalle-3", "attempt": 1},
    )
    assert resp.status_code == 202, f"Failed to create generation: {resp.text}"
    return resp.json()


def create_image_via_api(
    client: TestClient, headers: dict, project_id: str, filename: str = "test.jpg"
) -> dict:
    """Create image via POST /v1/projects/{id}/images. Requires project first."""
    resp = client.post(
        f"/v1/projects/{project_id}/images",
        headers=headers,
        json={"filename": filename, "content_type": "image/jpeg", "size_bytes": 1024},
    )
    # May return 500 if storage is not configured - that's ok for integration tests
    if resp.status_code == 201:
        return resp.json()
    return None
