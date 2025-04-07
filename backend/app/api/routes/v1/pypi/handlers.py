import re
from datetime import UTC, datetime

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
    # In a real implementation, we would fetch this from the database
    # For now, return a simple mock response
    normalized_name = normalize_name(project_name)

    # Check if project exists (mock implementation)
    if normalized_name not in ["example-package", "another-package"]:
        # Return an empty response rather than None
        return ProjectJSONResponse(
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

    # Create mock project info
    info = ProjectInfo(
        name=normalized_name,
        version="1.0",
        summary="A sample project",
        description="A longer description of the sample project",
        author="Sample Author",
        author_email="author@example.com",
        license="MIT",
        classifiers=[
            "Programming Language :: Python :: 3",
            "License :: OSI Approved :: MIT License",
        ],
        requires_python=">=3.7",
    )

    # Create mock release files
    now = datetime.now(UTC)
    iso_time = now.isoformat()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    # Create two file types for the release
    sdist = ReleaseFile(
        filename=f"{normalized_name}-1.0.tar.gz",
        url=f"/files/{normalized_name}-1.0.tar.gz",
        size=12345,
        digests={
            "md5": "d41d8cd98f00b204e9800998ecf8427e",
            "sha256": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        },
        requires_python=">=3.7",
        upload_time=timestamp,
        upload_time_iso_8601=iso_time,
        packagetype="sdist",
        python_version="source",
        yanked=False,
    )

    wheel = ReleaseFile(
        filename=f"{normalized_name}-1.0-py3-none-any.whl",
        url=f"/files/{normalized_name}-1.0-py3-none-any.whl",
        size=10000,
        digests={
            "md5": "d41d8cd98f00b204e9800998ecf8427e",
            "sha256": "a41368344c239e5e93d5472b75625606362a6d7f4612aade9c5ef7aa8b70ce73",
        },
        requires_python=">=3.7",
        upload_time=timestamp,
        upload_time_iso_8601=iso_time,
        packagetype="bdist_wheel",
        python_version="py3",
        yanked=False,
    )

    return ProjectJSONResponse(
        info=info,
        last_serial=123456,
        releases={"1.0": [sdist, wheel]},
        urls=[sdist, wheel],
    )
