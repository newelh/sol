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

    await conn.execute("""
    CREATE TABLE IF NOT EXISTS api_keys (
        id SERIAL PRIMARY KEY,
        key TEXT NOT NULL,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        scopes JSONB DEFAULT '["download"]'::JSONB,
        created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW(),
        expires_at TIMESTAMP WITH TIME ZONE NOT NULL,
        UNIQUE(key)
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

                await conn.execute(
                    """
                    INSERT INTO api_keys (
                        key, user_id, scopes, expires_at
                    ) VALUES (
                        'testpassword', $1, '["download", "upload"]', $2
                    )
                    """,
                    user_id,
                    expires_at,
                )
                logging.info("Test API key created successfully.")
            else:
                logging.info("Test API key already exists.")
    except Exception:
        logging.exception("Error creating test user or API key")


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
