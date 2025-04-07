"""
Rate limiting middleware using token bucket algorithm with different limits
for authenticated and unauthenticated requests.
"""

import hashlib
import logging
import time
from collections.abc import Callable

from fastapi import Request, Response, status
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

logger = logging.getLogger(__name__)


class RateLimiter:
    """Token bucket rate limiter implementation."""

    def __init__(self, rate: float, capacity: int):
        """
        Initialize rate limiter with specified rate and capacity.

        Args:
            rate: Rate at which tokens are refilled (tokens per second)
            capacity: Maximum number of tokens in the bucket

        """
        self.rate = rate
        self.capacity = capacity
        self.tokens: float = float(
            capacity
        )  # Use float for token count to avoid type issues
        self.last_refill = time.time()

    def can_consume(self, tokens: int = 1) -> bool:
        """
        Check if tokens can be consumed.

        Args:
            tokens: Number of tokens to consume

        Returns:
            True if tokens can be consumed, False otherwise

        """
        self._refill()
        if self.tokens >= tokens:
            self.tokens -= tokens
            return True
        return False

    def _refill(self) -> None:
        """Refill tokens based on elapsed time."""
        now = time.time()
        elapsed = now - self.last_refill
        new_tokens = elapsed * self.rate

        if new_tokens > 0:
            self.tokens = min(self.capacity, self.tokens + float(new_tokens))
            self.last_refill = now


