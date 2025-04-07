import hashlib
from datetime import datetime

from app.api.routes.v1.files.models import FileMetadata
from app.core.clients.postgres import PostgresClient
from app.core.clients.s3 import S3Client
from app.core.clients.valkey import ValkeyClient


async def download_file(
    file_path: str,
    postgres: PostgresClient,
    s3: S3Client,
    valkey: ValkeyClient | None = None,
) -> tuple[bytes, str, dict[str, str]]:
    """Returns (file_content, content_type, headers) from storage"""
    # Create S3 storage repository
    from app.repos.s3.storage_repo import S3StorageRepository

    storage_repo = S3StorageRepository(s3)

    # Create cache repo if valkey is available
    cache_repo = None
    if valkey:
        from app.repos.valkey.cache_repo import ValkeyCacheRepository

        cache_repo = ValkeyCacheRepository(valkey)

    # Check if file exists
    if not await storage_repo.file_exists(file_path):
        # Use a standard error message that will be handled by error middleware
        from fastapi import HTTPException, status

        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="File not found"
        )

    # Parse file path to extract project, version, and filename
    path_parts = file_path.split("/")
    if len(path_parts) >= 3:
        project_name = path_parts[-3]
        version = path_parts[-2]
        filename = path_parts[-1]
    else:
        filename = path_parts[-1]
        project_name = None
        version = None

    # Track download statistics (in the background to not slow down downloads)
    if project_name and version:
        download_key = f"downloads:{project_name}:{version}:{filename}"
        daily_key = f"downloads:daily:{datetime.now().strftime('%Y-%m-%d')}"

        # Try to increment download counters in cache
        if (
            cache_repo
            and hasattr(cache_repo, "valkey")
            and cache_repo.valkey
            and cache_repo.valkey._client
        ):
            try:
                client = cache_repo.valkey._client
                # Increment total download count for this file
                await client.hincrby(download_key, "total", 1)  # type: ignore
                # Increment daily download counter
                await client.hincrby(daily_key, file_path, 1)  # type: ignore
                # Set daily counter to expire after 90 days for data retention
                await client.expire(daily_key, 60 * 60 * 24 * 90)  # type: ignore

                # If download count hits threshold, persist to database
                download_count = await client.hget(download_key, "total")  # type: ignore
                if (
                    download_count and int(download_count) % 10 == 0
                ):  # Every 10 downloads
                    # Record in database for persistence (async fire-and-forget)
                    from app.repos.postgres.file_repo import PostgresFileRepository
                    from app.repos.postgres.project_repo import (
                        PostgresProjectRepository,
                    )
                    from app.repos.postgres.release_repo import (
                        PostgresReleaseRepository,
                    )

                    # This is a background task that shouldn't block download
                    try:
                        file_repo = PostgresFileRepository(postgres)
                        project_repo = PostgresProjectRepository(postgres)
                        release_repo = PostgresReleaseRepository(postgres)

                        # Get project and release IDs
                        project = await project_repo.get_project_by_name(project_name)
                        if project and project.id:
                            release = await release_repo.get_release(
                                project.id, version
                            )
                            if release and release.id:
                                # Find file record
                                files = await file_repo.get_files_for_release(
                                    release.id
                                )
                                file_obj = next(
                                    (f for f in files if f.filename == filename), None
                                )

                                if file_obj and file_obj.id:
                                    # Update download count in the database
                                    await file_repo.update_download_stats(
                                        file_obj.id, increment_by=10
                                    )

                                    # Update detailed stats in the download_stats JSONB field
                                    if file_obj.download_stats is None:
                                        file_obj.download_stats = {}

                                    # Add day-based stats
                                    today = datetime.now().strftime("%Y-%m-%d")
                                    if "daily" not in file_obj.download_stats:
                                        file_obj.download_stats["daily"] = {}

                                    # Increment today's count
                                    file_obj.download_stats["daily"][today] = (
                                        file_obj.download_stats["daily"].get(today, 0)
                                        + 10
                                    )

                                    # Store in database
                                    await file_repo.update_file(file_obj)
                    except Exception as e:
                        import logging

                        logging.getLogger(__name__).warning(
                            f"Error updating download stats in database: {e}"
                        )
            except Exception as e:
                import logging

                logging.getLogger(__name__).warning(
                    f"Error tracking download stats: {e}"
                )

    # Try to get file from cache first
    if cache_repo:
        cache_key = f"file_content:{file_path}"
        cached_data = await cache_repo.get(cache_key)
        if cached_data and isinstance(cached_data, dict):
            content = cached_data.get("content")
            if isinstance(content, str):
                content = content.encode("utf-8")
            return (
                content,
                cached_data.get("content_type", "application/octet-stream"),
                cached_data.get("headers", {}),
            )

    # Get file content from storage
    content = await storage_repo.get_file(file_path)

    # Get file metadata
    metadata = await storage_repo.get_file_metadata(file_path)
    content_type = metadata.get("content_type", "application/octet-stream")

    # Prepare headers
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": content_type,
        "Content-Length": str(len(content)),
        "ETag": metadata.get("etag", f'"{hashlib.sha256(content).hexdigest()[:32]}"'),
        "Last-Modified": metadata.get("last_modified", datetime.utcnow()).strftime(
            "%a, %d %b %Y %H:%M:%S GMT"
        ),
    }

    # Add any additional metadata as headers
    for key, value in metadata.items():
        if key not in ["content_type", "etag", "size", "last_modified"]:
            headers[f"X-{key.capitalize()}"] = str(value)

    # Cache the file content for frequently accessed files (if size is reasonable)
    if cache_repo and len(content) < 5 * 1024 * 1024:  # Only cache files < 5MB
        try:
            await cache_repo.set(
                f"file_content:{file_path}",
                {"content": content, "content_type": content_type, "headers": headers},
                expire=60 * 60,  # Cache for 1 hour
            )
        except Exception as e:
            import logging

            logging.getLogger(__name__).warning(f"Error caching file content: {e}")

    return content, content_type, headers


