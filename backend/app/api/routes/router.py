from fastapi import Depends, FastAPI, Header, Request

from app.api.routes.health import router as health_router
from app.api.routes.metrics import router as metrics_router
from app.api.routes.v1.files import router as files_v1_router
from app.api.routes.v1.legacy import router as legacy_v1_router
from app.api.routes.v1.pypi import router as pypi_v1_router
from app.api.routes.v1.search import router as search_v1_router
from app.api.routes.v1.simple import router as simple_v1_router


def get_api_version(
    sol_version: str | None = Header(None, alias="sol-version"),
) -> str:
    """Get the API version from request header or default to v1."""
    if sol_version is None:
        return "v1"

    # Normalize version format (e.g., "1.0" -> "v1")
    if sol_version.startswith("v"):
        major_version = sol_version.split(".")[0]
        return major_version
    else:
        try:
            major_version = sol_version.split(".")[0]
        except (ValueError, IndexError):
            return "v1"
        else:
            return f"v{major_version}"


def version_router(
    request: Request, api_version: str = Depends(get_api_version)
) -> str:
    """Route requests based on API version."""
    # Store the API version in request state for middleware/dependencies
    request.state.api_version = api_version
    return api_version


def setup_routes(app: FastAPI) -> None:
    """Configure all API routes."""
    # Health and metrics endpoints (no versioning)
    app.include_router(health_router, prefix="/health", tags=["health"])
    app.include_router(metrics_router, prefix="/metrics", tags=["metrics"])

    # Versioned API routes
    app.include_router(
        simple_v1_router,
        prefix="/simple",
        tags=["simple", "v1"],
        dependencies=[Depends(version_router)],
    )
    app.include_router(
        pypi_v1_router,
        prefix="/pypi",
        tags=["pypi", "v1"],
        dependencies=[Depends(version_router)],
    )
    app.include_router(
        files_v1_router,
        prefix="/files",
        tags=["files", "v1"],
        dependencies=[Depends(version_router)],
    )
    app.include_router(
        search_v1_router,
        prefix="/search",
        tags=["search", "v1"],
        dependencies=[Depends(version_router)],
    )
    app.include_router(
        legacy_v1_router,
        prefix="/legacy",
        tags=["legacy", "v1"],
        dependencies=[Depends(version_router)],
    )
