import logging
import re
from urllib.parse import urlparse

from app.api.routes.v1.simple.models import (
    PackageFile,
    ProjectDetail,
    ProjectList,
    ProjectReference,
)
from app.core.clients.postgres import PostgresClient
from app.core.clients.s3 import S3Client
from app.core.clients.valkey import ValkeyClient
from app.domain.models import File
from app.repos.postgres.file_repo import PostgresFileRepository
from app.repos.postgres.project_repo import PostgresProjectRepository
from app.repos.postgres.release_repo import PostgresReleaseRepository
from app.repos.valkey.cache_repo import ValkeyCacheRepository
from app.services.project_service import ProjectService

logger = logging.getLogger(__name__)

# Constants
CACHE_EXPIRY_SHORT = 60 * 5  # 5 minutes
CACHE_EXPIRY_LONG = 60 * 10  # 10 minutes


def normalize_name(name: str) -> str:
    """
    Normalize a package name according to PEP 503.

    This replaces runs of non-alphanumeric characters with a single '-'
    and lowercase the name.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


def _get_cache_repo(valkey: ValkeyClient | None) -> ValkeyCacheRepository | None:
    """Get a cache repository if valkey client is available."""
    if not valkey:
        return None
    return ValkeyCacheRepository(valkey)


def _create_project_service(postgres: PostgresClient) -> ProjectService:
    """Create and initialize a ProjectService with repositories."""
    project_repo = PostgresProjectRepository(postgres)
    release_repo = PostgresReleaseRepository(postgres)
    file_repo = PostgresFileRepository(postgres)

    return ProjectService(
        project_repo=project_repo,
        release_repo=release_repo,
        file_repo=file_repo,
        cache_repo=None,  # We handle caching explicitly in handlers
    )


async def get_all_projects(
    postgres: PostgresClient, valkey: ValkeyClient | None = None
) -> ProjectList:
    """Get all projects for the root `/simple/` endpoint."""
    cache_repo = _get_cache_repo(valkey)
    cache_key = "simple_all_projects"

    # Try to get from cache first
    if cache_repo:
        cached_data = await cache_repo.get(cache_key)
        if cached_data and isinstance(cached_data, list):
            return ProjectList(projects=[ProjectReference(name=p) for p in cached_data])

    # Initialize service
    project_service = _create_project_service(postgres)

    try:
        # Fetch all projects
        projects_db = await project_service.get_all_projects()
        project_refs = [ProjectReference(name=project.name) for project in projects_db]

        # Cache the result if we have projects and a cache
        if cache_repo and project_refs:
            await cache_repo.set(
                cache_key,
                [p.name for p in project_refs],
                expire=CACHE_EXPIRY_SHORT,
            )

        return ProjectList(projects=project_refs)
    except Exception:
        logger.exception("Error fetching projects from database")
        return ProjectList(projects=[])  # Empty list as fallback


async def get_project_detail(
    project_name: str,
    postgres: PostgresClient,
    s3: S3Client,
    valkey: ValkeyClient | None = None,
) -> ProjectDetail:
    """Get project details and files for the `/simple/{project_name}/` endpoint."""
    normalized_name = normalize_name(project_name)
    cache_repo = _get_cache_repo(valkey)
    cache_key = f"simple_project:{normalized_name}"

    # Initialize empty response for error cases
    empty_response = ProjectDetail(name=normalized_name, files=[], versions=[])

    # Try to get from cache first
    if cache_repo:
        cached_data = await cache_repo.get(cache_key)
        if cached_data and isinstance(cached_data, dict) and "files" in cached_data:
            return ProjectDetail(
                name=cached_data.get("name", normalized_name),
                files=[PackageFile(**f) for f in cached_data.get("files", [])],
                versions=cached_data.get("versions", []),
            )

    # Initialize service
    project_service = _create_project_service(postgres)

    try:
        # Get the project
        project = await project_service.get_project_by_name(project_name)
        if not project:
            return empty_response

        # Get all releases for the project
        releases = await project_service.get_project_releases(project_name)
        if not releases:
            return empty_response

        # Process releases and files
        all_files: list[PackageFile] = []
        versions: list[str] = []

        for release in releases:
            versions.append(release.version)
            release_files = await project_service.get_release_files(
                project_name, release.version
            )

            all_files.extend(
                _convert_file_to_package_file(file_obj) for file_obj in release_files
            )

        # Create the response object
        result = ProjectDetail(name=project.name, files=all_files, versions=versions)

        # Cache the result
        if cache_repo:
            await cache_repo.set(
                cache_key,
                {
                    "name": project.name,
                    "files": [f.dict() for f in all_files],
                    "versions": versions,
                },
                expire=CACHE_EXPIRY_SHORT,
            )

    except Exception:
        logger.exception("Error fetching project details from database")
        return empty_response
    else:
        return result


def _convert_file_to_package_file(file_obj: File) -> PackageFile:
    """Convert a domain File object to a PackageFile response model."""
    package_file = PackageFile(
        filename=file_obj.filename,
        url=f"/files/{file_obj.path}",
        hashes=file_obj.hashes,
        requires_python=file_obj.requires_python,
        size=file_obj.size,
    )

    # Add yanked info if applicable
    if file_obj.is_yanked:
        package_file.yanked = file_obj.yank_reason or True

    # Add metadata SHA if available
    if file_obj.has_metadata and file_obj.metadata_sha256:
        package_file.core_metadata = {"sha256": file_obj.metadata_sha256}

    # Add GPG signature info if available
    if file_obj.has_signature:
        package_file.gpg_sig = True

    return package_file


async def check_project_exists(
    project_name: str, postgres: PostgresClient, valkey: ValkeyClient | None = None
) -> bool:
    """Verify if a project exists before fetching its details."""
    normalized_name = normalize_name(project_name)
    cache_repo = _get_cache_repo(valkey)
    cache_key = f"project_exists:{normalized_name}"

    # Try cache first
    if cache_repo:
        cached = await cache_repo.get(cache_key)
        if cached is not None:
            return bool(cached)

    # Check the database
    project_repo = PostgresProjectRepository(postgres)
    project = await project_repo.get_project_by_name(project_name)
    result = project is not None

    # Cache the result
    if cache_repo:
        await cache_repo.set(cache_key, result, expire=CACHE_EXPIRY_LONG)

    return result


def validate_provenance_url(url: str) -> bool:
    """
    Validate provenance URL per PEP 740 requirements.

    Ensures URL is fully qualified and uses HTTPS (except localhost).
    """
    if not url:
        return False

    # Check if the URL is fully qualified
    if not url.startswith(("https://", "http://")):
        logger.warning(f"Rejecting provenance URL: not fully qualified: {url}")
        return False

    # Parse the URL
    parsed_url = urlparse(url)

    # Check for secure protocol
    if parsed_url.scheme != "https" and parsed_url.netloc != "localhost":
        logger.warning(f"Rejecting provenance URL: not using HTTPS: {url}")
        return False

    return True


def validate_requires_python(requires_python: str) -> bool:
    """
    Validate requires-python string format per PEP 440.

    Handles version specifiers, ranges, exclusions, and wildcards.
    """
    if not requires_python:
        return True  # Empty is valid (means no constraints)

    # Special case for '*' which means any version
    if requires_python.strip() == "*":
        return True

    # Pattern for valid version specifiers - handles common cases
    # Covers most of the common version specifier formats
    PATTERN = r"^\s*(?:(?:<=|>=|<|>|!=|==|~=)\s*[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?(?:\.dev[0-9]+)?(?:\s*,\s*)?)+\s*$"

    # Special case: Just a version without operator means ">="
    # For example, "3.6" is equivalent to ">=3.6"
    VERSION_ONLY_PATTERN = r"^\s*[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?(?:\.dev[0-9]+)?\s*$"

    # Special case for exclusion markers - more complex syntax that's valid but not captured by the simple regex
    # These are patterns like "!=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*"
    EXCLUSION_PATTERN = r"^\s*(?:!=\s*[0-9]+(?:\.[0-9]+)*\.\*\s*,?\s*)+$"

    if (
        re.match(PATTERN, requires_python)
        or re.match(VERSION_ONLY_PATTERN, requires_python)
        or re.match(EXCLUSION_PATTERN, requires_python)
    ):
        return True

    logger.warning(f"Invalid requires-python format: {requires_python}")
    return False


def escape_html(text: str) -> str:
    """Escape HTML special characters for safe output in templates."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
