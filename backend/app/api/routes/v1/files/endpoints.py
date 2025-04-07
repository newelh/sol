from typing import Annotated, NoReturn

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.api.dependencies.auth import verify_download_permission
from app.api.dependencies.services import get_file_service, get_project_service
from app.domain.models import File
from app.services.file_service import FileService
from app.services.project_service import ProjectService


def raise_not_found(item_type: str, item_name: str) -> NoReturn:
    raise HTTPException(status_code=404, detail=f"{item_type} not found: {item_name}")


def raise_metadata_not_available(path: str, reason: str) -> NoReturn:
    raise HTTPException(
        status_code=404,
        detail=f"Metadata not available for {path}: {reason}",
    )


router = APIRouter()


@router.get("/{file_path:path}")
async def serve_file(
    file_path: str,
    request: Request,
    file_service: Annotated[FileService, Depends(get_file_service)],
    user: Annotated[dict, Depends(verify_download_permission)],
) -> Response:
    """
    File download endpoint.

    Serves the actual package distribution files (wheels, tarballs, etc.).

    This should check authentication if access control is implemented.
    In a production system, these files would typically be served from
    a storage service (S3, GCS, etc.) or through a CDN.
    """
    try:
        # Check if this is a metadata or signature request
        if file_path.endswith(".metadata"):
            # Remove .metadata suffix for processing
            base_file_path = file_path[:-9]

            # First, check if the base file exists
            try:
                # Check if the base file exists and has metadata
                base_file_info = await get_file_info(
                    base_file_path,
                    request,
                    Depends(get_project_service),
                    file_service,
                    user,
                )

                # Check if file has metadata
                has_metadata = False
                if isinstance(base_file_info, dict):
                    has_metadata = base_file_info.get("has_metadata", False)
                else:
                    has_metadata = getattr(base_file_info, "has_metadata", False)

                if not has_metadata:
                    raise_metadata_not_available(
                        base_file_path, "File exists but has no metadata"
                    )
            except HTTPException as e:
                if e.status_code == 404 and "not found" in str(e.detail):
                    # Base file doesn't exist
                    raise HTTPException(
                        status_code=404,
                        detail=f"Cannot serve metadata for {base_file_path}: Base file not found",
                    ) from e
                raise

            # Try to get the actual metadata file
            try:
                content, content_type, headers = await file_service.get_file(
                    base_file_path + ".metadata"
                )
                return Response(
                    content=content, media_type=content_type, headers=headers
                )
            except FileNotFoundError as e:
                # If metadata was claimed but file is missing, this is an inconsistency
                metadata_sha256 = None
                if isinstance(base_file_info, dict):
                    metadata_sha256 = base_file_info.get("metadata_sha256")
                else:
                    metadata_sha256 = getattr(base_file_info, "metadata_sha256", None)

                if metadata_sha256:
                    # If metadata hash was advertised but file is missing, return a more detailed error
                    raise HTTPException(
                        status_code=500,
                        detail=f"Metadata inconsistency: File claims metadata (sha256={metadata_sha256}) but metadata file is missing",
                    ) from e
                else:
                    # Generic metadata not found error
                    raise HTTPException(
                        status_code=404, detail="Metadata file not found"
                    ) from e

        elif file_path.endswith(".asc"):
            # GPG signature file
            try:
                content, content_type, headers = await file_service.get_file(file_path)
                return Response(
                    content=content, media_type=content_type, headers=headers
                )
            except FileNotFoundError as e:
                raise HTTPException(
                    status_code=404, detail=f"Signature file not found: {file_path}"
                ) from e

        # Regular file download
        content, content_type, headers = await file_service.get_file(file_path)
        return Response(content=content, media_type=content_type, headers=headers)
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to serve file: {e!s}"
        ) from e


@router.get("/{file_path:path}/info")
async def get_file_info(
    file_path: str,
    request: Request,
    project_service: Annotated[ProjectService, Depends(get_project_service)],
    file_service: Annotated[FileService, Depends(get_file_service)],
    user: Annotated[dict, Depends(verify_download_permission)],
) -> File | dict:
    """
    Get metadata about a file.

    This endpoint provides information about a file without downloading it.

    Returns:
        File metadata

    """
    try:
        # Extract project name and version from file path
        # This is a simplified approach; in a real implementation, you'd have a more robust way
        # to map file paths to database records
        parts = file_path.split("/")
        if len(parts) >= 2:
            project_name = parts[0]
            # Find the project and release
            project = await project_service.get_project_by_name(project_name)
            if not project:
                raise_not_found("Project", project_name)

            # Get all releases and files
            releases = await project_service.get_project_releases(project_name)
            for release in releases:
                files = await project_service.get_release_files(
                    project_name, release.version
                )
                # Find the file with matching path
                for file in files:
                    if file.path == file_path:
                        # Return file metadata
                        return {
                            "filename": file.filename,
                            "project": project.name,
                            "version": release.version,
                            "content_type": file.content_type,
                            "size": file.size,
                            "sha256": file.sha256_digest,
                            "upload_time": file.upload_time.isoformat()
                            if hasattr(file, "upload_time")
                            and file.upload_time is not None
                            else None,
                            "uploaded_by": file.uploaded_by,
                            "requires_python": file.requires_python,
                            "is_yanked": file.is_yanked,
                            "yank_reason": file.yank_reason,
                            "has_signature": file.has_signature,
                            "has_metadata": file.has_metadata,
                            "metadata_sha256": file.metadata_sha256,
                        }

        # File not found
        raise_not_found("File", file_path)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to get file info: {e!s}"
        ) from e
