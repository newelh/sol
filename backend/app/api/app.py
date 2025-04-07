import logging
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

from app.api.middleware.rate_limit import RateLimitMiddleware
from app.api.routes.router import setup_routes
from app.api.state import setup_app_state
from app.core.config import get_settings

# Get application settings
settings = get_settings()

# Configure logging
logging.basicConfig(
    level=logging.DEBUG if settings.server.debug else logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Create FastAPI app with metadata
app = FastAPI(
    title=settings.app.name,
    description=settings.app.description,
    version=settings.app.version,
    docs_url="/docs" if settings.server.debug else None,
    redoc_url="/redoc" if settings.server.debug else None,
)


@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Global exception handler."""
    # Log the exception
    logging.exception(f"Unhandled exception: {exc!s}")

    # Return a JSON response
    return JSONResponse(
        status_code=500, content={"detail": f"Internal server error: {exc!s}"}
    )


# Add middleware
# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting middleware
app.add_middleware(
    RateLimitMiddleware,
    anon_rate=settings.server.rate_limit_anon,
    anon_capacity=settings.server.rate_limit_anon_capacity,
    auth_rate=settings.server.rate_limit_auth,
    auth_capacity=settings.server.rate_limit_auth_capacity,
    exempt_paths=["/health", "/docs", "/redoc", "/openapi.json"],
    token_cost_paths={
        "/files/": 2,  # Higher cost for file downloads
        "/legacy/": 5,  # Higher cost for uploads
        "/api/upload": 5,  # Higher cost for uploads
        "/": 1,  # Default cost
    },
)

# Initialize the application state
app.state.settings = settings
app.state.state = setup_app_state(app, settings)

# Configure routes
setup_routes(app)


# Add middleware for request logging
@app.middleware("http")
async def log_requests(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """Log all incoming requests and responses."""
    import time

    start_time = time.time()

    response = await call_next(request)

    process_time = time.time() - start_time
    logging.info(
        f"{request.method} {request.url.path} "
        f"- Status: {response.status_code} "
        f"- Process time: {process_time:.4f}s"
    )

    return response
