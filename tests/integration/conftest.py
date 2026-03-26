"""Integration test fixtures with PostgreSQL testcontainer lifecycle management."""

import logging
import os
import uuid

# Disable DEV_MODE to prevent ensure_dev_user running at startup
os.environ["DEV_MODE"] = "false"

import asyncpg
import pytest
from fastapi.testclient import TestClient
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


@pytest.fixture(scope="session", autouse=True)
def check_docker():
    """Ensure Docker is available before running any integration tests."""
    if not is_docker_available():
        logger.error("Docker is not available. Integration tests require Docker to be running.")
        pytest.exit("Docker is not available. Please start Docker and try again.", returncode=1)
    logger.info("Docker is available. Proceeding with integration tests.")
    yield


@pytest.fixture(scope="session")
def postgres_container() -> PostgresContainer:
    """Start PostgreSQL container once per test session.

    Lifecycle:
    - Starts the container when the fixture is first accessed
    - Keeps the container running for the entire test session
    - Stops and removes the container after all tests complete
    """
    logger.info("Starting PostgreSQL testcontainer...")

    container: PostgresContainer | None = None

    try:
        container = PostgresContainer("postgres:16-alpine")
        container.start()

        # Log the connection details
        connection_url: str = container.get_connection_url()  # type: ignore[assignment]
        host = connection_url.split("@")[1] if "@" in connection_url else "local"
        logger.info(f"PostgreSQL container started at: {host}")

        yield container  # type: ignore[return-value]

    except Exception as e:
        logger.error(f"Failed to start PostgreSQL container: {e}")
        pytest.exit(f"Failed to start PostgreSQL container: {e}", returncode=1)

    finally:
        # Cleanup: stop and remove the container
        if container is not None:
            try:
                logger.info("Stopping PostgreSQL testcontainer...")
                container.stop()  # type: ignore[union-attr]
                logger.info("PostgreSQL testcontainer stopped and removed.")
            except Exception as e:
                logger.warning(f"Error stopping PostgreSQL container: {e}")


@pytest.fixture(scope="session")
def db_dsn(postgres_container):
    """Get asyncpg-compatible connection string."""
    dsn = postgres_container.get_connection_url()
    if "postgresql+asyncpg" not in dsn:
        dsn = dsn.replace("postgresql://", "postgresql+asyncpg://")
    logger.debug(f"Database DSN configured: {dsn.split('@')[1] if '@' in dsn else 'local'}")
    return dsn


@pytest.fixture(scope="session")
async def db_pool(db_dsn):
    """Create asyncpg connection pool for the test session.

    Lifecycle:
    - Creates connection pool when session starts
    - Runs Alembic migrations to set up schema
    - Closes all connections when session ends
    """
    logger.info("Creating database connection pool...")

    pool = await asyncpg.create_pool(dsn=db_dsn, min_size=1, max_size=5)
    logger.info("Database pool created (min=1, max=5)")

    # Run migrations
    logger.info("Running Alembic migrations...")
    import subprocess

    env = os.environ.copy()
    env["DATABASE_URL"] = db_dsn.replace("postgresql+asyncpg://", "postgresql://")

    try:
        subprocess.run(
            ["alembic", "upgrade", "head"],
            env=env,
            check=True,
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        )
        logger.info("Alembic migrations completed successfully")
    except subprocess.CalledProcessError as e:
        logger.error(f"Migration failed: {e.stderr}")
        raise

    yield pool

    # Cleanup: close pool
    logger.info("Closing database connection pool...")
    await pool.close()
    logger.info("Database connection pool closed.")


@pytest.fixture
async def cleanup_tables(db_pool):
    """Truncate all tables after each test.

    This ensures test isolation by cleaning up all data created during each test.
    Uses TRUNCATE ... CASCADE to handle FK constraints automatically.
    """
    yield

    try:
        async with db_pool.acquire() as conn:
            for table in TABLES_TO_TRUNCATE:
                await conn.execute(f"TRUNCATE TABLE {table} CASCADE")
            logger.debug("Tables truncated for test isolation")
    except Exception as e:
        logger.warning(f"Error truncating tables: {e}")


@pytest.fixture(scope="session")
def app_with_test_db(db_pool):
    """Create FastAPI app with test database.

    Injects the test database pool into the application by overriding
    the get_db dependency.
    """
    import asyncpg

    from foreman.api import deps
    from foreman.db import Database
    from foreman.main import app

    class TestDatabase(Database):
        """Test Database that uses injected pool."""

        def __init__(self, pool: asyncpg.Pool):
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
    logger.debug("Application dependency overrides configured")

    yield app

    # Cleanup: remove overrides
    app.dependency_overrides.clear()
    logger.debug("Application dependency overrides cleared")


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
) -> dict | None:
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
