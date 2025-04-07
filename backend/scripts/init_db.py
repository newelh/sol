import asyncio
import logging
import os
import sys

import asyncpg

# Add the parent directory to the path so we can import app modules
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.core.config import get_settings


async def create_tables(conn: asyncpg.Connection) -> None:
    """Create database tables."""
    # User authentication tables
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id SERIAL PRIMARY KEY,
        username TEXT NOT NULL,
        email TEXT NOT NULL,
        name TEXT,
        provider_id TEXT NOT NULL,
        oauth_provider TEXT NOT NULL,
        scopes JSONB DEFAULT '["download"]'::JSONB,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(provider_id, oauth_provider),
        UNIQUE(username)
    );
    """)

    # Update API keys table with new fields for secure key storage
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS api_keys (
        id SERIAL PRIMARY KEY,
        key TEXT, -- Legacy field, will be phased out
        key_id TEXT, -- Public identifier of the key (first part of the key)
        key_hash TEXT, -- Secure hash of the full key
        key_salt TEXT, -- Salt used for hashing
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        scopes JSONB DEFAULT '["download"]'::JSONB,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        last_used_at TIMESTAMP WITH TIME ZONE,
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        revoked BOOLEAN DEFAULT FALSE,
        revoked_at TIMESTAMP WITH TIME ZONE,
        description TEXT,
        UNIQUE(key) -- For backward compatibility
    );
    """)

    # Project-related tables
    await conn.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        normalized_name TEXT NOT NULL,
        description TEXT,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(normalized_name)
    );
    """)

    await conn.execute("""
    CREATE TABLE IF NOT EXISTS project_permissions (
        id SERIAL PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        role TEXT NOT NULL, -- 'owner', 'maintainer', 'contributor'
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        UNIQUE(project_id, user_id)
    );
    """)

    await conn.execute("""
    CREATE TABLE IF NOT EXISTS releases (
        id SERIAL PRIMARY KEY,
        project_id INTEGER NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        version TEXT NOT NULL,
        requires_python TEXT,
        is_prerelease BOOLEAN DEFAULT FALSE,
        yanked BOOLEAN DEFAULT FALSE,
        yank_reason TEXT,
        uploaded_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        uploaded_by INTEGER REFERENCES users(id),
        summary TEXT,
        description TEXT,
        author TEXT,
        author_email TEXT,
        maintainer TEXT,
        maintainer_email TEXT,
        license TEXT,
        keywords TEXT,
        classifiers JSONB DEFAULT '[]'::JSONB,
        platform TEXT,
        home_page TEXT,
        download_url TEXT,
        requires_dist JSONB DEFAULT '[]'::JSONB,
        provides_dist JSONB DEFAULT '[]'::JSONB,
        obsoletes_dist JSONB DEFAULT '[]'::JSONB,
        requires_external JSONB DEFAULT '[]'::JSONB,
        project_urls JSONB DEFAULT '{}'::JSONB,
        UNIQUE(project_id, version)
    );
    """)

    await conn.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id SERIAL PRIMARY KEY,
        release_id INTEGER NOT NULL REFERENCES releases(id) ON DELETE CASCADE,
        filename TEXT NOT NULL,
        size INTEGER NOT NULL,
        md5_digest TEXT,
        sha256_digest TEXT NOT NULL,
        blake2_256_digest TEXT,
        upload_time TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        uploaded_by INTEGER REFERENCES users(id),
        path TEXT NOT NULL,
        content_type TEXT NOT NULL,
        packagetype TEXT NOT NULL,
        python_version TEXT NOT NULL,
        requires_python TEXT,
        has_signature BOOLEAN DEFAULT FALSE,
        has_metadata BOOLEAN DEFAULT FALSE,
        metadata_sha256 TEXT,
        is_yanked BOOLEAN DEFAULT FALSE,
        yank_reason TEXT,
        metadata_version TEXT,
        summary TEXT,
        description TEXT,
        description_content_type TEXT,
        author TEXT,
        author_email TEXT,
        maintainer TEXT,
        maintainer_email TEXT,
        license TEXT,
        keywords TEXT,
        classifiers JSONB DEFAULT '[]'::JSONB,
        platform TEXT,
        home_page TEXT,
        download_url TEXT,
        requires_dist JSONB DEFAULT '[]'::JSONB,
        provides_dist JSONB DEFAULT '[]'::JSONB,
        obsoletes_dist JSONB DEFAULT '[]'::JSONB,
        requires_external JSONB DEFAULT '[]'::JSONB,
        project_urls JSONB DEFAULT '{}'::JSONB,
        -- Download statistics fields
        download_count INTEGER DEFAULT 0,
        last_download TIMESTAMP WITH TIME ZONE,
        download_stats JSONB DEFAULT '{}'::JSONB,
        UNIQUE(release_id, filename)
    );
    """)

    # Create indexes
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_username ON users (username);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_users_provider ON users (provider_id, oauth_provider);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_keys_user_id ON api_keys (user_id);"
    )
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_api_keys_key ON api_keys (key);")
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_permissions_user_id ON project_permissions (user_id);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_project_permissions_project_id ON project_permissions (project_id);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_projects_normalized_name ON projects (normalized_name);"
    )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_releases_project_id ON releases (project_id);"
    )
    # Skip this index since the column uploaded_by might not exist in older schema versions
    # await conn.execute(
    #     "CREATE INDEX IF NOT EXISTS idx_releases_uploaded_by ON releases (uploaded_by);"
    # )
    await conn.execute(
        "CREATE INDEX IF NOT EXISTS idx_files_release_id ON files (release_id);"
    )
    await conn.execute("CREATE INDEX IF NOT EXISTS idx_files_path ON files (path);")
    # Skip this index since the column uploaded_by might not exist in older schema versions
    # await conn.execute(
    #     "CREATE INDEX IF NOT EXISTS idx_files_uploaded_by ON files (uploaded_by);"
    # )


