"""Database utilities for Foreman."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import AsyncIterator, Optional

import asyncpg

logger = logging.getLogger(__name__)


@dataclass
class DatabaseSettings:
    """Runtime configuration for the PostgreSQL connection pool."""

    url: Optional[str]
    min_size: int = 1
    max_size: int = 10
    command_timeout: float = 30.0

    @classmethod
    def from_env(cls) -> "DatabaseSettings":
        """Load database settings from environment variables."""
        url = os.getenv("DATABASE_URL")
        min_size = _int_from_env("DB_POOL_MIN_SIZE", default=1)
        max_size = _int_from_env("DB_POOL_MAX_SIZE", default=10)
        if max_size < min_size:
            logger.warning(
                "DB_POOL_MAX_SIZE (%s) is smaller than DB_POOL_MIN_SIZE (%s); using min value",
                max_size,
                min_size,
            )
            max_size = min_size

        command_timeout = float(_int_from_env("DB_COMMAND_TIMEOUT_SECONDS", default=30))
        return cls(
            url=url,
            min_size=min_size,
            max_size=max_size,
            command_timeout=command_timeout,
        )

    @property
    def is_configured(self) -> bool:
        """Return True when a usable PostgreSQL URL is available."""
        return bool(self.url)


class Database:
    """Thin wrapper around an asyncpg connection pool."""

    def __init__(self, settings: DatabaseSettings) -> None:
        self._settings = settings
        self._pool: Optional[asyncpg.Pool] = None

    @property
    def pool(self) -> Optional[asyncpg.Pool]:
        return self._pool

    async def startup(self) -> None:
        """Create an asyncpg connection pool if configuration is present."""
        if not self._settings.is_configured:
            logger.warning("DATABASE_URL is not configured; skipping PostgreSQL initialization")
            return

        if self._pool:
            logger.debug("Database pool already initialized")
            return

        logger.info(
            "Connecting to PostgreSQL (min_size=%s, max_size=%s)",
            self._settings.min_size,
            self._settings.max_size,
        )
        self._pool = await asyncpg.create_pool(
            dsn=self._settings.url,
            min_size=self._settings.min_size,
            max_size=self._settings.max_size,
            command_timeout=self._settings.command_timeout,
        )
        logger.info("PostgreSQL connection pool ready")

    async def shutdown(self) -> None:
        """Close the asyncpg pool when the application stops."""
        if not self._pool:
            return

        await self._pool.close()
        self._pool = None
        logger.info("PostgreSQL connection pool closed")

    @asynccontextmanager
    async def connection(self) -> AsyncIterator[asyncpg.Connection]:
        """Yield a single connection from the pool."""
        if not self._pool:
            raise RuntimeError("Database pool is not initialized")

        async with self._pool.acquire() as connection:
            yield connection

    async def execute(self, query: str, *args) -> str:
        """Execute a mutation query and return the status string."""
        if not self._pool:
            raise RuntimeError("Database pool is not initialized")

        async with self._pool.acquire() as connection:
            return await connection.execute(query, *args)

    async def fetch(self, query: str, *args) -> list[asyncpg.Record]:
        """Fetch multiple rows for SELECT-style statements."""
        if not self._pool:
            raise RuntimeError("Database pool is not initialized")

        async with self._pool.acquire() as connection:
            return await connection.fetch(query, *args)

    async def fetchrow(self, query: str, *args) -> Optional[asyncpg.Record]:
        """Fetch a single row or None."""
        if not self._pool:
            raise RuntimeError("Database pool is not initialized")

        async with self._pool.acquire() as connection:
            return await connection.fetchrow(query, *args)


def _int_from_env(name: str, default: int) -> int:
    """Parse integer environment variables with graceful fallback."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default

    try:
        return int(raw_value)
    except ValueError:
        logger.warning("Invalid value '%s' for %s. Falling back to %s.", raw_value, name, default)
        return default


__all__ = ["Database", "DatabaseSettings"]
