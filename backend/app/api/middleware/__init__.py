"""Middleware package for the API."""

from app.api.middleware.rate_limit import RateLimitMiddleware

__all__ = ["RateLimitMiddleware"]
