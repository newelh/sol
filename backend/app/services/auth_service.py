import json
import logging
import uuid
from datetime import datetime, timedelta
from typing import Any

import httpx
import jwt

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

# JWT settings
JWT_SECRET_KEY = settings.auth.jwt_secret_key
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_DELTA = timedelta(minutes=settings.auth.token_expire_minutes)


class AuthService:
    """
    Service for handling authentication and user management.

    Uses OAuth2 providers for authentication and manages API keys.
    User data is stored in PostgreSQL database.
    """

    def __init__(self, postgres_client: Any, cache_repo: Any = None) -> None:
        """Initialize the auth service with database and cache clients."""
        self.postgres = postgres_client
        self.cache = cache_repo

    async def create_access_token(self, data: dict) -> str:
        """
        Create a JWT access token with specified payload.

        Args:
            data: Payload to include in the token

        Returns:
            Encoded JWT token

        """
        to_encode = data.copy()
        expire = datetime.utcnow() + JWT_EXPIRATION_DELTA
        to_encode.update({"exp": expire})

        return jwt.encode(to_encode, JWT_SECRET_KEY, algorithm=JWT_ALGORITHM)

    async def get_user_by_id(self, user_id: str) -> dict | None:
        """
        Get user information by user ID.

        Args:
            user_id: Unique user identifier

        Returns:
            User data dictionary or None if not found

        """
        # Try cache first
        if self.cache:
            cached_user = await self.cache.get(f"user:{user_id}")
            if cached_user:
                return cached_user

        # Query database
        query = """
        SELECT
            id, username, email, scopes,
            created_at, updated_at, oauth_provider
        FROM users
        WHERE id = $1
        """
        user_row = await self.postgres.fetchrow(query, user_id)

        if not user_row:
            return None

        # Convert to dict
        user = {
            "user_id": user_row["id"],
            "username": user_row["username"],
            "email": user_row["email"],
            "scopes": user_row["scopes"],
            "created_at": user_row["created_at"].isoformat(),
            "updated_at": user_row["updated_at"].isoformat(),
            "oauth_provider": user_row["oauth_provider"],
        }

        # Cache the result
        if self.cache:
            await self.cache.set(f"user:{user_id}", user, expire=300)  # 5 minutes

        return user

    async def verify_oauth_token(self, token: str, provider: str) -> dict | None:
        """
        Verify an OAuth token with the provider and retrieve user information.

        Args:
            token: OAuth access token
            provider: OAuth provider name (github, google, microsoft)

        Returns:
            User information or None if token is invalid

        """
        if provider not in settings.auth.allowed_oauth_providers:
            logger.error(f"OAuth provider not supported: {provider}")
            return None

        try:
            # Verify token with provider
            user_data = await self._get_user_from_provider(token, provider)
            if not user_data:
                return None

            # Find or create user in database
            user = await self._find_or_create_user(user_data, provider)
        except Exception:
            logger.exception("Error verifying OAuth token")
            return None
        else:
            return user

    async def create_api_key(
        self, user_id: str, scopes: list[str], expires_in_days: int | None = None
    ) -> dict[str, Any]:
        """
        Create a new API key for a user.

        Args:
            user_id: The user ID to create the key for
            scopes: List of permission scopes for this key
            expires_in_days: Days until key expires (default from settings)

        Returns:
            API key information

        """
        # Generate a unique API key
        api_key = str(uuid.uuid4())

        # Set expiry
        if expires_in_days is None:
            expires_in_days = settings.auth.api_key_expiry_days

        expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

        # Store in database
        query = """
        INSERT INTO api_keys (key, user_id, scopes, expires_at)
        VALUES ($1, $2, $3, $4)
        RETURNING id, key, scopes, created_at, expires_at
        """
        row = await self.postgres.fetchrow(
            query, api_key, user_id, json.dumps(scopes), expires_at
        )

        # Return key info
        return {
            "id": row["id"],
            "key": row["key"],
            "scopes": json.loads(row["scopes"]),
            "created_at": row["created_at"].isoformat(),
            "expires_at": row["expires_at"].isoformat(),
        }

    async def verify_api_key(self, api_key: str) -> dict | None:
        """
        Verify an API key and return user information.

        Args:
            api_key: The API key to verify

        Returns:
            User information or None if key is invalid

        """
        # Try cache first
        if self.cache:
            cached_result = await self.cache.get(f"api_key:{api_key}")
            if cached_result:
                return cached_result

        # Get API key info
        query = """
        SELECT
            k.id, k.key, k.user_id, k.scopes, k.expires_at,
            u.username, u.email
        FROM api_keys k
        JOIN users u ON k.user_id = u.id
        WHERE k.key = $1 AND k.expires_at > $2
        """
        row = await self.postgres.fetchrow(query, api_key, datetime.utcnow())

        if not row:
            return None

        # Build user info
        user = {
            "user_id": row["user_id"],
            "username": row["username"],
            "email": row["email"],
            "scopes": json.loads(row["scopes"]),
            "api_key_id": row["id"],
        }

        # Cache result
        if self.cache:
            # Cache for 5 minutes
            await self.cache.set(f"api_key:{api_key}", user, expire=300)

        return user

    async def _get_user_from_provider(self, token: str, provider: str) -> dict | None:
        """
        Get user information from OAuth provider.

        Args:
            token: OAuth access token
            provider: OAuth provider name

        Returns:
            User data from provider or None if invalid

        """
        try:
            if provider == "github":
                return await self._get_github_user(token)
            elif provider == "google":
                return await self._get_google_user(token)
            elif provider == "microsoft":
                return await self._get_microsoft_user(token)
            else:
                logger.error(f"Unsupported OAuth provider: {provider}")
                return None

        except Exception:
            logger.exception(f"Error getting user from provider {provider}")
            return None

    async def _get_github_user(self, token: str) -> dict | None:
        """Get user data from GitHub."""
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"token {token}"}
            response = await client.get("https://api.github.com/user", headers=headers)

            if response.status_code != 200:
                logger.error(
                    f"GitHub API error: {response.status_code} {response.text}"
                )
                return None

            user_data = response.json()

            # Get email (which might be private)
            emails_response = await client.get(
                "https://api.github.com/user/emails", headers=headers
            )

            primary_email = None
            if emails_response.status_code == 200:
                emails = emails_response.json()
                for email in emails:
                    if email.get("primary", False):
                        primary_email = email.get("email")
                        break

            return {
                "provider_id": str(user_data["id"]),
                "username": user_data["login"],
                "name": user_data.get("name"),
                "email": primary_email or user_data.get("email"),
                "avatar_url": user_data.get("avatar_url"),
            }

    async def _get_google_user(self, token: str) -> dict | None:
        """Get user data from Google."""
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {token}"}
            response = await client.get(
                "https://www.googleapis.com/oauth2/v3/userinfo", headers=headers
            )

            if response.status_code != 200:
                logger.error(
                    f"Google API error: {response.status_code} {response.text}"
                )
                return None

            user_data = response.json()

            return {
                "provider_id": user_data["sub"],
                "username": user_data.get("name", "").replace(" ", "").lower()
                or user_data["sub"],
                "name": user_data.get("name"),
                "email": user_data.get("email"),
                "avatar_url": user_data.get("picture"),
            }

    async def _get_microsoft_user(self, token: str) -> dict | None:
        """Get user data from Microsoft."""
        async with httpx.AsyncClient() as client:
            headers = {"Authorization": f"Bearer {token}"}
            response = await client.get(
                "https://graph.microsoft.com/v1.0/me", headers=headers
            )

            if response.status_code != 200:
                logger.error(
                    f"Microsoft API error: {response.status_code} {response.text}"
                )
                return None

            user_data = response.json()

            return {
                "provider_id": user_data["id"],
                "username": user_data.get("userPrincipalName", "").split("@")[0]
                or user_data["id"],
                "name": user_data.get("displayName"),
                "email": user_data.get("mail") or user_data.get("userPrincipalName"),
                "avatar_url": None,  # Microsoft Graph requires additional permissions for photo
            }

    async def _find_or_create_user(self, provider_user: dict, provider: str) -> dict:
        """
        Find or create user in database based on OAuth provider data.

        Args:
            provider_user: User data from OAuth provider
            provider: OAuth provider name

        Returns:
            User data from database

        """
        # Look up user by provider ID and provider
        query = """
        SELECT
            id, username, email, scopes,
            created_at, updated_at, oauth_provider
        FROM users
        WHERE provider_id = $1 AND oauth_provider = $2
        """
        user_row = await self.postgres.fetchrow(
            query, provider_user["provider_id"], provider
        )

        if user_row:
            # User exists, update if needed
            if (
                user_row["email"] != provider_user["email"]
                or user_row["username"] != provider_user["username"]
            ):
                update_query = """
                UPDATE users
                SET email = $3, username = $4, updated_at = $5
                WHERE provider_id = $1 AND oauth_provider = $2
                RETURNING id, username, email, scopes,
                          created_at, updated_at, oauth_provider
                """
                user_row = await self.postgres.fetchrow(
                    update_query,
                    provider_user["provider_id"],
                    provider,
                    provider_user["email"],
                    provider_user["username"],
                    datetime.utcnow(),
                )
        else:
            # Create new user
            insert_query = """
            INSERT INTO users (
                provider_id, oauth_provider, username,
                email, name, scopes, created_at, updated_at
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8
            )
            RETURNING id, username, email, scopes,
                      created_at, updated_at, oauth_provider
            """
            # New users get download scope by default
            scopes = ["download"]

            user_row = await self.postgres.fetchrow(
                insert_query,
                provider_user["provider_id"],
                provider,
                provider_user["username"],
                provider_user["email"],
                provider_user.get("name"),
                json.dumps(scopes),
                datetime.utcnow(),
                datetime.utcnow(),
            )

        # Convert to dict
        user = {
            "user_id": user_row["id"],
            "username": user_row["username"],
            "email": user_row["email"],
            "scopes": json.loads(user_row["scopes"]),
            "created_at": user_row["created_at"].isoformat(),
            "updated_at": user_row["updated_at"].isoformat(),
            "oauth_provider": user_row["oauth_provider"],
        }

        # Cache the result
        if self.cache:
            await self.cache.set(f"user:{user['user_id']}", user, expire=300)

        return user
