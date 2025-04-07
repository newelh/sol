import json
import logging
import os
import shutil
import subprocess
import tempfile
from typing import Annotated, Any, NoReturn

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile

from app.api.dependencies.auth import verify_upload_permission
from app.api.dependencies.services import get_file_service, get_project_service
from app.api.routes.v1.legacy.handlers import (
    determine_package_type,
    get_file_hashes,
    is_valid_package_name,
    is_valid_version,
)
from app.domain.models import Project, Release
from app.services.file_service import FileService
from app.services.project_service import ProjectService, normalize_name

router = APIRouter()
logger = logging.getLogger(__name__)


class UVExecutableNotFoundError(FileNotFoundError):
    """Raised when the UV executable is not found in PATH."""

    def __init__(self) -> None:
        super().__init__("UV executable not found")


class CommandNotListError(ValueError):
    """Raised when a command is not provided as a list."""

    def __init__(self) -> None:
        super().__init__("Command must be a non-empty list")


class ExecutableNotFoundError(FileNotFoundError):
    """Raised when an executable is not found in PATH."""

    def __init__(self, command: str) -> None:
        super().__init__(f"Executable not found: {command}")


def run_subprocess_safely(
    command: list[str], **kwargs: Any
) -> subprocess.CompletedProcess:
    """Run a command with security precautions to avoid shell injection"""
    if not command or not isinstance(command, list):
        raise CommandNotListError()

    executable = shutil.which(command[0])
    if not executable:
        raise ExecutableNotFoundError(command[0])

    secure_command = [executable] + command[1:]
    kwargs.setdefault("shell", False)

    # ruff: noqa: S603
    return subprocess.run(secure_command, **kwargs)


def raise_validation_error(field: str, value: str) -> NoReturn:
    """Raise a standardized validation error."""
    raise HTTPException(status_code=400, detail=f"Invalid {field}: {value}")


def raise_checksum_mismatch(checksum_type: str) -> NoReturn:
    """Raise a standardized checksum mismatch error."""
    raise HTTPException(status_code=400, detail=f"{checksum_type} checksum mismatch")


