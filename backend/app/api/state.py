import logging
import traceback

from fastapi import FastAPI

from app.core.clients.postgres import PostgresClient
from app.core.clients.s3 import S3Client
from app.core.clients.valkey import ValkeyClient
from app.core.config import Settings
from app.repos.postgres import (
    PostgresFileRepository,
    PostgresProjectRepository,
    PostgresReleaseRepository,
)
from app.repos.s3 import S3StorageRepository
from app.repos.valkey import ValkeyCacheRepository
from app.services.auth_service import AuthService
from app.services.file_service import FileService
from app.services.project_service import ProjectService

logger = logging.getLogger(__name__)


class Services:
    """Container for application services."""

    def __init__(self) -> None:
        self.project: ProjectService | None = None
        self.file: FileService | None = None
        self.auth: AuthService | None = None


class AppState:
    """Application state containing clients, repositories, and services."""

    def __init__(self, settings: Settings):
        self.settings = settings

        # Clients
        self.postgres: PostgresClient | None = None
        self.s3: S3Client | None = None
        self.valkey: ValkeyClient | None = None

        # Repositories
        self.project_repo: PostgresProjectRepository | None = None
        self.release_repo: PostgresReleaseRepository | None = None
        self.file_repo: PostgresFileRepository | None = None
        self.storage_repo: S3StorageRepository | None = None
        self.cache_repo: ValkeyCacheRepository | None = None

        # Services
        self.services = Services()
        # For backward compatibility
        self.project_service: ProjectService | None = None
        self.file_service: FileService | None = None

    async def initialize(self) -> None:
        """Initialize all clients, repositories, and services."""
        logger.info("Initializing application state")

        # Initialize clients with error handling
        try:
            logger.info("Initializing PostgreSQL client")
            self.postgres = PostgresClient(self.settings.postgres)
            await self.postgres.initialize()
        except Exception:
            logger.exception("Failed to initialize PostgreSQL client")
            logger.debug(traceback.format_exc())
            # Continue even if PostgreSQL fails, but service will be degraded
            self.postgres = None

        try:
            logger.info("Initializing S3 client")
            self.s3 = S3Client(self.settings.s3)
            await self.s3.initialize()
        except Exception:
            logger.exception("Failed to initialize S3 client")
            logger.debug(traceback.format_exc())
            # Continue even if S3 fails, but service will be degraded
            self.s3 = None

        try:
            logger.info("Initializing Valkey client")
            self.valkey = ValkeyClient(self.settings.valkey)
            await self.valkey.initialize()
        except Exception:
            logger.exception("Failed to initialize Valkey client")
            logger.debug(traceback.format_exc())
            # Continue even if Valkey fails, but service will be degraded
            self.valkey = None

        # Initialize repositories with error handling
        logger.info("Initializing repositories")
        if self.postgres:
            self.project_repo = PostgresProjectRepository(self.postgres)
            self.release_repo = PostgresReleaseRepository(self.postgres)
            self.file_repo = PostgresFileRepository(self.postgres)
        else:
            logger.warning(
                "PostgreSQL repositories unavailable due to client initialization failure"
            )
            self.project_repo = None
            self.release_repo = None
            self.file_repo = None

        if self.s3:
            self.storage_repo = S3StorageRepository(self.s3)
        else:
            logger.warning(
                "S3 storage repository unavailable due to client initialization failure"
            )
            self.storage_repo = None

        if self.valkey:
            self.cache_repo = ValkeyCacheRepository(self.valkey)
        else:
            logger.warning(
                "Valkey cache repository unavailable due to client initialization failure"
            )
            self.cache_repo = None

        # Initialize services
        logger.info("Initializing services")

        if self.project_repo and self.release_repo and self.file_repo:
            self.services.project = ProjectService(
                self.project_repo,
                self.release_repo,
                self.file_repo,
                self.cache_repo,  # Cache repo is optional
            )
            # For backward compatibility
            self.project_service = self.services.project
            logger.info("ProjectService initialized")
        else:
            logger.warning(
                "ProjectService unavailable due to repository initialization failures"
            )
            self.services.project = None
            self.project_service = None

        if self.file_repo and self.storage_repo:
            self.services.file = FileService(
                self.file_repo,
                self.storage_repo,
                self.cache_repo,  # Cache repo is optional
            )
            # For backward compatibility
            self.file_service = self.services.file
            logger.info("FileService initialized")
        else:
            logger.warning(
                "FileService unavailable due to repository initialization failures"
            )
            self.services.file = None
            self.file_service = None

        if self.postgres:
            self.services.auth = AuthService(
                self.postgres,
                self.cache_repo,  # Cache repo is optional
            )
            logger.info("AuthService initialized")
        else:
            logger.warning(
                "AuthService unavailable due to PostgreSQL initialization failure"
            )
            self.services.auth = None

        logger.info("Application state initialization complete")

    async def cleanup(self) -> None:
        """Clean up all clients."""
        logger.info("Cleaning up application state")

        if self.postgres:
            try:
                logger.info("Cleaning up PostgreSQL client")
                await self.postgres.cleanup()
            except Exception:
                logger.exception("Error during PostgreSQL cleanup")
                logger.debug(traceback.format_exc())

        if self.s3:
            try:
                logger.info("Cleaning up S3 client")
                await self.s3.cleanup()
            except Exception:
                logger.exception("Error during S3 cleanup")
                logger.debug(traceback.format_exc())

        if self.valkey:
            try:
                logger.info("Cleaning up Valkey client")
                await self.valkey.cleanup()
            except Exception:
                logger.exception("Error during Valkey cleanup")
                logger.debug(traceback.format_exc())

        logger.info("Application state cleanup complete")


def setup_app_state(app: FastAPI, settings: Settings) -> AppState:
    """Create and configure application state with clients, repositories, and services."""
    state = AppState(settings)

    @app.on_event("startup")
    async def startup_event() -> None:
        await state.initialize()

    @app.on_event("shutdown")
    async def shutdown_event() -> None:
        await state.cleanup()

    return state
