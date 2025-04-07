import json
import logging
from typing import Any

from app.core.clients.valkey import ValkeyClient
from app.repos.interfaces import CacheRepository

logger = logging.getLogger(__name__)

# Error messages
VALKEY_CLIENT_NOT_INITIALIZED = "ValKey client is not initialized"


class ValkeyCacheRepository(CacheRepository):
    """Valkey implementation of the cache repository."""

    def __init__(self, valkey: ValkeyClient, prefix: str = "sol:"):
        self.valkey = valkey
        self.prefix = prefix

    async def get(self, key: str) -> Any | None:
        """Get a value from cache."""
        full_key = f"{self.prefix}{key}"
        data = await self.valkey.get(full_key)
        if data is None:
            return None
        try:
            # Convert to string if bytes
            string_data = data.decode("utf-8") if isinstance(data, bytes) else data

            # First try to deserialize as JSON (for simple types)
            return json.loads(string_data)
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            # Log and return None for invalid JSON
            logger.warning(f"Failed to deserialize data as JSON: {e}")
            return None
        except TypeError as e:
            # Log any type errors that might occur
            logger.warning(f"Type error during deserialization: {e}")
            return None

    async def set(self, key: str, value: Any, expire: int | None = None) -> bool:
        """Set a value in cache."""
        full_key = f"{self.prefix}{key}"

        # Try to serialize as JSON (more efficient, portable, and secure)
        try:
            data = json.dumps(value)
        except (TypeError, json.JSONDecodeError):
            # For non-JSON serializable objects, convert to string
            # This is safer than using pickle which can execute arbitrary code
            logger.warning("Object is not JSON serializable, storing as string")
            data = str(value)

        # Set in cache with optional expiration
        return await self.valkey.set(full_key, data, ex=expire)

    async def delete(self, key: str) -> bool:
        """Delete a value from cache."""
        full_key = f"{self.prefix}{key}"
        result = await self.valkey.delete(full_key)
        return result > 0

    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        full_key = f"{self.prefix}{key}"
        result = await self.valkey.exists(full_key)
        return result > 0

    async def clear(self) -> bool:
        """Clear all values with our prefix from cache."""
        # This is a potentially expensive operation - use with caution
        keys = await self._scan_keys(f"{self.prefix}*")
        if not keys:
            return True

        result = await self.valkey.delete(*keys)
        return result > 0

    async def _scan_keys(self, pattern: str) -> list[str]:
        """Scan for keys matching a pattern."""
        cursor = 0
        keys = []

        while True:
            if self.valkey._client is None:
                raise ValueError(VALKEY_CLIENT_NOT_INITIALIZED)

            cursor, matched_keys = await self.valkey._client.scan(
                cursor=cursor, match=pattern, count=100
            )
            keys.extend(matched_keys)

            if cursor == 0:  # No more keys
                break

        return keys
