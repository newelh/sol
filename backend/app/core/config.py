from pydantic_settings import BaseSettings, SettingsConfigDict

# =====================================================================
# Configuration Framework
# =====================================================================
# The application uses a hierarchical settings system that:
#
# 1. Prioritizes values from environment variables over defaults
# 2. Groups related settings into logical categories
# 3. Uses Pydantic for validation and type safety
# 4. Supports .env files for local development
# 5. Uses nested settings with appropriate prefixes
#
# Each setting can be overridden with environment variables following
# the pattern: PREFIX__SETTING_NAME. For example:
#   - POSTGRES_PASSWORD=secret
#   - S3_ENDPOINT_URL=http://minio:9000
#   - AUTH_JWT_SECRET_KEY=mysecretkey
# =====================================================================


class PostgresSettings(BaseSettings):
    """Settings for PostgreSQL client."""

    host: str = "localhost"  # Database server hostname/IP
    port: int = 5432  # PostgreSQL standard port
    user: str = "postgres"  # Database user for authentication
    password: str | None = (
        None  # Password - Must be provided via environment variables in production
    )
    database: str = "pypi"  # Database name to connect to
    min_connections: int = 1  # Minimum connections in pool (set higher in production)
    max_connections: int = 10  # Maximum simultaneous connections allowed
    statement_timeout: int | None = None  # Query timeout in seconds (None = no limit)

    model_config = SettingsConfigDict(env_prefix="POSTGRES_")


class S3Settings(BaseSettings):
    """Settings for S3 client."""

    endpoint_url: str = "http://localhost:9000"
    region_name: str = "us-east-1"
    access_key_id: str | None = (
        None  # Must be provided via environment variables in production
    )
    secret_access_key: str | None = (
        None  # Must be provided via environment variables in production
    )
    use_ssl: bool = True
    verify: bool = True
    default_bucket: str = "pypi"

    model_config = SettingsConfigDict(env_prefix="S3_")


class ValkeySettings(BaseSettings):
    """Settings for Valkey client."""

    host: str = "localhost"
    port: int = 6379
    password: str | None = None
    db: int = 0
    ssl: bool = False
    socket_timeout: int = 5
    socket_connect_timeout: int = 5
    health_check_interval: int = 30
    max_connections: int = 10

    model_config = SettingsConfigDict(env_prefix="VALKEY_")


class ServerSettings(BaseSettings):
    """Settings for the HTTP server."""

    host: str = "127.0.0.1"  # Default to localhost for security - only bind to all interfaces (0.0.0.0) when explicitly configured
    port: int = 8000
    debug: bool = False
    workers: int = 1
    environment: str = "development"

    # CORS settings
    cors_origins: list[str] = ["*"]

    # Rate limiting settings
    rate_limit_anon: float = 30.0  # Requests per second for anonymous users
    rate_limit_anon_capacity: int = 50  # Maximum burst capacity for anonymous users
    rate_limit_auth: float = 60.0  # Requests per second for authenticated users
    rate_limit_auth_capacity: int = (
        100  # Maximum burst capacity for authenticated users
    )

    model_config = SettingsConfigDict(env_prefix="SERVER_")


class AuthSettings(BaseSettings):
    """Authentication and authorization settings."""

    # OAuth2 settings
    authorization_url: str | None = None
    # URL to redirect users for OAuth login (e.g., GitHub login page)
    # Must be provided via environment variables in production

    token_url: str | None = None
    # URL to exchange authorization code for access token
    # Must be provided via environment variables in production

    jwt_secret_key: str | None = None
    # Secret key used to sign JWT tokens
    # REQUIRED: Must be at least 32 chars, high entropy in production
    # WARNING: Changing this invalidates all existing tokens!
    # Must be provided via environment variables in production

    token_expire_minutes: int = 60  # How long JWT tokens remain valid
    # Balance security (shorter) vs. UX (longer)
    # For production: 15-60 min recommended

    allowed_oauth_providers: list[str] = ["github", "google", "microsoft"]
    # List of enabled OAuth identity providers
    # Each requires additional provider-specific config

    # API keys
    api_key_expiry_days: int = 365  # Default validity period for API keys
    # Set to 0 for non-expiring keys (not recommended)
    # For CI/CD: 30-90 days recommended with rotation

    model_config = SettingsConfigDict(env_prefix="AUTH_")


class AppSettings(BaseSettings):
    """Application metadata settings."""

    name: str = "Sol PyPI"
    description: str = "A PEP-compliant PyPI index server"
    version: str = "0.1.0"

    model_config = SettingsConfigDict(env_prefix="APP_")


class Settings(BaseSettings):
    """Main application settings that aggregate all sub-settings."""

    app: AppSettings = AppSettings()
    server: ServerSettings = ServerSettings()
    postgres: PostgresSettings = PostgresSettings()
    s3: S3Settings = S3Settings()
    valkey: ValkeySettings = ValkeySettings()
    auth: AuthSettings = AuthSettings()

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", env_nested_delimiter="__"
    )


def get_settings() -> Settings:
    """Get application settings from environment variables."""
    return Settings()
