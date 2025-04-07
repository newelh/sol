import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from app.api.state import AppState

logger = logging.getLogger(__name__)


router = APIRouter()


class HealthResponse(BaseModel):
    """Health check response model."""

    status: str
    postgres: bool
    s3: bool
    valkey: bool
    version: str
    environment: str  # Adds environment information to help with debugging


def get_app_state(request: Request) -> AppState:
    """Get the application state from the request."""
    return request.app.state.state


@router.get("/")
async def health_check(
    request: Request, state: Annotated[AppState, Depends(get_app_state)]
) -> HealthResponse:
    """
    Health check endpoint that verifies all services are operational.
    """
    logger.info("Running health check")

    # Get environment information with a default value in case it's not set
    try:
        env = request.app.state.settings.server.environment
    except AttributeError:
        env = "development"  # Default environment if not set
    logger.info(f"Current environment: {env}")

    # Check all service connections with detailed logging
    postgres_healthy = False
    s3_healthy = False
    valkey_healthy = False

    try:
        logger.info("Checking PostgreSQL health")
        postgres_healthy = (
            await state.postgres.health_check() if state.postgres else False
        )
        logger.info(f"PostgreSQL health check result: {postgres_healthy}")

        if not postgres_healthy:
            logger.warning("PostgreSQL health check failed")
            if state.postgres:
                pg_config = state.postgres.config
                logger.warning(
                    f"PostgreSQL config: host={pg_config.host}, port={pg_config.port}, db={pg_config.database}"
                )
            else:
                logger.warning("PostgreSQL client not initialized")
    except Exception:
        logger.exception("PostgreSQL health check error")

    try:
        logger.info("Checking S3 health")
        s3_healthy = await state.s3.health_check() if state.s3 else False
        logger.info(f"S3 health check result: {s3_healthy}")

        if not s3_healthy:
            logger.warning("S3 health check failed")
            if state.s3:
                s3_config = state.s3.config
                logger.warning(
                    f"S3 config: endpoint={s3_config.endpoint_url}, bucket={s3_config.default_bucket}"
                )
            else:
                logger.warning("S3 client not initialized")
    except Exception:
        logger.exception("S3 health check error")

    try:
        logger.info("Checking Valkey health")
        valkey_healthy = await state.valkey.health_check() if state.valkey else False
        logger.info(f"Valkey health check result: {valkey_healthy}")

        if not valkey_healthy:
            logger.warning("Valkey health check failed")
            if state.valkey:
                valkey_config = state.valkey.config
                logger.warning(
                    f"Valkey config: host={valkey_config.host}, port={valkey_config.port}"
                )
            else:
                logger.warning("Valkey client not initialized")
    except Exception:
        logger.exception("Valkey health check error")

    # Determine overall status
    status = (
        "healthy" if all([postgres_healthy, s3_healthy, valkey_healthy]) else "degraded"
    )
    logger.info(f"Overall health status: {status}")

    return HealthResponse(
        status=status,
        postgres=postgres_healthy,
        s3=s3_healthy,
        valkey=valkey_healthy,
        version=request.app.state.settings.app.version,
        environment=env,
    )