async def get_file_metadata(
    file_path: str,
    postgres: PostgresClient,
    s3: S3Client,
    valkey: ValkeyClient | None = None,
) -> FileMetadata:
    """Returns metadata for the specified file"""
    # Parse file path to extract project name, version and filename
    parts = file_path.split("/")
    filename = parts[-1]

    # A typical file path is expected to be {project_name}/{version}/{filename}
    if len(parts) >= 3:
        project_name = parts[-3]
        version = parts[-2]
    else:
        # Fall back to parsing from filename if path doesn't match expected pattern
        project_parts = filename.split("-")
        if len(project_parts) >= 2:
            project_name = "-".join(project_parts[:-1])
            version = project_parts[-1].split(".")[0]
        else:
            project_name = "unknown"
            version = "0.0.0"

    # Create storage repository
    from app.repos.postgres.file_repo import PostgresFileRepository
    from app.repos.postgres.project_repo import PostgresProjectRepository
    from app.repos.postgres.release_repo import PostgresReleaseRepository
    from app.repos.s3.storage_repo import S3StorageRepository

    # s3 is a parameter passed to the function
    storage_repo = S3StorageRepository(s3)
    file_repo = PostgresFileRepository(postgres)
    project_repo = PostgresProjectRepository(postgres)
    release_repo = PostgresReleaseRepository(postgres)

    # Check if file exists in storage
    try:
        # Get storage metadata first
        s3_metadata = await storage_repo.get_file_metadata(file_path)

        # Try to get project from database
        project = await project_repo.get_project_by_name(project_name)
        if project and project.id:
            # Try to get release
            release = await release_repo.get_release(project.id, version)
            if release and release.id:
                # Try to get file metadata from database
                files = await file_repo.get_files_for_release(release.id)
                file_obj = next((f for f in files if f.filename == filename), None)

                if file_obj:
                    # Use the database record if available
                    return FileMetadata(
                        filename=file_obj.filename,
                        project=project.name,
                        version=release.version,
                        content_type=file_obj.content_type,
                        size=file_obj.size,
                        sha256=file_obj.sha256_digest,
                        upload_time=file_obj.upload_time.isoformat(),
                        requires_python=file_obj.requires_python,
                        has_metadata=file_obj.has_metadata,
                        metadata_sha256=file_obj.metadata_sha256,
                    )
    except Exception as e:
        # Log error but continue to fallback
        import logging

        logging.getLogger(__name__).warning(f"Error getting file metadata: {e}")

    # Fallback to S3 metadata if database lookup fails
    try:
        from app.repos.s3.storage_repo import S3StorageRepository

        # s3 is a parameter passed to the function
        storage_repo = S3StorageRepository(s3)

        # Get storage metadata
        s3_metadata = await storage_repo.get_file_metadata(file_path)

        # Determine content type from S3 metadata or filename
        content_type = s3_metadata.get("content_type", "application/octet-stream")
        if not content_type or content_type == "application/octet-stream":
            if filename.endswith(".tar.gz"):
                content_type = "application/x-tar"
            elif filename.endswith(".whl"):
                content_type = "application/wheel+zip"
            elif filename.endswith(".zip"):
                content_type = "application/zip"

        # Create metadata from S3 info
        return FileMetadata(
            filename=filename,
            project=project_name,
            version=version,
            content_type=content_type,
            size=s3_metadata.get("size", 0),
            sha256=s3_metadata.get("sha256", ""),
            upload_time=datetime.utcnow().isoformat(),  # S3 doesn't store original upload time
            requires_python=s3_metadata.get("requires-python"),
            has_metadata=False,  # Can't determine this from S3 metadata alone
            metadata_sha256=None,
        )

    except Exception:
        # Final fallback - return basic metadata based on filename
        import logging

        logging.getLogger(__name__).exception("Error getting S3 file metadata")

        # Determine content type from filename
        content_type = "application/octet-stream"
        if filename.endswith(".tar.gz"):
            content_type = "application/x-tar"
        elif filename.endswith(".whl"):
            content_type = "application/wheel+zip"
        elif filename.endswith(".zip"):
            content_type = "application/zip"

        # Create basic metadata
        return FileMetadata(
            filename=filename,
            project=project_name,
            version=version,
            content_type=content_type,
            size=0,
            sha256="",
            upload_time=datetime.utcnow().isoformat(),
            requires_python=None,
            has_metadata=False,
            metadata_sha256=None,
        )


