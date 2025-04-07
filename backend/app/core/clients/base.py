from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

ConfigT = TypeVar("ConfigT")


class BaseClient(ABC, Generic[ConfigT]):
    """
    Base client interface for all backend service clients.

    This abstract class provides a common interface for clients that interact with
    external services such as databases, object storage, caches, etc.
    """

    def __init__(self, config: ConfigT):
        self.config = config
        self._initialized = False

    @abstractmethod
    async def initialize(self) -> None:
        """
        Initialize the client with necessary setup.
        This may include creating connections, initializing pools, etc.
        """
        pass

    @abstractmethod
    async def cleanup(self) -> None:
        """
        Clean up resources used by the client.
        This may include closing connections, releasing resources, etc.
        """
        pass

    @property
    def is_initialized(self) -> bool:
        """Check if the client has been initialized."""
        return self._initialized

    @abstractmethod
    async def get_metrics(self) -> dict[str, Any]:
        """
        Get metrics about the client's operation.
        This may include connection pool stats, request counts, etc.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Perform a health check on the underlying service.
        Returns True if the service is healthy, False otherwise.
        """
        pass
