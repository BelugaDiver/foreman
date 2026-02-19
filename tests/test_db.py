"""Tests for the database helpers."""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock

import pytest

from foreman.db import Database, DatabaseSettings, sql


class _DummyAcquire:
    def __init__(self, connection):
        self._connection = connection

    async def __aenter__(self):
        return self._connection

    async def __aexit__(self, exc_type, exc, tb):
        return False


class _DummyPool:
    def __init__(self, connection):
        self.connection = connection

    def acquire(self):
        return _DummyAcquire(self.connection)

    async def close(self):
        return None


class _DummyConnection:
    def __init__(self) -> None:
        self.execute = AsyncMock(return_value="OK")
        self.fetch = AsyncMock(return_value=[{"id": 1}])
        self.fetchrow = AsyncMock(return_value={"id": 1})


@pytest.fixture
def database_with_dummy_pool():
    database = Database(DatabaseSettings(url="postgresql://user:pass@db/service"))
    connection = _DummyConnection()
    database._pool = _DummyPool(connection)
    return database, connection


def test_settings_from_env(monkeypatch):
    """Environment variables should populate database settings."""
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db/service")
    monkeypatch.setenv("DB_POOL_MIN_SIZE", "5")
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "15")
    monkeypatch.setenv("DB_COMMAND_TIMEOUT_SECONDS", "45")

    settings = DatabaseSettings.from_env()

    assert settings.url == "postgresql://user:pass@db/service"
    assert settings.min_size == 5
    assert settings.max_size == 15
    assert settings.command_timeout == 45


def test_settings_invalid_numbers(monkeypatch, caplog):
    """Invalid integer settings should fall back to sensible defaults."""
    caplog.set_level(logging.WARNING)
    monkeypatch.setenv("DB_POOL_MIN_SIZE", "not-a-number")
    monkeypatch.setenv("DB_POOL_MAX_SIZE", "0")

    settings = DatabaseSettings.from_env()

    assert settings.min_size == 1  # default fallback
    assert settings.max_size == 1  # coerced to min_size when smaller
    assert "Invalid value" in caplog.text


@pytest.mark.asyncio
async def test_database_startup_without_url(caplog):
    """Startup is a no-op when the database URL is absent."""
    caplog.set_level(logging.WARNING)
    database = Database(DatabaseSettings(url=None))

    await database.startup()

    assert database.pool is None
    assert "DATABASE_URL is not configured" in caplog.text


@pytest.mark.asyncio
async def test_database_startup_with_url(monkeypatch):
    """Pool creation uses asyncpg.create_pool with the expected parameters."""
    fake_pool = AsyncMock()

    async def fake_create_pool(**kwargs):
        fake_pool.kwargs = kwargs
        return fake_pool

    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@db/service")
    monkeypatch.setattr("foreman.db.asyncpg.create_pool", fake_create_pool)

    settings = DatabaseSettings.from_env()
    database = Database(settings)

    await database.startup()
    assert database.pool is fake_pool
    assert fake_pool.kwargs["dsn"].endswith("/service")

    await database.shutdown()
    fake_pool.close.assert_awaited()


@pytest.mark.asyncio
async def test_connection_context_manager(database_with_dummy_pool):
    """The connection context manager should yield a connection from the pool."""

    database, connection = database_with_dummy_pool

    async with database.connection() as acquired:
        await acquired.execute("SELECT 1")

    connection.execute.assert_awaited_with("SELECT 1")


@pytest.mark.asyncio
async def test_connection_context_manager_without_pool():
    """Requesting a connection before startup should raise an error."""
    database = Database(DatabaseSettings(url="postgresql://user:pass@db/service"))

    with pytest.raises(RuntimeError):
        async with database.connection():
            pass


def test_sql_helper_builds_statements():
    """`sql` should capture the text and params separately."""
    statement = sql("SELECT * FROM users WHERE id = $1", 42)

    assert statement.text == "SELECT * FROM users WHERE id = $1"
    assert statement.params == (42,)


@pytest.mark.asyncio
async def test_execute_requires_sql_statement(database_with_dummy_pool):
    """Database.execute should forward structured statements."""
    database, connection = database_with_dummy_pool
    connection.execute.return_value = "UPDATE 1"
    statement = sql("UPDATE users SET email = $1 WHERE id = $2", "a@example.com", 7)

    result = await database.execute(statement)

    assert result == "UPDATE 1"
    connection.execute.assert_awaited_with(statement.text, *statement.params)


@pytest.mark.asyncio
async def test_fetch_uses_sql_statement(database_with_dummy_pool):
    database, connection = database_with_dummy_pool
    connection.fetch.return_value = [{"id": 1, "name": "Ada"}]
    statement = sql("SELECT * FROM users WHERE id = $1", 1)

    rows = await database.fetch(statement)

    assert rows == [{"id": 1, "name": "Ada"}]
    connection.fetch.assert_awaited_with(statement.text, *statement.params)


@pytest.mark.asyncio
async def test_fetchrow_uses_sql_statement(database_with_dummy_pool):
    database, connection = database_with_dummy_pool
    connection.fetchrow.return_value = {"id": 2, "name": "Grace"}
    statement = sql("SELECT * FROM users WHERE id = $1", 2)

    row = await database.fetchrow(statement)

    assert row == {"id": 2, "name": "Grace"}
    connection.fetchrow.assert_awaited_with(statement.text, *statement.params)