async def download_file_metadata(
    file_path: str,
    postgres: PostgresClient,
    s3: S3Client,
    valkey: ValkeyClient | None = None,
) -> tuple[bytes, str, dict[str, str]]:
    """
    Download metadata for a file.

    Args:
        file_path: The path to the file (without .metadata extension)
        postgres: PostgreSQL client
        s3: S3 client
        valkey: Valkey client (optional)

    Returns:
        Tuple of (metadata_content, content_type, headers)
    """
    # Try to get metadata from cache if available
    cache_key = f"metadata:{file_path}"
    if valkey:
        from app.repos.valkey.cache_repo import ValkeyCacheRepository

        cache_repo = ValkeyCacheRepository(valkey)
        cached_data = await cache_repo.get(cache_key)
        if cached_data and isinstance(cached_data, dict):
            content = cached_data.get("content")
            if content:
                # Convert string back to bytes if needed
                if isinstance(content, str):
                    content = content.encode("utf-8")
                headers = cached_data.get("headers", {})
                return content, "text/plain", headers

    # Parse file path to extract project name, version and filename
    parts = file_path.split("/")
    filename = parts[-1]

    # A typical file path is expected to be {project_name}/{version}/{filename}
    if len(parts) >= 3:
        project_name = parts[-3]
        version = parts[-2]
    else:
        # Fall back to parsing from filename if path doesn't match expected pattern
        project_parts = filename.split("-")
        if len(project_parts) >= 2:
            project_name = "-".join(project_parts[:-1])
            version = project_parts[-1].split(".")[0]
        else:
            project_name = "unknown"
            version = "0.0.0"

    # First check if we have metadata in the database
    try:
        from app.repos.postgres.file_repo import PostgresFileRepository
        from app.repos.postgres.project_repo import PostgresProjectRepository
        from app.repos.postgres.release_repo import PostgresReleaseRepository

        file_repo = PostgresFileRepository(postgres)
        project_repo = PostgresProjectRepository(postgres)
        release_repo = PostgresReleaseRepository(postgres)

        # Get project, release, and file metadata from database
        project = await project_repo.get_project_by_name(project_name)
        if project and project.id:
            release = await release_repo.get_release(project.id, version)
            if release and release.id:
                files = await file_repo.get_files_for_release(release.id)
                file_obj = next((f for f in files if f.filename == filename), None)

                if file_obj and file_obj.has_metadata and file_obj.metadata_sha256:
                    # Check if we have a metadata file in S3
                    metadata_path = f"{file_path}.metadata"
                    from app.repos.s3.storage_repo import S3StorageRepository

                    storage_repo = S3StorageRepository(s3)

                    if await storage_repo.file_exists(metadata_path):
                        # Get metadata content from S3
                        metadata_content = await storage_repo.get_file(metadata_path)
                        metadata = await storage_repo.get_file_metadata(metadata_path)

                        # Set appropriate headers
                        headers = {
                            "Content-Type": "text/plain",
                            "Content-Length": str(len(metadata_content)),
                            "ETag": f'"{file_obj.metadata_sha256[:32]}"',
                            "Last-Modified": metadata.get(
                                "last_modified", datetime.utcnow()
                            ).strftime("%a, %d %b %Y %H:%M:%S GMT"),
                        }

                        # Cache the metadata
                        if valkey:
                            await cache_repo.set(
                                cache_key,
                                {"content": metadata_content, "headers": headers},
                                expire=60 * 60,  # Cache for 1 hour
                            )

                        return metadata_content, "text/plain", headers
    except Exception as e:
        # Log error but continue to generate fallback metadata
        import logging

        logging.getLogger(__name__).warning(
            f"Error getting metadata from database: {e}"
        )

    # If we reach here, we need to generate metadata from file information
    # Use metadata from file_metadata function
    file_meta = await get_file_metadata(file_path, postgres, s3, valkey)

    # Generate metadata content based on available information
    metadata_lines = [
        "Metadata-Version: 2.1",
        f"Name: {file_meta.project}",
        f"Version: {file_meta.version}",
    ]

    # Add optional fields if available
    if file_meta.requires_python:
        metadata_lines.append(f"Requires-Python: {file_meta.requires_python}")

    # Finish with some default values
    metadata_content = "\n".join(metadata_lines).encode()

    # Set appropriate headers
    headers = {
        "Content-Type": "text/plain",
        "Content-Length": str(len(metadata_content)),
        "ETag": f'"{hashlib.sha256(metadata_content).hexdigest()[:32]}"',
        "Last-Modified": datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT"),
        "X-Generated": "true",  # Indicate this is generated, not real metadata
    }

    # Cache the generated metadata
    if valkey:
        await cache_repo.set(
            cache_key,
            {"content": metadata_content, "headers": headers},
            expire=60 * 60,  # Cache for 1 hour
        )

    return metadata_content, "text/plain", headers
