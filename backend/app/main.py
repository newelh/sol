import logging
import sys

import uvicorn

# Remove the incorrect import
from app.core.config import get_settings


def main() -> None:
    """Run the application."""
    settings = get_settings()

    # Configure logging
    log_level = logging.DEBUG if settings.server.debug else logging.INFO

    # More verbose logging format with line numbers
    log_format = "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s"

    # Configure root logger
    logging.basicConfig(level=log_level, format=log_format, stream=sys.stdout)

    # Set specific logger levels for client modules for better diagnostics
    client_loggers = [
        "app.core.clients.postgres",
        "app.core.clients.s3",
        "app.core.clients.valkey",
        "app.api.routes.health",
        "app.api.state",
    ]

    for logger_name in client_loggers:
        module_logger = logging.getLogger(logger_name)
        module_logger.setLevel(logging.DEBUG)  # Always use DEBUG for these modules

    # Log startup information
    logger = logging.getLogger(__name__)
    logger.info(f"Starting Sol PyPI Index Server v{settings.app.version}")
    logger.info(f"Environment: {settings.server.environment}")
    logger.info(f"Debug mode: {settings.server.debug}")
    logger.info(f"Host: {settings.server.host}:{settings.server.port}")

    # Log service configuration
    logger.info(
        f"PostgreSQL: {settings.postgres.host}:{settings.postgres.port}/{settings.postgres.database}"
    )
    logger.info(f"S3: {settings.s3.endpoint_url}/{settings.s3.default_bucket}")
    logger.info(
        f"Valkey: {settings.valkey.host}:{settings.valkey.port}/{settings.valkey.db}"
    )

    # Run the application
    uvicorn.run(
        "app.api.app:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=settings.server.debug,
        workers=settings.server.workers,
        log_level="debug" if settings.server.debug else "info",
    )


if __name__ == "__main__":
    main()
