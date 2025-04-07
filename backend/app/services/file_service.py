import hashlib
import logging

from app.domain.models import File, Project, Release
from app.repos.interfaces import CacheRepository, FileRepository, StorageRepository

logger = logging.getLogger(__name__)


class InvalidProjectReleaseError(ValueError):
    """Raised when project and release do not have valid IDs."""

    def __init__(self) -> None:
        super().__init__("Project and release must have valid IDs")


class FileUploadError(RuntimeError):
    """Raised when file upload fails."""

    def __init__(self, path: str) -> None:
        super().__init__(f"Failed to upload file: {path}")


class FileService:
    """Service for working with package files."""

    def __init__(
        self,
        file_repo: FileRepository,
        storage_repo: StorageRepository,
        cache_repo: CacheRepository | None = None,
    ):
        self.file_repo = file_repo
        self.storage_repo = storage_repo
        self.cache_repo = cache_repo

    async def get_file(self, path: str) -> tuple[bytes, str, dict[str, str]]:
        """
        Get a file from storage.

        Args:
            path: The path to the file

        Returns:
            Tuple of (file_content, content_type, headers)

        """
        # Try to get file metadata from the database first
        # This would require a more complex lookup by path which isn't modeled yet
        # For simplicity, we'll just get the file from storage directly

        # Calculate cache key
        cache_key = f"file_content:{path}"

        # Try to get from cache first
        cached_content = None
        if self.cache_repo:
            cached_content = await self.cache_repo.get(cache_key)

        # Fetch from storage if not in cache
        if not cached_content:
            content = await self.storage_repo.get_file(path)

            # Get file metadata
            metadata = await self.storage_repo.get_file_metadata(path)
            content_type = metadata.get("content_type", "application/octet-stream")

            # Calculate headers
            headers = {
                "Content-Disposition": f'attachment; filename="{path.split("/")[-1]}"',
                "Content-Type": content_type,
                "Content-Length": str(len(content)),
                "ETag": metadata.get("etag", hashlib.sha256(content).hexdigest()[:32]),
            }

            # Add any metadata values as headers
            for key, value in metadata.items():
                if key not in ["content_type", "etag", "size"]:
                    headers[f"X-{key.capitalize()}"] = str(value)

            # Cache small files (< 5MB)
            if self.cache_repo and len(content) < 5 * 1024 * 1024:
                await self.cache_repo.set(
                    cache_key,
                    {
                        "content": content,
                        "content_type": content_type,
                        "headers": headers,
                    },
                    expire=60 * 10,  # Cache for 10 minutes
                )

            return content, content_type, headers
        else:
            # Use cached content
            return (
                cached_content["content"],
                cached_content["content_type"],
                cached_content["headers"],
            )

    async def get_file_metadata(self, file_id: int) -> File | None:
        """Get metadata for a file by ID."""
        # Try to get from cache first
        if self.cache_repo:
            cached = await self.cache_repo.get(f"file_metadata:{file_id}")
            if cached:
                return File.parse_obj(cached)

        # This needs a more complex implementation based on the actual schema
        # For now, we'll just return None
        return None

    async def upload_file(
        self,
        project: Project,
        release: Release,
        filename: str,
        content: bytes,
        content_type: str,
        metadata: dict | None = None,
    ) -> File:
        """
        Upload a file to storage and register it in the database.

        Args:
            project: The project the file belongs to
            release: The release the file belongs to
            filename: The name of the file
            content: The file content
            content_type: The content type of the file
            metadata: Optional metadata to attach to the file

        Returns:
            The created File object

        """
        if not project.id or not release.id:
            raise InvalidProjectReleaseError()

        # Get path for storing a file: {package_name}/{version}/{filename}

        path = f"{project.normalized_name}/{release.version}/{filename}"

        # Calculate hashes
        # Use MD5 only for backwards compatibility, not for security
        md5_digest = hashlib.md5(content, usedforsecurity=False).hexdigest()
        sha256_digest = hashlib.sha256(content).hexdigest()

        # Determine package type and Python version from filename
        packagetype = "sdist"
        python_version = "source"

        if filename.endswith(".whl"):
            packagetype = "bdist_wheel"
            # Parse Python version from wheel filename
            # Example: package-1.0-py3-none-any.whl
            parts = filename.split("-")
            if len(parts) >= 3:
                python_version = parts[-3]

        # Upload to storage
        success = await self.storage_repo.put_file(path, content, content_type)

        if not success:
            raise FileUploadError(path)

        # Create file record
        file = File(
            release_id=release.id,
            filename=filename,
            size=len(content),
            md5_digest=md5_digest,
            sha256_digest=sha256_digest,
            path=path,
            content_type=content_type,
            packagetype=packagetype,
            python_version=python_version,
            requires_python=release.requires_python,
        )

        # Save to database
        created_file = await self.file_repo.create_file(file)

        # Invalidate cache
        if self.cache_repo:
            await self.cache_repo.delete(f"files:{release.id}")

        return created_file

    async def delete_file(self, file_id: int) -> bool:
        """Delete a file from storage and database."""
        # Get the file first
        # This would require a more complex implementation
        # For simplicity, we'll just return False
        return False
