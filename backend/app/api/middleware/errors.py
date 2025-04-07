"""
Error handling middleware for the API.

This module implements global error handling for all routes.
"""

import logging
import traceback

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)

# Error handling middleware for consistent API responses
# =====================================================================


def register_exception_handlers(app: FastAPI) -> None:
    """Register exception handlers with the FastAPI application."""

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Handle HTTP exceptions."""
        logger.info(
            f"HTTP exception: {exc.status_code} - {exc.detail}",
            extra={"path": request.url.path},
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={"detail": exc.detail},
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle request validation errors."""
        logger.info(
            f"Validation error: {exc}",
            extra={"path": request.url.path},
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()},
        )

    @app.exception_handler(ValidationError)
    async def pydantic_validation_exception_handler(
        request: Request, exc: ValidationError
    ) -> JSONResponse:
        """Handle Pydantic validation errors."""
        logger.info(
            f"Pydantic validation error: {exc}",
            extra={"path": request.url.path},
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()},
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle unhandled exceptions."""
        # Log the full exception with traceback for debugging
        logger.error(
            f"Unhandled exception: {exc}",
            extra={
                "path": request.url.path,
                "traceback": traceback.format_exc(),
            },
        )

        # Return a generic error message to the client
        # This prevents leaking internal implementation details
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "An unexpected error occurred. Please try again later."},
        )
