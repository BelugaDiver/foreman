"""Integration test fixtures with PostgreSQL testcontainer lifecycle management."""

import logging
import os
import uuid

# Disable DEV_MODE to prevent ensure_dev_user running at startup
os.environ["DEV_MODE"] = "false"

import asyncio

import asyncpg
import httpx
import pytest
from testcontainers.postgres import PostgresContainer

logger = logging.getLogger(__name__)

# Table order for truncation (children before parents due to FK)
TABLES_TO_TRUNCATE = [
    "generations",
    "images",
    "projects",
    "users",
    "styles",
]


def is_docker_available() -> bool:
    """Check if Docker is available and running."""
    import subprocess

    try:
        result = subprocess.run(
            ["docker", "info"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=5,
        )
        return result.returncode == 0
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False


# Global container reference
_postgres_container = None


@pytest.fixture(scope="session", autouse=True)
def setup_postgres():
    """Start PostgreSQL container once per test session."""
    global _postgres_container

    if not is_docker_available():
        logger.error("Docker is not available.")
        pytest.exit("Docker is not available. Please start Docker and try again.", returncode=1)

    logger.info("Starting PostgreSQL testcontainer...")
    try:
        _postgres_container = PostgresContainer("postgres:18-alpine")
        _postgres_container.start()
        connection_url = _postgres_container.get_connection_url()
        host = connection_url.split("@")[1] if "@" in connection_url else "local"
        logger.info(f"PostgreSQL container started at: {host}")

        # Run migrations
        dsn = connection_url
        if "+" in dsn.split("://")[0]:
            scheme = dsn.split("://")[0].split("+")[0]
            dsn = dsn.replace(dsn.split("://")[0], scheme)

        import subprocess

        env = os.environ.copy()
        env["DATABASE_URL"] = dsn.replace("postgresql+asyncpg://", "postgresql://")

        subprocess.run(
            ["alembic", "upgrade", "heads"],
            env=env,
            check=True,
            capture_output=True,
            text=True,
        )
        logger.info("Alembic migrations completed")
    except Exception as e:
        logger.error(f"Setup failed: {e}")
        pytest.exit(f"Setup failed: {e}", returncode=1)

    yield

    if _postgres_container:
        try:
            logger.info("Stopping PostgreSQL testcontainer...")
            _postgres_container.stop()
        except Exception as e:
            logger.warning(f"Error stopping container: {e}")


def get_db_dsn():
    """Get asyncpg-compatible connection string."""
    dsn = _postgres_container.get_connection_url()
    if "+" in dsn.split("://")[0]:
        scheme = dsn.split("://")[0].split("+")[0]
        dsn = dsn.replace(dsn.split("://")[0], scheme)
    return dsn


@pytest.fixture(autouse=True)
async def cleanup_tables():
    """Truncate all tables before AND after each test for maximum isolation."""

    async def do_cleanup():
        for attempt in range(3):
            try:
                conn = await asyncpg.connect(get_db_dsn())
                try:
                    await conn.execute(
                        "TRUNCATE TABLE generations, images, projects, users, styles CASCADE"
                    )
                    break
                finally:
                    await conn.close()
            except Exception as e:
                if attempt == 2:
                    logger.warning(f"Error in cleanup: {e}")
                else:
                    await asyncio.sleep(0.1)

    # Clean before test
    await do_cleanup()

    yield

    # Clean after test
    await do_cleanup()


@pytest.fixture
async def app_with_test_db():
    """Create FastAPI app with test database using direct connections."""
    from foreman.api import deps
    from foreman.db import Database
    from foreman.main import app

    # Create connections on-demand instead of using a pool
    class TestDatabase(Database):
        def __init__(self):
            self._pool = None

        async def startup(self):
            pass

        async def shutdown(self):
            pass

        @property
        def pool(self):
            return None

        async def fetchrow(self, statement):
            conn = await asyncpg.connect(get_db_dsn())
            try:
                return await conn.fetchrow(statement.text, *statement.params)
            finally:
                await conn.close()

        async def fetch(self, statement):
            conn = await asyncpg.connect(get_db_dsn())
            try:
                return await conn.fetch(statement.text, *statement.params)
            finally:
                await conn.close()

        async def execute(self, statement):
            conn = await asyncpg.connect(get_db_dsn())
            try:
                return await conn.execute(statement.text, *statement.params)
            finally:
                await conn.close()

    test_db = TestDatabase()

    async def override_get_db():
        return test_db

    app.dependency_overrides[deps.get_db] = override_get_db

    yield app

    app.dependency_overrides.clear()


@pytest.fixture
async def client(app_with_test_db):
    """Create async HTTP client for the app."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app_with_test_db),
        base_url="http://testserver",
        follow_redirects=True,
    ) as client:
        yield client


# ---------------------------------------------------------------------------
# Helper functions for scaffolding test data
# ---------------------------------------------------------------------------


async def create_user_via_api(
    client: httpx.AsyncClient, email: str | None = None
) -> tuple[dict, dict]:
    """Create user via POST /v1/users and return (user_data, auth_headers)."""
    if email is None:
        email = f"test-{uuid.uuid4().hex[:8]}@example.com"

    resp = await client.post("/v1/users", json={"email": email, "full_name": "Test User"})
    assert resp.status_code == 201, f"Failed to create user: {resp.text}"
    user = resp.json()
    return user, {"X-User-ID": user["id"]}


async def create_project_via_api(
    client: httpx.AsyncClient,
    headers: dict,
    name: str = "Test Project",
    image_url: str | None = "https://example.com/image.jpg",
) -> dict:
    """Create project via POST /v1/projects/. Requires user first."""
    resp = await client.post(
        "/v1/projects/", headers=headers, json={"name": name, "original_image_url": image_url}
    )
    assert resp.status_code == 201, f"Failed to create project: {resp.text}"
    return resp.json()


async def create_generation_via_api(
    client: httpx.AsyncClient,
    headers: dict,
    project_id: str,
    prompt: str = "modern living room",
    style_id: str | None = None,
) -> dict:
    """Create generation via POST /v1/projects/{id}/generations. Requires project first."""
    resp = await client.post(
        f"/v1/projects/{project_id}/generations",
        headers=headers,
        json={"prompt": prompt, "style_id": style_id, "model_used": "dalle-3", "attempt": 1},
    )
    assert resp.status_code == 202, f"Failed to create generation: {resp.text}"
    return resp.json()


async def create_image_via_api(
    client: httpx.AsyncClient, headers: dict, project_id: str, filename: str = "test.jpg"
) -> dict | None:
    """Create image via POST /v1/projects/{id}/images. Requires project first."""
    resp = await client.post(
        f"/v1/projects/{project_id}/images",
        headers=headers,
        json={"filename": filename, "content_type": "image/jpeg", "size_bytes": 1024},
    )
    if resp.status_code == 201:
        return resp.json()
    return None


async def create_image_direct(
    dsn: str, project_id: uuid.UUID, user_id: uuid.UUID, filename: str = "test.jpg"
) -> dict:
    """Create an image directly in the database. Returns the image dict."""
    import asyncpg

    conn = await asyncpg.connect(dsn)
    try:
        row = await conn.fetchrow(
            """
            INSERT INTO images
                (project_id, user_id, filename, content_type, size_bytes, storage_key, url)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            RETURNING *
            """,
            project_id,
            user_id,
            filename,
            "image/jpeg",
            1024,
            f"projects/{project_id}/test/{filename}",
            f"https://example.com/{filename}",
        )
        return dict(row)
    finally:
        await conn.close()
