from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from app.api.dependencies.services import get_project_service
from app.domain.models import File, Project, Release
from app.services.project_service import ProjectService

router = APIRouter()


@router.get("/{project_name}/json")
async def json_project_metadata(
    project_name: str,
    request: Request,
    project_service: Annotated[ProjectService, Depends(get_project_service)],
) -> dict[str, Any]:
    """
    Project JSON metadata endpoint.

    While not specified in a PEP, this endpoint is widely used by tools
    to get comprehensive metadata about a project. It's analogous to
    PyPI's /pypi/{project}/json endpoint.

    This provides more detailed information than the simple API, including:
    - All available releases and their files
    - Full package metadata (author, description, classifiers, etc.)
    - URLs for project homepage, documentation, etc.
    """
    # Get the project from the service
    project = await project_service.get_project_by_name(project_name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_name} not found")

    # Get all releases for the project
    releases = await project_service.get_project_releases(project_name)

    # Build the response structure
    response = {
        "info": await _build_project_info(project, releases),
        "last_serial": 1,  # Simple serial number, would be more meaningful in a real implementation
        "releases": await _build_releases_dict(
            project, releases, project_service, request
        ),
        "urls": await _build_latest_urls(project, releases, project_service, request),
    }

    return response


async def _build_project_info(
    project: Project, releases: list[Release]
) -> dict[str, Any]:
    """
    Build the 'info' section of the PyPI JSON response.

    Uses the project data and the latest release for detailed metadata.
    """
    # Use the latest release for detailed metadata
    latest_release = None
    if releases:
        # Simple sorting by upload time; in a real implementation, you'd use proper version comparison
        latest_release = sorted(releases, key=lambda r: r.uploaded_at, reverse=True)[0]

    info = {
        "name": project.name,
        "version": latest_release.version if latest_release else "",
        "summary": latest_release.summary if latest_release else None,
        "description": latest_release.description
        if latest_release
        else project.description,
        "description_content_type": None,  # Not stored in our model yet
        "author": latest_release.author if latest_release else None,
        "author_email": latest_release.author_email if latest_release else None,
        "maintainer": latest_release.maintainer if latest_release else None,
        "maintainer_email": latest_release.maintainer_email if latest_release else None,
        "license": latest_release.license if latest_release else None,
        "keywords": latest_release.keywords if latest_release else None,
        "classifiers": latest_release.classifiers if latest_release else [],
        "platform": latest_release.platform if latest_release else None,
        "home_page": latest_release.home_page if latest_release else None,
        "download_url": latest_release.download_url if latest_release else None,
        "requires_python": latest_release.requires_python if latest_release else None,
        "requires_dist": latest_release.requires_dist if latest_release else [],
        "project_urls": latest_release.project_urls if latest_release else {},
        "yanked": latest_release.yanked if latest_release else False,
        "yanked_reason": latest_release.yank_reason
        if latest_release and latest_release.yanked
        else None,
    }

    # Filter out None values
    return {k: v for k, v in info.items() if v is not None}


async def _build_releases_dict(
    project: Project,
    releases: list[Release],
    project_service: ProjectService,
    request: Request | None = None,
) -> dict[str, list[dict[str, Any]]]:
    """
    Build the 'releases' section of the PyPI JSON response.

    A dictionary mapping version strings to lists of file information.
    """
    result = {}

    for release in releases:
        # Get files for this release
        files = await project_service.get_release_files(project.name, release.version)

        # Build file info for each file
        file_list = []
        for file in files:
            file_info = _build_file_info(file, request)
            file_list.append(file_info)

        # Add to the result dictionary
        result[release.version] = file_list

    return result


async def _build_latest_urls(
    project: Project,
    releases: list[Release],
    project_service: ProjectService,
    request: Request | None = None,
) -> list[dict[str, Any]]:
    """
    Build the 'urls' section of the PyPI JSON response.

    A list of file information for the latest version.
    """
    if not releases:
        return []

    # Get the latest release
    latest_release = sorted(releases, key=lambda r: r.uploaded_at, reverse=True)[0]

    # Get files for the latest release
    files = await project_service.get_release_files(
        project.name, latest_release.version
    )

    # Build file info for each file
    file_list = []
    for file in files:
        file_info = _build_file_info(file, request)
        file_list.append(file_info)

    return file_list


def _build_file_info(file: File, request: Request | None = None) -> dict[str, Any]:
    """Build a dictionary of file information for the PyPI JSON response."""
    # Construct the base URL using the request object if available
    base_url = ""
    if request:
        base_url = str(request.base_url).rstrip("/")

    info = {
        "filename": file.filename,
        "url": f"{base_url}/files/{file.path}",
        "size": file.size,
        "digests": {},
        "python_version": file.python_version,
        "packagetype": file.packagetype,
        "has_sig": file.has_signature,
        "upload_time": file.upload_time.strftime("%Y-%m-%d %H:%M:%S")
        if hasattr(file.upload_time, "strftime")
        else None,
        "upload_time_iso_8601": file.upload_time.isoformat()
        if hasattr(file.upload_time, "isoformat")
        else None,
        "requires_python": file.requires_python,
        "yanked": file.is_yanked,
        "yanked_reason": file.yank_reason if file.is_yanked else None,
    }

    # Add digests
    digests: dict[str, str] = {}  # Create a new dict
    if file.md5_digest:
        digests["md5"] = file.md5_digest
    if file.sha256_digest:
        digests["sha256"] = file.sha256_digest
    if file.blake2_256_digest:
        digests["blake2_256"] = file.blake2_256_digest
    # Now replace the entire digests dict
    info["digests"] = digests

    # Filter out None values
    return {k: v for k, v in info.items() if v is not None}
