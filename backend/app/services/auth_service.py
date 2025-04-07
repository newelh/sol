import base64
import contextlib
import hashlib
import json
import logging
import os
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

    async def create_access_token(
        self, data: dict, expires_delta: timedelta | None = None
    ) -> str:
        """
        Create a JWT access token with specified payload.

        Args:
            data: Payload to include in the token
            expires_delta: Optional custom expiration time

        Returns:
            Encoded JWT token

        """
        from app.api.dependencies.auth import JWT_ALGORITHM, JWT_SECRET_KEY

        to_encode = data.copy()

        # Use provided expiration or default from settings
        if expires_delta:
            expire = datetime.utcnow() + expires_delta
        else:
            from app.api.dependencies.auth import JWT_EXPIRATION_DELTA

            expire = datetime.utcnow() + JWT_EXPIRATION_DELTA

        to_encode.update({"exp": expire})

        # Add issued at time for security
        to_encode.update({"iat": datetime.utcnow()})

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
        self,
        user_id: str,
        scopes: list[str],
        expires_in_days: int | None = None,
        description: str = "",
    ) -> dict[str, Any]:
        """
        Create a new API key for a user.

        Args:
            user_id: The user ID to create the key for
            scopes: List of permission scopes for this key
            expires_in_days: Days until key expires (default from settings)
            description: Optional description for this API key

        Returns:
            API key information including the original key (only returned once)

        """
        # Generate a unique API key with more entropy
        # Format: prefix_base64(uuid4)_base64(32 random bytes)
        key_prefix = "sol"
        uuid_part = (
            base64.urlsafe_b64encode(uuid.uuid4().bytes).decode("ascii").rstrip("=")
        )
        random_part = (
            base64.urlsafe_b64encode(os.urandom(32)).decode("ascii").rstrip("=")
        )
        api_key = f"{key_prefix}_{uuid_part}_{random_part}"

        # Generate a key ID (first 8 chars of uuid)
        key_id = uuid_part[:8]

        # Hash the API key for storage
        # Use a strong hashing algorithm with salt
        salt = os.urandom(16)
        key_hash = hashlib.pbkdf2_hmac(
            "sha256",
            api_key.encode(),
            salt,
            100000,  # Use 100,000 iterations for PBKDF2
        )

        # Store the salt and hash separately
        salt_hex = salt.hex()
        key_hash_hex = key_hash.hex()

        # Set expiry
        if expires_in_days is None:
            expires_in_days = settings.auth.api_key_expiry_days

        expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

        # Check if the API key already exists (by user_id and description)
        if description:
            existing_query = """
            SELECT id FROM api_keys
            WHERE user_id = $1 AND description = $2
            """
            existing = await self.postgres.fetchrow(
                existing_query, user_id, description
            )

            if existing:
                # Revoke the existing key first
                await self.revoke_api_key(existing["id"])

        # Store in database - don't store the actual key, only its hash
        query = """
        INSERT INTO api_keys (
            key_id, key_hash, key_salt, user_id, scopes,
            expires_at, description, last_used_at
        )
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
        RETURNING id, key_id, scopes, created_at, expires_at, description
        """
        now = datetime.utcnow()
        row = await self.postgres.fetchrow(
            query,
            key_id,
            key_hash_hex,
            salt_hex,
            user_id,
            json.dumps(scopes),
            expires_at,
            description,
            now,
        )

        # Return key info including the original key
        # Note: This is the only time the actual key will be returned
        return {
            "id": row["id"],
            "key": api_key,  # Only returned once at creation
            "key_id": row["key_id"],  # Public identifier of the key
            "scopes": json.loads(row["scopes"]),
            "created_at": row["created_at"].isoformat(),
            "expires_at": row["expires_at"].isoformat(),
            "description": row["description"] if row["description"] else None,
        }

    async def verify_api_key(self, api_key: str) -> dict | None:
        """
        Verify an API key and return user information.

        Args:
            api_key: The API key to verify

        Returns:
            User information or None if key is invalid

        """
        # Check for development/test mode special case
        if settings.server.environment == "development" and api_key == "testpassword":
            # Special case for test environment - directly query the database for this key
            logger.info("Using test mode API key authentication")
            query = """
            SELECT
                k.id, k.key, k.user_id, k.scopes, k.expires_at,
                u.username, u.email
            FROM api_keys k
            JOIN users u ON k.user_id = u.id
            WHERE k.key = $1 AND k.expires_at > $2
            """
            row = await self.postgres.fetchrow(query, api_key, datetime.utcnow())

            if row:
                # Build user info
                return {
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "email": row["email"],
                    "scopes": json.loads(row["scopes"]),
                    "api_key_id": row["id"],
                    "key_id": "test",  # Placeholder for test key
                    "expires_at": row["expires_at"].isoformat()
                    if row["expires_at"]
                    else None,
                }

        # Regular API key validation for production keys
        # Check if the API key has the correct format
        if not api_key or not isinstance(api_key, str):
            return None

        # Validate key format: prefix_uuid_random
        parts = api_key.split("_")
        if len(parts) != 3 or parts[0] != "sol":
            # Try legacy key format (direct key lookup)
            query = """
            SELECT
                k.id, k.key, k.user_id, k.scopes, k.expires_at,
                u.username, u.email
            FROM api_keys k
            JOIN users u ON k.user_id = u.id
            WHERE k.key = $1 AND k.expires_at > $2
            """
            row = await self.postgres.fetchrow(query, api_key, datetime.utcnow())

            if row:
                # Build user info for legacy key
                return {
                    "user_id": row["user_id"],
                    "username": row["username"],
                    "email": row["email"],
                    "scopes": json.loads(row["scopes"]),
                    "api_key_id": row["id"],
                    "expires_at": row["expires_at"].isoformat()
                    if row["expires_at"]
                    else None,
                }
            return None

        # Extract the key ID from the UUID part
        try:
            key_id = parts[1][:8]  # First 8 chars of the uuid part
        except (IndexError, AttributeError):
            return None

        # Try cache first with a derived cache key (not the actual API key)
        cache_key = f"api_key_hash:{hashlib.sha256(api_key.encode()).hexdigest()}"
        if self.cache:
            cached_result = await self.cache.get(cache_key)
            if cached_result:
                # Update last used time asynchronously
                update_query = """
                UPDATE api_keys
                SET last_used_at = $1
                WHERE id = $2
                """
                try:
                    await self.postgres.execute(
                        update_query, datetime.utcnow(), cached_result.get("api_key_id")
                    )
                except Exception:
                    # Non-critical error, just log it
                    logger.warning(
                        f"Failed to update last_used_at for API key: {key_id}"
                    )

                return cached_result

        # Get API key record by key_id
        query = """
        SELECT
            k.id, k.key_id, k.key_hash, k.key_salt,
            k.user_id, k.scopes, k.expires_at, k.description,
            u.username, u.email
        FROM api_keys k
        JOIN users u ON k.user_id = u.id
        WHERE k.key_id = $1 AND k.expires_at > $2
        """
        now = datetime.utcnow()
        row = await self.postgres.fetchrow(query, key_id, now)

        if not row:
            return None

        # Check if we have the new format with hash
        if row.get("key_hash") and row.get("key_salt"):
            # Verify the key hash
            try:
                # Get the stored hash and salt
                stored_hash = bytes.fromhex(row["key_hash"])
                salt = bytes.fromhex(row["key_salt"])

                # Calculate hash from provided key
                key_hash = hashlib.pbkdf2_hmac(
                    "sha256",
                    api_key.encode(),
                    salt,
                    100000,  # Same iteration count as when creating
                )

                # Compare in constant time to prevent timing attacks
                import hmac

                if not hmac.compare_digest(key_hash, stored_hash):
                    return None
            except Exception:
                logger.exception("Error verifying API key")
                return None

        # Update last used time
        update_query = """
        UPDATE api_keys
        SET last_used_at = $1
        WHERE id = $2
        """
        try:
            await self.postgres.execute(update_query, now, row["id"])
        except Exception as e:
            # Non-critical error, just log it
            logger.warning(f"Failed to update last_used_at for API key: {e}")

        # Build user info
        user = {
            "user_id": row["user_id"],
            "username": row["username"],
            "email": row["email"],
            "scopes": json.loads(row["scopes"]),
            "api_key_id": row["id"],
            "key_id": row.get(
                "key_id", "legacy"
            ),  # Include the public key ID or mark as legacy
            "expires_at": row["expires_at"].isoformat() if row["expires_at"] else None,
        }

        # Cache result
        if self.cache:
            # Cache for 5 minutes
            await self.cache.set(cache_key, user, expire=300)

        return user

    async def revoke_api_key(self, key_id: int) -> bool:
        """
        Revoke an API key.

        Args:
            key_id: The internal ID of the key to revoke

        Returns:
            True if key was revoked, False otherwise
        """
        query = """
        UPDATE api_keys
        SET revoked = TRUE, revoked_at = $1
        WHERE id = $2
        RETURNING id, key_id
        """

        try:
            row = await self.postgres.fetchrow(query, datetime.utcnow(), key_id)

            # Clear cache entries for this key
            if self.cache and row and row.get("key_id"):
                # We don't know the exact cache key since it's derived from the full API key
                # which we don't store. The best we can do is invalidate potential cache keys
                # by pattern if the cache backend supports it.
                # Use contextlib.suppress to handle the case where pattern deletion isn't supported
                with contextlib.suppress(Exception):
                    await self.cache.delete("api_key_hash:*")
                    logger.debug("Cleared API key cache entries with pattern deletion")

        except Exception:
            logger.exception("Failed to revoke API key")
            return False
        else:
            return row is not None

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