@router.post("/")
async def legacy_upload(
    request: Request,
    name: Annotated[str, Form(...)],
    version: Annotated[str, Form(...)],
    content: Annotated[UploadFile, File(...)],
    project_service: Annotated[ProjectService, Depends(get_project_service)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    user: Annotated[dict, Depends(verify_upload_permission)],
    md5_digest: Annotated[str | None, Form()] = None,
    sha256_digest: Annotated[str | None, Form()] = None,
    requires_python: Annotated[str | None, Form()] = None,
    description: Annotated[str | None, Form()] = None,
    summary: Annotated[str | None, Form()] = None,
    license: Annotated[str | None, Form()] = None,
    author: Annotated[str | None, Form()] = None,
    author_email: Annotated[str | None, Form()] = None,
    maintainer: Annotated[str | None, Form()] = None,
    maintainer_email: Annotated[str | None, Form()] = None,
    home_page: Annotated[str | None, Form()] = None,
    keywords: Annotated[str | None, Form()] = None,
    classifiers: Annotated[list[str] | None, Form()] = None,
) -> dict:
    """
    Legacy package upload endpoint.

    This endpoint handles package uploads from traditional Python packaging tools like
    twine, setuptools, or poetry. It follows the PyPI upload API format.

    Args:
        name: Project name
        version: Release version
        content: Distribution file (wheel, sdist, etc.)
        md5_digest: MD5 hash of the file (optional)
        sha256_digest: SHA256 hash of the file (optional)
        requires_python: Python version requirement
        description: Long description
        summary: Short description
        license: License identifier
        author: Author name
        author_email: Author email
        maintainer: Maintainer name
        maintainer_email: Maintainer email
        home_page: Project homepage URL
        keywords: Comma-separated keywords
        classifiers: Trove classifiers

    Returns:
        JSON response indicating success or error

    """
    try:
        # Validate package name according to PEP 508
        if not is_valid_package_name(name):
            raise_validation_error("package name", name)

        # Validate version according to PEP 440
        if not is_valid_version(version):
            raise_validation_error("version", version)

        # Validate file name based on PEP 503/440 rules
        filename = (
            content.filename or f"{name}-{version}.tar.gz"
        )  # Provide a default filename
        if not _is_valid_package_filename(filename):
            raise_validation_error("package filename", filename)

        # Read the file
        file_contents = await content.read()

        # Calculate file hashes
        hashes = get_file_hashes(file_contents)

        # Verify file hashes if provided
        if md5_digest and hashes["md5"] != md5_digest:
            raise_checksum_mismatch("MD5")

        if sha256_digest and hashes["sha256"] != sha256_digest:
            raise_checksum_mismatch("SHA256")
        else:
            # Use calculated SHA256 if not provided
            sha256_digest = hashes["sha256"]

        # Get or create the project
        normalized_name = normalize_name(name)
        project = await project_service.get_project_by_name(name)

        if not project:
            # Create new project
            project = await project_service.create_project(
                Project(
                    name=name, normalized_name=normalized_name, description=description
                )
            )

        # Extract additional metadata from the file
        try:
            metadata = _extract_metadata(file_contents, filename)
        except Exception as e:
            logger.warning(f"Failed to extract metadata from {filename}: {e}")
            metadata = {}

        # Get or create the release
        releases = await project_service.get_project_releases(name)
        release = next((r for r in releases if r.version == version), None)

        if not release:
            # Create new release
            try:
                logger.info(f"Creating new release: {name} {version}")
                # Log the data we're sending
                release_data = Release(
                    version=version,
                    requires_python=requires_python,
                    summary=summary or metadata.get("summary"),
                    description=description or metadata.get("description"),
                    author=author or metadata.get("author"),
                    author_email=author_email or metadata.get("author_email"),
                    maintainer=maintainer or metadata.get("maintainer"),
                    maintainer_email=maintainer_email
                    or metadata.get("maintainer_email"),
                    license=license or metadata.get("license"),
                    keywords=keywords or metadata.get("keywords"),
                    classifiers=classifiers or metadata.get("classifiers", []),
                    home_page=home_page or metadata.get("home_page"),
                    requires_dist=metadata.get("requires_dist", []),
                    provides_dist=metadata.get("provides_dist", []),
                    obsoletes_dist=metadata.get("obsoletes_dist", []),
                    project_urls=metadata.get("project_urls", {}),
                )
                logger.info(f"Release data: {release_data}")

                release = await project_service.create_release(name, release_data)
                logger.info(f"Release created successfully with ID: {release.id}")
            except Exception:
                logger.exception("Error creating release")
                raise

        # Determine package type and Python version
        packagetype, python_version = determine_package_type(filename)

        # Determine content type based on filename
        content_type = _get_content_type(filename)

        # Upload the file
        try:
            logger.info(
                f"Uploading file: {filename} for {project.name} {release.version}"
            )
            file_metadata = {
                **metadata,
                "packagetype": packagetype,
                "python_version": python_version,
                "uploaded_by": user["username"],
            }
            logger.info(f"File metadata: {file_metadata}")

            # Use the validated filename for upload (will never be None at this point)
            file = await file_service.upload_file(
                project,
                release,
                filename,
                file_contents,
                content_type,
                metadata=file_metadata,
            )
            logger.info(f"File uploaded successfully with ID: {file.id}")
        except Exception as upload_err:
            logger.exception("Error uploading file")
            if not isinstance(upload_err, HTTPException):
                raise HTTPException(
                    status_code=500, detail=f"Upload failed: {upload_err!s}"
                ) from upload_err
            else:
                raise
    except HTTPException:
        # Re-raise HTTP exceptions
        raise
    except Exception as e:
        logger.exception("Upload failed")
        raise HTTPException(status_code=500, detail=f"Upload failed: {e!s}") from e
    else:
        return {
            "success": True,
            "file": {
                "name": file.filename,
                "size": file.size,
                "md5_digest": file.md5_digest,
                "sha256_digest": file.sha256_digest,
                "content_type": file.content_type,
                "url": f"/files/{file.path}",
            },
        }


def _is_valid_package_filename(filename: str) -> bool:
    """
    Validate package filename according to PEP specifications.

    Valid formats include:
    - package-1.0.tar.gz (sdist)
    - package-1.0-py3-none-any.whl (wheel)
    - package-1.0.zip (sdist)
    """
    # Check for common distribution extensions
    if not any(filename.endswith(ext) for ext in [".whl", ".tar.gz", ".zip", ".egg"]):
        return False

    # Basic format check
    parts = filename.split("-")
    if len(parts) < 2:
        return False

    # If this is a wheel, it needs at least 4 parts
    return not (filename.endswith(".whl") and len(parts) < 4)


def _get_content_type(filename: str) -> str:
    """Determine content type based on filename."""
    if filename.endswith(".whl"):
        return "application/octet-stream"
    elif filename.endswith(".tar.gz"):
        return "application/gzip"
    elif filename.endswith(".zip") or filename.endswith(".egg"):
        return "application/zip"
    else:
        return "application/octet-stream"


def _extract_metadata(file_contents: bytes, filename: str) -> dict:
    """
    Extract metadata from a distribution file.

    Attempted to use uv to extract metadata, but falls back to basic info
    if uv is not available or fails.
    """
    # Basic metadata we can extract from the filename
    metadata = {}

    # Extract package name and version from filename
    # Example: package-1.0-py3-none-any.whl
    try:
        parts = filename.split("-")
        if len(parts) >= 2:
            # Handle package names with hyphens
            if filename.endswith(".whl"):
                # For wheels, version is usually the second part but can vary
                # We'll use a simple heuristic: find the first part that looks like a version
                name_parts = []
                version = None
                for part in parts:
                    # Simple version detection: contains a digit and maybe a period
                    if any(c.isdigit() for c in part) and (
                        "." in part or any(c.isdigit() for c in part)
                    ):
                        version = part
                        break
                    name_parts.append(part)

                if version and name_parts:
                    metadata["name"] = "-".join(name_parts)
                    metadata["version"] = version
            else:
                # For sdists (tar.gz, zip), it's usually simpler
                metadata["name"] = parts[0]
                metadata["version"] = parts[1]
    except Exception as e:
        logger.warning(f"Failed to extract name/version from filename: {e!s}")

    # Now try to extract more detailed metadata if possible
    try:
        # Save file contents to a temporary file
        with tempfile.NamedTemporaryFile(
            delete=False, suffix=os.path.splitext(filename)[1]
        ) as temp_file:
            temp_file.write(file_contents)
            temp_path = temp_file.name

        try:
            # First check if uv is available
            try:
                # Use absolute path for better security
                uv_path = shutil.which("uv")
                if not uv_path:
                    logger.debug("UV executable not found in PATH")
                    uv_available = False
                else:
                    try:
                        result = run_subprocess_safely(
                            ["uv", "--version"],
                            capture_output=True,
                            text=True,
                            check=False,  # Don't raise an exception if it fails
                        )
                        uv_available = result.returncode == 0
                    except FileNotFoundError:
                        uv_available = False
            except FileNotFoundError:
                uv_available = False

            if uv_available:
                # Use uv inspect to extract metadata
                # Using full path for better security
                try:
                    result = run_subprocess_safely(
                        ["uv", "inspect", "metadata", temp_path],
                        capture_output=True,
                        text=True,
                        check=True,
                    )
                except FileNotFoundError as e:
                    logger.warning("UV executable not found in PATH")
                    raise UVExecutableNotFoundError() from e

                # Parse the JSON output
                uv_metadata = json.loads(result.stdout)

                # Format metadata to match our expected structure
                formatted_metadata = {
                    "name": uv_metadata.get("name"),
                    "version": uv_metadata.get("version"),
                    "summary": uv_metadata.get("summary"),
                    "description": uv_metadata.get("description"),
                    "description_content_type": uv_metadata.get(
                        "description_content_type"
                    ),
                    "author": uv_metadata.get("author"),
                    "author_email": uv_metadata.get("author_email"),
                    "maintainer": uv_metadata.get("maintainer"),
                    "maintainer_email": uv_metadata.get("maintainer_email"),
                    "license": uv_metadata.get("license"),
                    "keywords": uv_metadata.get("keywords"),
                    "classifiers": uv_metadata.get("classifiers", []),
                    "home_page": uv_metadata.get("home_page")
                    or uv_metadata.get("project_url", {}).get("Homepage"),
                    "requires_python": uv_metadata.get("requires_python"),
                    "requires_dist": uv_metadata.get("requires_dist", []),
                    "provides_dist": uv_metadata.get("provides_dist", []),
                    "obsoletes_dist": uv_metadata.get("obsoletes_dist", []),
                    "project_urls": uv_metadata.get("project_urls", {}),
                }

                # Update metadata with the more detailed info
                metadata.update(
                    {k: v for k, v in formatted_metadata.items() if v is not None}
                )
        finally:
            # Clean up temporary file
            os.unlink(temp_path)

    except subprocess.CalledProcessError as e:
        logger.warning(f"Failed to extract metadata with uv: {e.stderr}")
    except Exception as e:
        logger.warning(f"Failed to extract metadata: {e!s}")

    return metadata