class RateLimiters:
    """Rate limiters for different client identifiers."""

    def __init__(
        self,
        anon_rate: float = 1.0,
        anon_capacity: int = 10,
        auth_rate: float = 5.0,
        auth_capacity: int = 50,
        cleanup_interval: int = 300,
    ):
        """
        Initialize rate limiters.

        Args:
            anon_rate: Rate for anonymous requests (per second)
            anon_capacity: Capacity for anonymous requests
            auth_rate: Rate for authenticated requests (per second)
            auth_capacity: Capacity for authenticated requests
            cleanup_interval: Interval for cleaning up stale limiters (seconds)

        """
        self.anon_rate = anon_rate
        self.anon_capacity = anon_capacity
        self.auth_rate = auth_rate
        self.auth_capacity = auth_capacity
        self.cleanup_interval = cleanup_interval

        # Store limiters by client ID
        self.limiters: dict[str, tuple[RateLimiter, float]] = {}
        self.last_cleanup = time.time()

    def get_limiter(self, client_id: str, authenticated: bool = False) -> RateLimiter:
        """
        Get or create a rate limiter for a client.

        Args:
            client_id: Client identifier (IP address or user ID)
            authenticated: Whether the client is authenticated

        Returns:
            RateLimiter for the client

        """
        # Clean up stale limiters if necessary
        now = time.time()
        if now - self.last_cleanup > self.cleanup_interval:
            self._cleanup()
            self.last_cleanup = now

        # Get or create limiter
        if client_id not in self.limiters:
            rate = self.auth_rate if authenticated else self.anon_rate
            capacity = self.auth_capacity if authenticated else self.anon_capacity
            self.limiters[client_id] = (RateLimiter(rate, capacity), now)
            return self.limiters[client_id][0]

        # Update last access time
        limiter, _ = self.limiters[client_id]
        self.limiters[client_id] = (limiter, now)
        return limiter

    def _cleanup(self) -> None:
        """Remove stale limiters that haven't been accessed recently."""
        now = time.time()
        stale_time = now - (self.cleanup_interval * 2)

        # Find keys to remove
        to_remove = []
        for client_id, (_, last_access) in self.limiters.items():
            if last_access < stale_time:
                to_remove.append(client_id)

        # Remove stale limiters
        for client_id in to_remove:
            del self.limiters[client_id]

        if to_remove:
            logger.debug(f"Cleaned up {len(to_remove)} stale rate limiters")


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Middleware for rate limiting API requests."""

    def __init__(
        self,
        app: ASGIApp,
        anon_rate: float = 30.0,
        anon_capacity: int = 50,
        auth_rate: float = 60.0,
        auth_capacity: int = 100,
        exempt_paths: list[str] | None = None,
        auth_header: str = "Authorization",
        token_cost_paths: dict[str, int] | None = None,
    ):
        """
        Initialize the middleware.

        Args:
            app: FastAPI application
            anon_rate: Rate for anonymous requests (per second)
            anon_capacity: Capacity for anonymous requests
            auth_rate: Rate for authenticated requests (per second)
            auth_capacity: Capacity for authenticated requests
            exempt_paths: Paths that are exempt from rate limiting
            auth_header: HTTP header used for authentication
            token_cost_paths: Dictionary mapping path prefixes to token costs

        """
        super().__init__(app)
        self.rate_limiters = RateLimiters(
            anon_rate=anon_rate,
            anon_capacity=anon_capacity,
            auth_rate=auth_rate,
            auth_capacity=auth_capacity,
        )
        self.exempt_paths = exempt_paths or [
            "/health",
            "/docs",
            "/redoc",
            "/openapi.json",
        ]
        self.auth_header = auth_header
        self.token_cost_paths = token_cost_paths or {
            "/files/": 2,  # Higher cost for file downloads
            "/legacy/": 5,  # Higher cost for uploads
            "/api/upload": 5,  # Higher cost for uploads
            "/": 1,  # Default cost
        }

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """
        Process the request and apply rate limiting.

        Args:
            request: FastAPI request
            call_next: Next middleware in the chain

        Returns:
            Response from the API

        """
        # Skip rate limiting for exempt paths
        path = request.url.path
        if any(path.startswith(exempt) for exempt in self.exempt_paths):
            return await call_next(request)

        # Determine if request is authenticated
        authenticated = self.auth_header in request.headers

        # Get client identifier (IP address or user ID if authenticated)
        client_id = self._get_client_id(request)

        # Get token cost for this path
        token_cost = self._get_token_cost(path)

        # Get rate limiter for this client
        limiter = self.rate_limiters.get_limiter(client_id, authenticated)

        # Check if request is allowed
        if not limiter.can_consume(token_cost):
            logger.warning(f"Rate limit exceeded for client {client_id}")
            return JSONResponse(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                content={"detail": "Too many requests. Please try again later."},
            )

        # Add rate limit headers to response
        response = await call_next(request)
        remaining = max(0, limiter.tokens)
        limit = limiter.capacity

        response.headers["X-RateLimit-Limit"] = str(limit)
        response.headers["X-RateLimit-Remaining"] = str(int(remaining))
        response.headers["X-RateLimit-Reset"] = str(
            int(
                time.time() + (limit - remaining) / limiter.rate
                if remaining < limit
                else 0
            )
        )

        return response

    def _get_client_id(self, request: Request) -> str:
        """
        Get client identifier from request.

        Uses the following in order of preference:
        1. User ID from authentication (if available)
        2. X-Forwarded-For header (if available)
        3. Client host

        Args:
            request: FastAPI request

        Returns:
            Client identifier

        """
        # Extract user ID from authentication context if available
        auth_user = None

        # Check for the user object attached to the request state
        if hasattr(request.state, "user") and request.state.user:
            auth_user = request.state.user

            # If we have a user ID, use it as the client identifier
            if "user_id" in auth_user and auth_user["user_id"] != "anonymous":
                user_id = auth_user["user_id"]
                # Use a prefix to distinguish user IDs from IP hashes
                return f"user:{user_id}"

        # Try to extract API key from headers
        api_key = request.headers.get("X-API-Key")
        if api_key:
            # Hash the API key to use as identifier
            # This works even before authentication is complete
            return f"apikey:{hashlib.sha256(api_key.encode()).hexdigest()[:16]}"

        # Try X-Forwarded-For header
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # Use the first IP in the list (client IP)
            client_ip = forwarded_for.split(",")[0].strip()
            return f"ip:{hashlib.md5(client_ip.encode(), usedforsecurity=False).hexdigest()}"

        # Use client host
        client_host = request.client.host if request.client else "unknown"
        return (
            f"ip:{hashlib.md5(client_host.encode(), usedforsecurity=False).hexdigest()}"
        )

    def _get_token_cost(self, path: str) -> int:
        """
        Get token cost for a path.

        Args:
            path: Request path

        Returns:
            Token cost for the path

        """
        for prefix, cost in self.token_cost_paths.items():
            if path.startswith(prefix):
                return cost

        # Default cost
        return 1
