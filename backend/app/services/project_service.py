import logging
import re

from app.domain.models import File, Project, Release
from app.repos.interfaces import (
    CacheRepository,
    FileRepository,
    ProjectRepository,
    ReleaseRepository,
)

logger = logging.getLogger(__name__)


class ProjectNotFoundError(ValueError):
    """Raised when a project is not found."""

    def __init__(self, project_name: str) -> None:
        super().__init__(f"Project not found: {project_name}")


def normalize_name(name: str) -> str:
    """
    Normalize a package name according to PEP 503.

    PEP 503 (Simple Repository API) requires package names to be normalized
    by replacing runs of non-alphanumeric characters with a single hyphen
    and lowercasing the result. This ensures consistent package name lookup
    regardless of the original name casing or punctuation.

    Examples:
    - Flask -> flask
    - django-rest-framework -> django-rest-framework
    - sqlalchemy_utils -> sqlalchemy-utils
    - NUMPY -> numpy
    - Zope.Interface -> zope-interface

    This exact implementation is critical for compatibility with pip and other
    tools that follow the same normalization rules when looking up packages.
    """
    return re.sub(r"[-_.]+", "-", name.lower())


class ProjectService:
    """Service for working with projects."""

    def __init__(
        self,
        project_repo: ProjectRepository,
        release_repo: ReleaseRepository,
        file_repo: FileRepository,
        cache_repo: CacheRepository | None = None,
    ):
        self.project_repo = project_repo
        self.release_repo = release_repo
        self.file_repo = file_repo
        self.cache_repo = cache_repo

    async def get_all_projects(self) -> list[Project]:
        """Get all projects in the repository."""
        # Try to get from cache first
        if self.cache_repo:
            cached = await self.cache_repo.get("all_projects")
            if cached:
                return [Project.parse_obj(p) for p in cached]

        # Fetch from database
        projects = await self.project_repo.get_all_projects()

        # Cache the result
        if self.cache_repo:
            await self.cache_repo.set(
                "all_projects",
                [p.dict() for p in projects],
                expire=60 * 5,  # Cache for 5 minutes
            )

        return projects

    async def get_project_by_name(self, name: str) -> Project | None:
        """Get a project by name."""
        # Normalize the name for lookup
        normalized_name = normalize_name(name)

        # Try to get from cache first
        if self.cache_repo:
            cached = await self.cache_repo.get(f"project:{normalized_name}")
            if cached:
                return Project.parse_obj(cached)

        # Fetch from database
        project = await self.project_repo.get_project_by_name(name)

        # Cache the result if found
        if project and self.cache_repo:
            await self.cache_repo.set(
                f"project:{normalized_name}",
                project.dict(),
                expire=60 * 15,  # Cache for 15 minutes
            )

        return project

    async def create_project(self, project: Project) -> Project:
        """Create a new project."""
        # Ensure the normalized name is set
        if not project.normalized_name:
            project.normalized_name = normalize_name(project.name)

        # Create the project in the database
        result = await self.project_repo.create_project(project)

        # Invalidate cache
        if self.cache_repo:
            await self.cache_repo.delete("all_projects")

        return result

    async def update_project(self, project: Project) -> Project:
        """Update an existing project."""
        # Update the project in the database
        result = await self.project_repo.update_project(project)

        # Invalidate cache
        if self.cache_repo:
            await self.cache_repo.delete("all_projects")
            await self.cache_repo.delete(f"project:{project.normalized_name}")

        return result

    async def delete_project(self, project_id: int) -> bool:
        """Delete a project."""
        # Fetch the project first to get the normalized name for cache invalidation
        projects = await self.project_repo.get_all_projects()
        project = next((p for p in projects if p.id == project_id), None)

        if not project:
            return False

        # Delete the project from the database
        result = await self.project_repo.delete_project(project_id)

        # Invalidate cache
        if result and self.cache_repo:
            await self.cache_repo.delete("all_projects")
            await self.cache_repo.delete(f"project:{project.normalized_name}")

        return result

    async def get_project_releases(self, project_name: str) -> list[Release]:
        """Get all releases for a project."""
        # Get the project first
        project = await self.get_project_by_name(project_name)
        if not project or not project.id:
            return []

        # Try to get from cache first
        if self.cache_repo:
            cached = await self.cache_repo.get(f"releases:{project.id}")
            if cached:
                return [Release.parse_obj(r) for r in cached]

        # Fetch from database
        releases = await self.release_repo.get_all_releases(project.id)

        # Cache the result
        if releases and self.cache_repo:
            await self.cache_repo.set(
                f"releases:{project.id}",
                [r.dict() for r in releases],
                expire=60 * 10,  # Cache for 10 minutes
            )

        return releases

    async def get_release_files(self, project_name: str, version: str) -> list[File]:
        """Get all files for a specific release."""
        # Get the project first
        project = await self.get_project_by_name(project_name)
        if not project or not project.id:
            return []

        # Get the release
        release = await self.release_repo.get_release(project.id, version)
        if not release or not release.id:
            return []

        # Try to get from cache first
        if self.cache_repo:
            cached = await self.cache_repo.get(f"files:{release.id}")
            if cached:
                return [File.parse_obj(f) for f in cached]

        # Fetch from database
        files = await self.file_repo.get_files_for_release(release.id)

        # Cache the result
        if files and self.cache_repo:
            await self.cache_repo.set(
                f"files:{release.id}",
                [f.dict() for f in files],
                expire=60 * 10,  # Cache for 10 minutes
            )

        return files

    async def search_projects(self, query: str) -> list[Project]:
        """Search for projects."""
        # This is a potentially expensive operation, so don't cache results
        return await self.project_repo.search_projects(query)

    async def create_release(self, project_name: str, release: Release) -> Release:
        """Create a new release for a project."""
        # Get the project first
        project = await self.get_project_by_name(project_name)
        if not project or not project.id:
            raise ProjectNotFoundError(project_name)

        # Set the project_id on the release
        release.project_id = project.id

        # Create the release
        result = await self.release_repo.create_release(release)

        # Invalidate cache
        if self.cache_repo:
            await self.cache_repo.delete(f"releases:{project.id}")

        return result
