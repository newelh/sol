import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, JSONResponse

from app.api.dependencies.services import get_project_service
from app.api.routes.v1.simple.handlers import (
    escape_html,
    validate_provenance_url,
    validate_requires_python,
)
from app.domain.models import File, Project
from app.services.project_service import ProjectService

logger = logging.getLogger(__name__)


router = APIRouter()


async def negotiate_content_type(
    request: Request,
    accept: str = Header(None),
    format: str = Query(None),
) -> str:
    """
    Negotiate content type based on Accept header and optional format parameter.

    Supports content negotiation for the Simple API as described in PEP 691.
    This implementation properly handles quality values in Accept headers.
    """
    # If format is explicitly specified via parameter, use that (takes precedence)
    if format:
        if format.lower() == "json":
            return "application/vnd.pypi.simple.v1+json"
        elif format.lower() == "html":
            return "application/vnd.pypi.simple.v1+html"

    # If no Accept header, default to HTML for backward compatibility
    if not accept:
        return "text/html"

    # Parse the Accept header with proper quality value handling
    # Format is typically: "type/subtype;q=value,type/subtype;q=value"
    media_types = []

    for media_range in accept.split(","):
        media_range = media_range.strip()
        parts = media_range.split(";")
        mime_type = parts[0].strip()

        # Default quality is 1.0
        quality = 1.0

        # Extract quality value if present
        for param in parts[1:]:
            param = param.strip()
            if param.startswith("q="):
                try:
                    quality = float(param[2:])
                except ValueError:
                    quality = 0.0

        # Only add if quality > 0
        if quality > 0:
            media_types.append((mime_type, quality))

    # Sort by quality (highest first)
    media_types.sort(key=lambda x: x[1], reverse=True)

    # Check for our specific MIME types in order of preference
    for mime_type, _ in media_types:
        if mime_type == "application/vnd.pypi.simple.v1+json":
            return "application/vnd.pypi.simple.v1+json"
        elif mime_type in ["application/vnd.pypi.simple.v1+html", "text/html"]:
            return "application/vnd.pypi.simple.v1+html"

    # If we got here, no acceptable match was found
    # Default to HTML for backward compatibility
    return "text/html"


def render_project_list_html(projects: list[Project]) -> str:
    """Render a project list as HTML."""
    html = """<!DOCTYPE html>
<html>
  <head>
    <meta name="pypi:repository-version" content="1.3">
  </head>
  <body>
"""

    for project in projects:
        html += f'    <a href="/simple/{project.normalized_name}/">{project.name}</a>\n'

    html += """  </body>
</html>
"""
    return html


def render_project_detail_html(
    project: Project, files: list[File], versions: list[str]
) -> str:
    """Render project details as HTML."""
    html = f"""<!DOCTYPE html>
<html>
  <head>
    <meta name="pypi:repository-version" content="1.3">
  </head>
  <body>
    <h1>{project.name}</h1>
"""

    for file in files:
        html += f'    <a href="/files/{file.path}'

        # Add hash fragment if available
        if file.sha256_digest:
            html += f"#sha256={file.sha256_digest}"

        html += '"'

        # Add data attributes
        if file.requires_python:
            # Validate requires-python format
            if validate_requires_python(file.requires_python):
                # Use comprehensive HTML escaping
                requires_python_encoded = escape_html(file.requires_python)
                html += f' data-requires-python="{requires_python_encoded}"'
            else:
                # Still include but log a warning
                requires_python_encoded = escape_html(file.requires_python)
                html += f' data-requires-python="{requires_python_encoded}"'
                logger.warning(
                    f"Invalid requires-python format in {file.filename}: {file.requires_python}"
                )

        # Handle yanked status consistently per PEP 592
        if file.is_yanked:
            if file.yank_reason:
                # Escape any HTML in the yank reason
                yank_reason_encoded = escape_html(file.yank_reason)
                html += f' data-yanked="{yank_reason_encoded}"'
            else:
                html += ' data-yanked="true"'  # Use explicit true value for consistency

        if file.has_metadata:
            if file.metadata_sha256:
                html += f' data-core-metadata="sha256={file.metadata_sha256}"'
                html += f' data-dist-info-metadata="sha256={file.metadata_sha256}"'
            else:
                html += ' data-core-metadata="true"'
                html += ' data-dist-info-metadata="true"'

        if file.has_signature:
            html += ' data-gpg-sig="true"'

        # Add provenance data if it exists and is valid
        # Per PEP 740, validate the provenance URL
        if hasattr(file, "provenance") and file.provenance:
            if validate_provenance_url(file.provenance):
                html += f' data-provenance="{file.provenance}"'
            else:
                logger.warning(f"Invalid provenance URL skipped: {file.provenance}")

        html += f">{file.filename}</a>\n"

    html += """  </body>
</html>
"""
    return html


