import logging
import traceback
from typing import Any

import asyncpg

from app.core.clients.base import BaseClient
from app.core.config import PostgresSettings

logger = logging.getLogger(__name__)

# Error messages
POSTGRES_NOT_INITIALIZED = "PostgreSQL pool is not initialized"


class PostgresClient(BaseClient[PostgresSettings]):
    """Client for interacting with PostgreSQL database."""

    def __init__(self, config: PostgresSettings) -> None:
        super().__init__(config)
        self._pool: asyncpg.Pool | None = None
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize the connection pool to PostgreSQL."""
        if self._initialized:
            return

        logger.info(
            f"Initializing PostgreSQL client with connection to {self.config.host}:{self.config.port}/{self.config.database}"
        )

        try:
            # Build connection parameters
            connect_kwargs = {
                "host": self.config.host,
                "port": self.config.port,
                "user": self.config.user,
                "password": self.config.password,
                "database": self.config.database,
                "min_size": self.config.min_connections,
                "max_size": self.config.max_connections,
            }

            # Only add command_timeout if specified
            if self.config.statement_timeout is not None:
                connect_kwargs["command_timeout"] = self.config.statement_timeout

            logger.debug(f"PostgreSQL connection parameters: {connect_kwargs}")

            # Create the connection pool
            self._pool = await asyncpg.create_pool(**connect_kwargs)

            # If statement_timeout is specified, set it for all connections in the pool
            if self.config.statement_timeout is not None:
                timeout_ms = (
                    self.config.statement_timeout * 1000
                )  # Convert to milliseconds
                async with self._pool.acquire() as conn:
                    await conn.execute(f"SET statement_timeout = {timeout_ms}")

            self._initialized = True
            logger.info("PostgreSQL client initialization successful")
        except Exception:
            logger.exception(
                f"Failed to initialize PostgreSQL client with host={self.config.host}, port={self.config.port}, db={self.config.database}"
            )
            logger.debug(traceback.format_exc())
            raise

    async def cleanup(self) -> None:
        """Close all connections in the pool."""
        if self._pool is not None:
            await self._pool.close()
            self._pool = None
            self._initialized = False

    async def get_metrics(self) -> dict[str, Any]:
        """Get connection pool metrics."""
        if not self._pool:
            return {"status": "not_initialized"}

        return {
            "status": "initialized",
            "min_size": self.config.min_connections,
            "max_size": self.config.max_connections,
            "size": self._pool.get_size(),
            "free_size": self._pool.get_idle_size(),
        }

    async def health_check(self) -> bool:
        """Verify database connectivity with a simple query."""
        if not self._pool:
            logger.warning(
                "PostgreSQL health check failed: connection pool not initialized"
            )
            return False

        try:
            logger.info("Performing PostgreSQL health check")
            async with self._pool.acquire() as conn:
                result = await conn.fetchval("SELECT 1")
                logger.info(f"PostgreSQL health check result: {result}")

                # Get PostgreSQL version for diagnostics
                version = await conn.fetchval("SELECT version()")
                logger.info(f"PostgreSQL version: {version}")

                # Get connection info
                conn_info = await conn.fetchrow(
                    "SELECT current_database(), current_user"
                )
                logger.info(
                    f"Connected as: {conn_info['current_user']} to database: {conn_info['current_database']}"
                )

                return result == 1
        except Exception:
            logger.exception("PostgreSQL health check failed")
            logger.debug(traceback.format_exc())
            return False

    async def execute(self, query: str, *args: Any) -> str:
        """Execute a SQL query and return the command tag."""
        if not self._initialized:
            await self.initialize()
        if self._pool is None:
            raise ValueError(POSTGRES_NOT_INITIALIZED)
        return await self._pool.execute(query, *args)

    async def fetch(self, query: str, *args: Any) -> list[asyncpg.Record]:
        """Execute a query and return all rows."""
        if not self._initialized:
            await self.initialize()
        if self._pool is None:
            raise ValueError(POSTGRES_NOT_INITIALIZED)
        return await self._pool.fetch(query, *args)

    async def fetchval(self, query: str, *args: Any) -> Any:
        """Execute a query and return a single value."""
        if not self._initialized:
            await self.initialize()
        if self._pool is None:
            raise ValueError(POSTGRES_NOT_INITIALIZED)
        return await self._pool.fetchval(query, *args)

    async def fetchrow(self, query: str, *args: Any) -> asyncpg.Record | None:
        """Execute a query and return a single row."""
        if not self._initialized:
            await self.initialize()
        if self._pool is None:
            raise ValueError(POSTGRES_NOT_INITIALIZED)
        return await self._pool.fetchrow(query, *args)

    async def execute_many(self, query: str, args_list: list[tuple[Any, ...]]) -> None:
        """Execute a query with different sets of arguments."""
        if not self._initialized:
            await self.initialize()
        if self._pool is None:
            raise ValueError(POSTGRES_NOT_INITIALIZED)
        async with self._pool.acquire() as conn:
            await conn.executemany(query, args_list)

    async def transaction(self) -> Any:
        """Start a transaction and return a transaction context manager."""
        if not self._initialized:
            await self.initialize()
        if self._pool is None:
            raise ValueError(POSTGRES_NOT_INITIALIZED)
        return self._pool.acquire()
