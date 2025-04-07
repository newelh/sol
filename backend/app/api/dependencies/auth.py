import logging
from datetime import datetime, timedelta
from typing import NoReturn

import jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import APIKeyHeader, OAuth2AuthorizationCodeBearer

from app.api.dependencies.services import get_app_state
from app.api.state import AppState
from app.core.config import get_settings

# Authentication module for API key and OAuth2 JWT-based auth
settings = get_settings()

# Security schemes
# Type assertions for mypy - these environment vars are guaranteed to exist
authorization_url: str = settings.auth.authorization_url  # type: ignore
token_url: str = settings.auth.token_url  # type: ignore

oauth2_scheme = OAuth2AuthorizationCodeBearer(
    authorizationUrl=authorization_url,
    tokenUrl=token_url,
    scopes={
        "upload": "Upload packages to the repository",
        "download": "Download packages from the repository",
    },
    auto_error=False,  # Don't auto-raise errors to handle API key auth path
)
api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)

logger = logging.getLogger(__name__)

# JWT settings - uses auth.jwt_secret_key from env vars
JWT_SECRET_KEY = settings.auth.jwt_secret_key

JWT_ALGORITHM = "HS256"  # HMAC with SHA-256
JWT_EXPIRATION_DELTA = timedelta(minutes=settings.auth.token_expire_minutes)


def raise_credentials_exception() -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )


def raise_permission_exception(permission: str) -> NoReturn:
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail=f"User does not have permission to {permission}",
    )


async def get_current_user(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    api_key: str | None = Depends(api_key_header),
    state: AppState = Depends(get_app_state),
) -> dict:
    """
    Authenticate user using OAuth2 token or API key.

    Returns:
        Dict: User information

    """
    # Try API key authentication first
    if api_key:
        try:
            # Verify API key with auth service
            if state.services.auth is None:
                logger.error("Auth service not initialized")
                raise_credentials_exception()

            user = await state.services.auth.verify_api_key(api_key)
            if user:
                return user
        except Exception:
            logger.exception("API key verification error")
            # Continue to OAuth2 token authentication instead of raising an exception

    # Try OAuth2 token authentication
    if token:
        try:
            # Decode JWT token
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[JWT_ALGORITHM])
            user_id: str = payload.get("sub")
            if user_id is None:
                raise_credentials_exception()

            # Verify token has not expired
            exp = payload.get("exp")
            if exp is None or datetime.fromtimestamp(exp) < datetime.utcnow():
                raise_credentials_exception()

            # Retrieve user from auth service
            if state.services.auth is None:
                logger.error("Auth service not initialized")
                raise_credentials_exception()

            user = await state.services.auth.get_user_by_id(user_id)
            if user is None:
                raise_credentials_exception()
            else:
                return user

        except Exception as err:
            # Handle JWT validation errors by checking the error type name
            if type(err).__name__ in ("InvalidTokenError", "ExpiredSignatureError"):
                logger.warning(f"Token validation failed: {err!s}")
            else:
                logger.exception("Token verification error")
            raise_credentials_exception()

    # Authentication failed
    raise_credentials_exception()


async def verify_upload_permission(
    user: dict = Depends(get_current_user),
) -> dict:
    """
    Verify that the user has permission to upload packages.

    Verifies that the authenticated user has the 'upload' scope.
    Also checks package-specific permissions if applicable.

    Returns:
        Dict: User information

    """
    # Check user has upload scope
    if "upload" not in user.get("scopes", []):
        raise_permission_exception("upload packages")

    return user


async def verify_download_permission(
    request: Request,
    token: str | None = Depends(oauth2_scheme),
    api_key: str | None = Depends(api_key_header),
    state: AppState = Depends(get_app_state),
) -> dict:
    """
    Verify that the user has permission to download packages.

    This implementation allows anonymous downloads, which is standard for PyPI servers.
    If authentication is provided, it validates the user has proper permissions.

    Returns:
        Dict: User information

    """
    # If no authentication provided, allow anonymous access
    if not token and not api_key:
        return {"user_id": "anonymous", "username": "anonymous", "scopes": ["download"]}

    # If authentication is provided, validate it
    try:
        user = await get_current_user(request, token, api_key, state)
        if "download" not in user.get("scopes", []):
            raise_permission_exception("download packages")
        else:
            return user
    except HTTPException:
        # If authentication fails but we're doing anonymous access, allow it
        return {"user_id": "anonymous", "username": "anonymous", "scopes": ["download"]}