@router.get("/", response_model=None)
async def simple_index(
    request: Request,
    project_service: Annotated[ProjectService, Depends(get_project_service)],
    content_type: Annotated[str, Depends(negotiate_content_type)],
) -> Response:
    """
    Project listing endpoint (PEP 503 / PEP 691).

    This endpoint returns a list of all projects in the repository.

    - PEP 503: Returns HTML with an anchor element for each project
    - PEP 691: When requested with proper Accept header, returns JSON representation

    The response format is determined by content negotiation based on the Accept header.

    # Implements PEPs 503, 691, 658, and 592 for Simple API
    """
    # Get all projects from the service
    projects = await project_service.get_all_projects()

    # Return response in the negotiated format
    if content_type in ["text/html", "application/vnd.pypi.simple.v1+html"]:
        html_content = render_project_list_html(projects)
        return HTMLResponse(content=html_content, media_type=content_type)
    elif content_type == "application/vnd.pypi.simple.v1+json":
        # Build the JSON response according to PEP 691
        # Get versions for all projects (for tracks metadata per PEP 708)
        versions = {}
        for p in projects:
            project_releases = await project_service.get_project_releases(p.name)
            versions[p.normalized_name] = [r.version for r in project_releases]

        json_response = {
            "meta": {"api-version": "1.3"},
            "projects": [{"name": p.name} for p in projects],
            "versions": versions,
            "tracks": {
                "default": {"stable": True},
                "stable": {"stable": True},
                "prerelease": {"dev": True, "a": True, "b": True, "rc": True},
            },
        }
        return JSONResponse(content=json_response, media_type=content_type)

    # This should not happen due to content negotiation
    raise HTTPException(status_code=406, detail="Not Acceptable")


@router.get("/{project_name}/", response_model=None)
async def project_detail(
    project_name: str,
    request: Request,
    project_service: Annotated[ProjectService, Depends(get_project_service)],
    content_type: Annotated[str, Depends(negotiate_content_type)],
) -> Response:
    """
    Project detail endpoint (PEP 503 / PEP 691).

    This endpoint returns details about a specific project, including:
    - Links to all available files for the project
    - Hashes for each file (recommended: sha256)
    - Python version requirements (PEP 345, exposed via data-requires-python)
    - Whether a file has been yanked (PEP 592, data-yanked attribute)
    - GPG signature information (data-gpg-sig attribute)
    - Metadata availability (PEP 658/714, data-dist-info-metadata/data-core-metadata attribute)
    - Provenance information (PEP 740, data-provenance attribute)

    The project_name is normalized according to PEP 503 rules.
    The response format is determined by content negotiation based on the Accept header.
    """
    # Get the project from the service
    project = await project_service.get_project_by_name(project_name)
    if not project:
        raise HTTPException(status_code=404, detail=f"Project {project_name} not found")

    # Get all releases for the project
    releases = await project_service.get_project_releases(project_name)

    # Collect all files from all releases
    all_files = []
    versions = []
    for release in releases:
        versions.append(release.version)
        release_files = await project_service.get_release_files(
            project_name, release.version
        )
        all_files.extend(release_files)

    # Sort files by filename
    all_files.sort(key=lambda f: f.filename)

    # Return response in the negotiated format
    if content_type in ["text/html", "application/vnd.pypi.simple.v1+html"]:
        html_content = render_project_detail_html(project, all_files, versions)
        return HTMLResponse(content=html_content, media_type=content_type)
    elif content_type == "application/vnd.pypi.simple.v1+json":
        # Build the JSON response according to PEP 691
        file_list = []
        for file in all_files:
            # Ensure file size is always included (mandatory per API v1.1)
            if not hasattr(file, "size") or file.size is None:
                logger.error(f"Missing required file size for {file.filename}")
                # Default to 0 for size if missing, though this shouldn't happen
                # Better to send some response than to fail completely
                file_size = 0
            else:
                file_size = file.size

            # Initialize with empty hashes dict
            hashes = {}
            if file.sha256_digest:
                hashes["sha256"] = file.sha256_digest.lower()
            if file.md5_digest:
                hashes["md5"] = file.md5_digest.lower()
            if file.blake2_256_digest:
                hashes["blake2b_256"] = file.blake2_256_digest.lower()

            file_info = {
                "filename": file.filename,
                "url": f"/files/{file.path}",
                "hashes": hashes,
                "size": file_size,
            }

            # Add requires-python if present (with validation)
            if file.requires_python:
                if validate_requires_python(file.requires_python):
                    file_info["requires-python"] = file.requires_python
                else:
                    # Still include it but log a warning
                    file_info["requires-python"] = file.requires_python
                    logger.warning(
                        f"Invalid requires-python format in JSON response for {file.filename}: {file.requires_python}"
                    )

            # Add yanked info if present (consistent with PEP 592)
            if file.is_yanked:
                # For JSON response, use true or the reason string
                file_info["yanked"] = file.yank_reason if file.yank_reason else True

            # Add metadata info if present
            if file.has_metadata:
                if file.metadata_sha256:
                    file_info["core-metadata"] = {"sha256": file.metadata_sha256}
                    file_info["dist-info-metadata"] = {"sha256": file.metadata_sha256}
                else:
                    file_info["core-metadata"] = True
                    file_info["dist-info-metadata"] = True

            # Add signature info if present
            if file.has_signature:
                file_info["gpg-sig"] = True

            # Add upload time if present
            if hasattr(file, "upload_time") and file.upload_time is not None:
                file_info["upload-time"] = file.upload_time.isoformat()

            # Add provenance data if it exists and is valid (PEP 740)
            if hasattr(file, "provenance") and file.provenance:
                if validate_provenance_url(file.provenance):
                    file_info["provenance"] = file.provenance
                else:
                    logger.warning(
                        f"Invalid provenance URL skipped for JSON response: {file.provenance}"
                    )

            file_list.append(file_info)

        json_response = {
            "meta": {"api-version": "1.3"},
            "name": project.normalized_name,
            "files": file_list,
            "versions": versions,
            "tracks": {
                "default": {"stable": True},
                "stable": {"stable": True},
                "prerelease": {"dev": True, "a": True, "b": True, "rc": True},
            },
        }

        return JSONResponse(content=json_response, media_type=content_type)

    # This should not happen due to content negotiation
    raise HTTPException(status_code=406, detail="Not Acceptable")
