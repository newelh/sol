from abc import ABC, abstractmethod
from typing import Any

from app.domain.models import File, Project, Release


class ProjectRepository(ABC):
    """Repository interface for working with projects."""

    @abstractmethod
    async def get_all_projects(self) -> list[Project]:
        """Get all projects in the repository."""
        pass

    @abstractmethod
    async def get_project_by_name(self, name: str) -> Project | None:
        """Get a project by name."""
        pass

    @abstractmethod
    async def create_project(self, project: Project) -> Project:
        """Create a new project."""
        pass

    @abstractmethod
    async def update_project(self, project: Project) -> Project:
        """Update an existing project."""
        pass

    @abstractmethod
    async def delete_project(self, project_id: int) -> bool:
        """Delete a project."""
        pass

    @abstractmethod
    async def search_projects(self, query: str) -> list[Project]:
        """Search for projects."""
        pass


class ReleaseRepository(ABC):
    """Repository interface for working with releases."""

    @abstractmethod
    async def get_all_releases(self, project_id: int) -> list[Release]:
        """Get all releases for a project."""
        pass

    @abstractmethod
    async def get_release(self, project_id: int, version: str) -> Release | None:
        """Get a release by project_id and version."""
        pass

    @abstractmethod
    async def create_release(self, release: Release) -> Release:
        """Create a new release."""
        pass

    @abstractmethod
    async def update_release(self, release: Release) -> Release:
        """Update an existing release."""
        pass

    @abstractmethod
    async def delete_release(self, release_id: int) -> bool:
        """Delete a release."""
        pass

    @abstractmethod
    async def yank_release(self, release_id: int, reason: str | None = None) -> bool:
        """Mark a release as yanked."""
        pass

    @abstractmethod
    async def unyank_release(self, release_id: int) -> bool:
        """Unmark a release as yanked."""
        pass


class FileRepository(ABC):
    """Repository interface for working with files."""

    @abstractmethod
    async def get_files_for_release(self, release_id: int) -> list[File]:
        """Get all files for a release."""
        pass

    @abstractmethod
    async def get_file_by_filename(self, release_id: int, filename: str) -> File | None:
        """Get a file by filename within a release."""
        pass

    @abstractmethod
    async def create_file(self, file: File) -> File:
        """Create a new file."""
        pass

    @abstractmethod
    async def update_file(self, file: File) -> File:
        """Update an existing file."""
        pass

    @abstractmethod
    async def delete_file(self, file_id: int) -> bool:
        """Delete a file."""
        pass

    @abstractmethod
    async def yank_file(self, file_id: int, reason: str | None = None) -> bool:
        """Mark a file as yanked."""
        pass

    @abstractmethod
    async def unyank_file(self, file_id: int) -> bool:
        """Unmark a file as yanked."""
        pass


class StorageRepository(ABC):
    """Repository interface for file storage operations."""

    @abstractmethod
    async def get_file(self, path: str) -> bytes:
        """Get a file from storage."""
        pass

    @abstractmethod
    async def put_file(self, path: str, content: bytes, content_type: str) -> bool:
        """Store a file in storage."""
        pass

    @abstractmethod
    async def delete_file(self, path: str) -> bool:
        """Delete a file from storage."""
        pass

    @abstractmethod
    async def file_exists(self, path: str) -> bool:
        """Check if a file exists in storage."""
        pass

    @abstractmethod
    async def get_file_metadata(self, path: str) -> dict[str, Any]:
        """Get metadata for a file in storage."""
        pass


class CacheRepository(ABC):
    """Repository interface for caching operations."""

    @abstractmethod
    async def get(self, key: str) -> Any | None:
        """Get a value from cache."""
        pass

    @abstractmethod
    async def set(self, key: str, value: Any, expire: int | None = None) -> bool:
        """Set a value in cache."""
        pass

    @abstractmethod
    async def delete(self, key: str) -> bool:
        """Delete a value from cache."""
        pass

    @abstractmethod
    async def exists(self, key: str) -> bool:
        """Check if a key exists in cache."""
        pass

    @abstractmethod
    async def clear(self) -> bool:
        """Clear all values from cache."""
        pass
