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
    # TODO: Implement caching, download stats, etc.

    # Parse file path to extract filename (project name not needed here)
    parts = file_path.split("/")
    filename = parts[-1]

    # Mock metadata
    is_wheel = filename.endswith(".whl")
    content_type = "application/octet-stream"
    if filename.endswith(".tar.gz"):
        content_type = "application/x-tar"
    elif is_wheel:
        content_type = "application/wheel+zip"
    elif filename.endswith(".zip"):
        content_type = "application/zip"

    # Generate mock file content
    content = f"Mock content for {filename}".encode()

    # Set appropriate headers
    headers = {
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Type": content_type,
        "Content-Length": str(len(content)),
        "ETag": f'"{hashlib.sha256(content).hexdigest()[:32]}"',  # Use SHA256 but truncate to 32 chars similar to MD5 length
        "Last-Modified": datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT"),
    }

    return content, content_type, headers


async def get_file_metadata(
    file_path: str, postgres: PostgresClient, valkey: ValkeyClient | None = None
) -> FileMetadata:
    """Returns metadata for the specified file"""
    # TODO: Replace mock implementation with actual DB query

    # Parse file path to extract project name and filename
    parts = file_path.split("/")
    filename = parts[-1]

    # Try to extract project name and version from filename
    project_parts = filename.split("-")
    if len(project_parts) >= 2:
        project_name = "-".join(project_parts[:-1])
        version = project_parts[-1].split(".")[0]
    else:
        project_name = "unknown"
        version = "0.0.0"

    # Determine content type
    content_type = "application/octet-stream"
    if filename.endswith(".tar.gz"):
        content_type = "application/x-tar"
    elif filename.endswith(".whl"):
        content_type = "application/wheel+zip"
    elif filename.endswith(".zip"):
        content_type = "application/zip"

    # Create mock file metadata
    metadata = FileMetadata(
        filename=filename,
        project=project_name,
        version=version,
        content_type=content_type,
        size=12345,
        sha256="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        upload_time=datetime.utcnow().isoformat(),
        requires_python=">=3.7",
        has_metadata=True,
        metadata_sha256="a41368344c239e5e93d5472b75625606362a6d7f4612aade9c5ef7aa8b70ce73",
    )

    return metadata


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
    # In a real implementation, we would:
    # 1. Check if metadata exists in the cache
    # 2. If not, get file metadata from database
    # 3. Download the metadata from S3

    # For now, we'll return mock data

    # Parse file path to extract project name and filename
    parts = file_path.split("/")
    filename = parts[-1]
    project_name = "-".join(filename.split("-")[:-1]) if "-" in filename else "unknown"

    # Generate mock metadata content
    content = f"""Metadata-Version: 2.1
Name: {project_name}
Version: 1.0.0
Summary: A mock package
Home-page: https://example.com/{project_name}
Author: Example Author
Author-email: author@example.com
License: MIT
Requires-Python: >=3.7
Classifier: Programming Language :: Python :: 3
Classifier: License :: OSI Approved :: MIT License
Requires-Dist: requests
Requires-Dist: fastapi
""".encode()

    # Set appropriate headers
    headers = {
        "Content-Type": "text/plain",
        "Content-Length": str(len(content)),
        "ETag": f'"{hashlib.sha256(content).hexdigest()[:32]}"',  # Use SHA256 but truncate to 32 chars similar to MD5 length
        "Last-Modified": datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT"),
    }

    return content, "text/plain", headers
