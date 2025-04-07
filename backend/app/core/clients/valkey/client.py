import logging
import traceback
from typing import Any, TypeVar, cast

import valkey.asyncio as valkey

from app.core.clients.base import BaseClient
from app.core.config import ValkeySettings

# Define a generic type for valkey results
T = TypeVar("T")

logger = logging.getLogger(__name__)

# Error messages
VALKEY_NOT_INITIALIZED = "Valkey client is not initialized"


class ValkeyClient(BaseClient[ValkeySettings]):
    """Client for interacting with Valkey/Redis."""

    def __init__(self, config: ValkeySettings) -> None:
        super().__init__(config)
        self._client: valkey.Redis | None = None
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize the Valkey client."""
        if self._initialized:
            return

        logger.info(
            f"Initializing Valkey client with connection {self.config.host}:{self.config.port}"
        )
        try:
            self._client = valkey.Redis(
                host=self.config.host,
                port=self.config.port,
                password=self.config.password,
                db=self.config.db,
                ssl=self.config.ssl,
                socket_timeout=self.config.socket_timeout,
                socket_connect_timeout=self.config.socket_connect_timeout,
                health_check_interval=self.config.health_check_interval,
                max_connections=self.config.max_connections,
            )
            self._initialized = True
            logger.info("Valkey client initialization successful")
        except Exception:
            logger.exception(
                f"Failed to initialize Valkey client with host={self.config.host}, port={self.config.port}, db={self.config.db}"
            )
            logger.debug(traceback.format_exc())
            raise

    async def cleanup(self) -> None:
        """Close the Valkey client."""
        if self._client:
            await self._client.close()
            self._client = None
            self._initialized = False

    async def get_metrics(self) -> dict[str, Any]:
        """Get client metrics."""
        if not self._client:
            return {"status": "not_initialized"}

        try:
            info = await self._client.info()
            return {
                "status": "initialized",
                "used_memory": info.get("used_memory", 0),
                "connected_clients": info.get("connected_clients", 0),
                "uptime_in_seconds": info.get("uptime_in_seconds", 0),
            }
        except Exception:
            return {
                "status": "error",
                "connection": f"{self.config.host}:{self.config.port}",
            }

    async def health_check(self) -> bool:
        """Check connectivity with a ping."""
        if not self._client:
            logger.warning("Valkey health check failed: client not initialized")
            return False

        try:
            logger.info("Performing Valkey health check")
            result = await self._client.ping()
            logger.info(f"Valkey health check result: {result}")

            # Also try to get some server info for diagnostics
            info = await self._client.info()
            logger.info(f"Valkey version: {info.get('redis_version', 'unknown')}")
            logger.info(
                f"Valkey memory usage: {info.get('used_memory_human', 'unknown')}"
            )
        except Exception:
            logger.exception("Valkey health check failed")
            logger.debug(traceback.format_exc())
            return False
        else:
            return result

    # Basic operations

    async def get(self, key: str) -> str | None:
        """Get the value of a key."""
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        # Explicitly calling and handling the result
        result: Any = self._client.get(key)
        if hasattr(result, "__await__"):
            return await result
        return result  # Fallback case, although this shouldn't happen

    async def set(
        self,
        key: str,
        value: str | bytes,
        ex: int | None = None,
        px: int | None = None,
        nx: bool = False,
        xx: bool = False,
    ) -> bool:
        """
        Set the value of a key.

        Args:
            key: Key to set
            value: Value to set
            ex: Expire time in seconds
            px: Expire time in milliseconds
            nx: Only set if key does not exist
            xx: Only set if key exists

        Returns:
            True if successful, False otherwise

        """
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        result: Any = self._client.set(key, value, ex=ex, px=px, nx=nx, xx=xx)
        if hasattr(result, "__await__"):
            result = await result
        return result == "OK"

    async def delete(self, *keys: str) -> int:
        """
        Delete one or more keys.

        Returns:
            Number of keys deleted
        """
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        result: Any = self._client.delete(*keys)
        if hasattr(result, "__await__"):
            return await result
        return result

    async def exists(self, *keys: str) -> int:
        """
        Check if key(s) exist.

        Returns:
            Number of keys that exist
        """
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        result: Any = self._client.exists(*keys)
        if hasattr(result, "__await__"):
            return await result
        return result

    async def expire(self, key: str, seconds: int) -> bool:
        """
        Set a key's time to live in seconds.

        Returns:
            True if successful, False otherwise
        """
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        result: Any = self._client.expire(key, seconds)
        if hasattr(result, "__await__"):
            return await result
        return result

    # Hash operations

    async def hget(self, name: str, key: str) -> str | None:
        """Get the value of a hash field."""
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        result: Any = self._client.hget(name, key)
        if hasattr(result, "__await__"):
            result = await result
        return cast(str | None, result)

    async def hset(self, name: str, key: str, value: str | bytes) -> int:
        """Set the value of a hash field."""
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        # Convert bytes to str if necessary for valkey - Redis/valkey
        # expects string values, not bytes
        value_str: str = value.decode("utf-8") if isinstance(value, bytes) else value

        result: Any = self._client.hset(name, key, value_str)
        if hasattr(result, "__await__"):
            result = await result
        return cast(int, result)

    async def hmget(self, name: str, keys: list[str]) -> list[str | None]:
        """Get the values of multiple hash fields."""
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        result: Any = self._client.hmget(name, keys)
        if hasattr(result, "__await__"):
            result = await result
        return cast(list[str | None], result)

    async def hmset(self, name: str, mapping: dict[str, str | bytes]) -> bool:
        """Set multiple hash fields."""
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        # Convert any bytes values to strings
        str_mapping: dict[str, str] = {}
        for k, v in mapping.items():
            if isinstance(v, bytes):
                str_mapping[k] = v.decode("utf-8")
            else:
                str_mapping[k] = v

        result: Any = self._client.hmset(name, str_mapping)
        if hasattr(result, "__await__"):
            result = await result
        return result == "OK"

    async def hgetall(self, name: str) -> dict[str, str]:
        """Get all fields and values in a hash."""
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        result: Any = self._client.hgetall(name)
        if hasattr(result, "__await__"):
            result = await result
        return cast(dict[str, str], result)

    # List operations

    async def lpush(self, name: str, *values: str | bytes) -> int:
        """Prepend values to a list."""
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        # Convert bytes to strings if needed
        str_values = [v.decode("utf-8") if isinstance(v, bytes) else v for v in values]

        result: Any = self._client.lpush(name, *str_values)
        if hasattr(result, "__await__"):
            result = await result
        return cast(int, result)

    async def rpush(self, name: str, *values: str | bytes) -> int:
        """Append values to a list."""
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        # Convert bytes to strings if needed
        str_values = [v.decode("utf-8") if isinstance(v, bytes) else v for v in values]

        result: Any = self._client.rpush(name, *str_values)
        if hasattr(result, "__await__"):
            result = await result
        return cast(int, result)

    async def lpop(self, name: str) -> str | None:
        """Remove and get the first element in a list."""
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        result: Any = self._client.lpop(name)
        if hasattr(result, "__await__"):
            result = await result
        return cast(str | None, result)

    async def rpop(self, name: str) -> str | None:
        """Remove and get the last element in a list."""
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        result: Any = self._client.rpop(name)
        if hasattr(result, "__await__"):
            result = await result
        return cast(str | None, result)

    async def lrange(self, name: str, start: int, end: int) -> list[str]:
        """Get a range of elements from a list."""
        if not self._initialized:
            await self.initialize()
        if self._client is None:
            raise ValueError(VALKEY_NOT_INITIALIZED)

        result: Any = self._client.lrange(name, start, end)
        if hasattr(result, "__await__"):
            result = await result
        return cast(list[str], result)
