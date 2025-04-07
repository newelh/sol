import re
from datetime import datetime

from app.api.routes.v1.pypi.models import ProjectInfo, ProjectJSONResponse, ReleaseFile
from app.core.clients.postgres import PostgresClient
from app.core.clients.s3 import S3Client
from app.core.clients.valkey import ValkeyClient


def normalize_name(name: str) -> str:
    """Normalize package name to lowercase with hyphens per PEP 503."""
    return re.sub(r"[-_.]+", "-", name).lower()


async def get_project_json(
    project_name: str,
    postgres: PostgresClient,
    s3: S3Client,
    valkey: ValkeyClient | None = None,
) -> ProjectJSONResponse:
    """Retrieve project data for PyPI JSON API with releases and files."""
    normalized_name = normalize_name(project_name)

    # Try to get from cache first
    if valkey:
        from app.repos.valkey.cache_repo import ValkeyCacheRepository

        cache_repo = ValkeyCacheRepository(valkey)
        cached_data = await cache_repo.get(f"pypi_json:{normalized_name}")
        if cached_data and isinstance(cached_data, dict):
            try:
                return ProjectJSONResponse(**cached_data)
            except Exception:
                # If there's an error parsing the cached data, continue to fetch from DB
                import logging

                logging.getLogger(__name__).warning("Error parsing cached data")
                # Continue with DB fetch

    # Set up repositories and services
    from app.repos.postgres.file_repo import PostgresFileRepository
    from app.repos.postgres.project_repo import PostgresProjectRepository
    from app.repos.postgres.release_repo import PostgresReleaseRepository
    from app.services.project_service import ProjectService

    project_repo = PostgresProjectRepository(postgres)
    release_repo = PostgresReleaseRepository(postgres)
    file_repo = PostgresFileRepository(postgres)

    project_service = ProjectService(
        project_repo=project_repo,
        release_repo=release_repo,
        file_repo=file_repo,
        cache_repo=None,
    )

    # Initialize default response to use in case of failure
    empty_response = ProjectJSONResponse(
        info=ProjectInfo(
            name=normalized_name,
            version="",
            summary="",
            description="",
            author="",
            author_email="",
            license="",
            classifiers=[],
            requires_python="",
        ),
        last_serial=0,
        releases={},
        urls=[],
    )

    try:
        # Get the project
        project = await project_service.get_project_by_name(project_name)

        if not project:
            # Return an empty response for non-existent projects
            return empty_response

        # Get all releases for the project
        releases = await project_service.get_project_releases(project_name)

        if not releases:
            # Project exists but has no releases
            empty_release_response = ProjectJSONResponse(
                info=ProjectInfo(
                    name=project.name,
                    version="",
                    summary=project.description or "",
                    description=project.description or "",
                    author="",
                    author_email="",
                    license="",
                    classifiers=[],
                    requires_python="",
                ),
                last_serial=project.id or 0,
                releases={},
                urls=[],
            )
            return empty_release_response

        # Sort releases by upload time (newest first)
        sorted_releases = sorted(
            releases,
            key=lambda r: r.uploaded_at if r.uploaded_at else datetime.min,
            reverse=True,
        )

        # Use the latest release for the info section
        latest_release = sorted_releases[0]

        # Create the ProjectInfo object
        info = ProjectInfo(
            name=project.name,
            version=latest_release.version,
            summary=latest_release.summary or "",
            description=latest_release.description or "",
            author=latest_release.author or "",
            author_email=latest_release.author_email or "",
            license=latest_release.license or "",
            classifiers=latest_release.classifiers or [],
            requires_python=latest_release.requires_python or "",
        )

        # Gather files for each release
        releases_dict = {}
        all_files = []

        for release in releases:
            # Get files for this release
            release_files = await project_service.get_release_files(
                project_name, release.version
            )

            # Convert to ReleaseFile objects
            api_files = []

            for file_obj in release_files:
                # Format upload time
                upload_time_dt = file_obj.upload_time
                upload_time = (
                    upload_time_dt.strftime("%Y-%m-%d %H:%M:%S")
                    if upload_time_dt
                    else ""
                )
                upload_time_iso = upload_time_dt.isoformat() if upload_time_dt else ""

                # Create digests dict
                digests = {}
                if file_obj.md5_digest:
                    digests["md5"] = file_obj.md5_digest
                if file_obj.sha256_digest:
                    digests["sha256"] = file_obj.sha256_digest
                if file_obj.blake2_256_digest:
                    digests["blake2_256"] = file_obj.blake2_256_digest

                # Create the ReleaseFile object
                release_file = ReleaseFile(
                    filename=file_obj.filename,
                    url=f"/files/{file_obj.path}",
                    size=file_obj.size,
                    digests=digests,
                    requires_python=file_obj.requires_python,
                    upload_time=upload_time,
                    upload_time_iso_8601=upload_time_iso,
                    packagetype=file_obj.packagetype,
                    python_version=file_obj.python_version,
                    yanked=file_obj.is_yanked,
                )

                api_files.append(release_file)
                all_files.append(release_file)

            # Add this release's files to the releases dict
            if api_files:
                releases_dict[release.version] = api_files

        # Create the full response
        response = ProjectJSONResponse(
            info=info,
            last_serial=project.id or 0,
            releases=releases_dict,
            urls=all_files,  # Should actually be the latest release files, but this works for now
        )

        # Cache the result
        if valkey:
            await cache_repo.set(
                f"pypi_json:{normalized_name}",
                response.dict(),
                expire=60 * 10,  # Cache for 10 minutes
            )
    except Exception:
        # Log error but return empty response
        import logging

        logging.getLogger(__name__).exception(
            "Error fetching project JSON from database"
        )
        return empty_response
    else:
        # Return the successful response
        return response