async def create_test_user(conn: asyncpg.Connection) -> None:
    """Create a test user for development."""
    # Create a test user
    try:
        # Check if test user already exists
        test_user = await conn.fetchrow(
            "SELECT * FROM users WHERE username = 'testuser'"
        )

        user_id = None
        if not test_user:
            # Create the test user
            user_id = await conn.fetchval(
                """
                INSERT INTO users (
                    username, email, name, provider_id, oauth_provider, scopes
                ) VALUES (
                    'testuser', 'test@example.com', 'Test User', 'test123', 'test',
                    '["download", "upload"]'
                ) RETURNING id
                """
            )
            logging.info(f"Test user created successfully with ID: {user_id}")
        else:
            user_id = test_user["id"]
            logging.info(f"Test user already exists with ID: {user_id}")

        # Create API key for the test user if it doesn't exist
        if user_id:
            api_key = await conn.fetchrow(
                "SELECT * FROM api_keys WHERE user_id = $1 AND key = 'testpassword'",
                user_id,
            )

            if not api_key:
                # Create an API key with expiration date 1 year from now
                from datetime import datetime, timedelta

                expires_at = datetime.utcnow() + timedelta(days=365)

                # Create hash and salt for secure storage
                import hashlib
                import os

                salt = os.urandom(16)
                salt_hex = salt.hex()

                # Hash the key
                key_hash = hashlib.pbkdf2_hmac(
                    "sha256",
                    b"testpassword",
                    salt,
                    100000,  # 100k iterations for security
                )
                key_hash_hex = key_hash.hex()

                # Insert with both old key field (for compatibility) and new secure fields
                await conn.execute(
                    """
                    INSERT INTO api_keys (
                        key, key_id, key_hash, key_salt, user_id, scopes,
                        expires_at, description, last_used_at
                    ) VALUES (
                        'testpassword', 'test', $1, $2, $3, '["download", "upload"]',
                        $4, 'Test API key for integration testing', NOW()
                    )
                    """,
                    key_hash_hex,
                    salt_hex,
                    user_id,
                    expires_at,
                )
                logging.info("Test API key created successfully with secure storage.")
            else:
                logging.info("Test API key already exists.")
    except Exception:
        logging.exception("Error creating test user or API key")


async def migrate_api_keys(conn: asyncpg.Connection) -> None:
    """Migrate existing API keys to the new secure schema."""
    try:
        # First check if we have the key_id column
        key_id_exists = False
        try:
            await conn.fetchval(
                """
                SELECT key_id FROM api_keys LIMIT 1
                """
            )
            key_id_exists = True
        except asyncpg.exceptions.UndefinedColumnError:
            key_id_exists = False

        # If the key_id column doesn't exist, skip the migration
        if not key_id_exists:
            logging.info(
                "Schema needs migration, but skipping as it will run next time"
            )
            return

        # Get a list of API keys that haven't been migrated yet
        # These will have key value but no key_hash
        rows = await conn.fetch(
            """
            SELECT id, key FROM api_keys
            WHERE key IS NOT NULL AND key_hash IS NULL
            """
        )

        if not rows:
            logging.info("No API keys need migration")
            return

        logging.info(f"Migrating {len(rows)} API keys to the new secure schema...")

        for row in rows:
            key_id = f"legacy_{row['id']}"

            # Create a hash of the key
            import hashlib
            import os

            salt = os.urandom(16)
            key_hash = hashlib.pbkdf2_hmac(
                "sha256",
                row["key"].encode(),
                salt,
                100000,  # Use 100,000 iterations for PBKDF2
            )

            # Store the hash and salt
            await conn.execute(
                """
                UPDATE api_keys
                SET key_id = $1, key_hash = $2, key_salt = $3, updated_at = NOW()
                WHERE id = $4
                """,
                key_id,
                key_hash.hex(),
                salt.hex(),
                row["id"],
            )

        logging.info(f"Successfully migrated {len(rows)} API keys")

    except Exception:
        logging.exception("Error migrating API keys")


async def main() -> None:
    """Initialize the database."""
    settings = get_settings()
    logging.basicConfig(level=logging.INFO)
    logger = logging.getLogger(__name__)

    try:
        # Connect to PostgreSQL
        logger.info(
            f"Connecting to PostgreSQL at {settings.postgres.host}:{settings.postgres.port}"
        )
        conn = await asyncpg.connect(
            host=settings.postgres.host,
            port=settings.postgres.port,
            user=settings.postgres.user,
            password=settings.postgres.password,
            database=settings.postgres.database,
        )

        # Create tables
        logger.info("Creating database tables...")
        await create_tables(conn)

        # Migrate API keys to new schema if needed
        logger.info("Checking for API key migration...")
        await migrate_api_keys(conn)

        # Create test user
        logger.info("Creating test user...")
        await create_test_user(conn)

        # Close connection
        logger.info("Database initialization completed successfully.")
        await conn.close()

    except Exception:
        logger.exception("Error initializing database")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
