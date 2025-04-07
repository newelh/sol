from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

# Data models for projects, releases, and files following PyPI's schema


class Project(BaseModel):
    """Package in the repository with metadata and versioning information."""

    id: int | None = None  # Primary key in database
    name: str  # Original package name with case preserved (e.g., "Flask")
    normalized_name: str  # PEP 503 normalized name for lookups (e.g., "flask")
    description: str | None = None
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    def __init__(self, **data: Any) -> None:
        if "normalized_name" not in data and "name" in data:
            # Auto-generate normalized_name from name
            import re

            data["normalized_name"] = re.sub(r"[-_.]+", "-", data["name"].lower())
        super().__init__(**data)


class Release(BaseModel):
    """Specific version of a project with its metadata and dependencies."""

    id: int | None = None  # Primary key in database
    project_id: int | None = None  # Foreign key to the parent Project
    version: str  # Version string (e.g., "2.28.1")
    requires_python: str | None = None  # Python version specifier (e.g., ">=3.7")
    is_prerelease: bool = False  # Flag for pre-release versions (alpha/beta/rc)
    yanked: bool = False  # PEP 592: Flag for yanked/removed releases
    yank_reason: str | None = None  # Optional reason why a release was yanked
    uploaded_at: datetime = Field(default_factory=datetime.utcnow)
    summary: str | None = None  # Short description for the release
    description: str | None = None
    author: str | None = None
    author_email: str | None = None
    maintainer: str | None = None
    maintainer_email: str | None = None
    license: str | None = None
    keywords: str | None = None
    classifiers: list[str] = Field(default_factory=list)
    platform: str | None = None
    home_page: str | None = None
    download_url: str | None = None
    requires_dist: list[str] = Field(default_factory=list)
    provides_dist: list[str] = Field(default_factory=list)
    obsoletes_dist: list[str] = Field(default_factory=list)
    requires_external: list[str] = Field(default_factory=list)
    project_urls: dict[str, str] = Field(default_factory=dict)


class File(BaseModel):
    """Distribution file (wheel, sdist, etc.) with metadata and content information."""

    id: int | None = None  # Primary key in database
    release_id: int | None = None  # Foreign key to the parent Release
    filename: str  # The actual filename (e.g., "flask-2.0.1-py3-none-any.whl")
    size: int  # Size in bytes - required by PEP 691
    # File hashes, following PEP 503 and PEP 691 requirements
    md5_digest: str | None = None  # Legacy checksum - kept for backward compatibility
    sha256_digest: str  # Primary secure checksum - required for all files
    blake2_256_digest: str | None = None  # Alternative hash for future compatibility
    upload_time: datetime = Field(default_factory=datetime.utcnow)
    uploaded_by: str | None = None  # Username or API key identifier of uploader
    path: str  # S3 object key: {project}/{release}/{filename}
    content_type: str
    packagetype: str  # sdist, bdist_wheel, etc.
    python_version: str  # py3, source, etc.
    requires_python: str | None = None
    has_signature: bool = False
    has_metadata: bool = False
    metadata_sha256: str | None = None
    is_yanked: bool = False
    yank_reason: str | None = None
    metadata_version: str | None = None
    summary: str | None = None
    description: str | None = None
    description_content_type: str | None = None
    author: str | None = None
    author_email: str | None = None
    maintainer: str | None = None
    maintainer_email: str | None = None
    license: str | None = None
    keywords: str | None = None
    classifiers: list[str] = Field(default_factory=list)
    platform: str | None = None
    home_page: str | None = None
    download_url: str | None = None
    requires_dist: list[str] = Field(default_factory=list)
    provides_dist: list[str] = Field(default_factory=list)
    obsoletes_dist: list[str] = Field(default_factory=list)
    requires_external: list[str] = Field(default_factory=list)
    project_urls: dict[str, str] = Field(default_factory=dict)

    @property
    def hashes(self) -> dict[str, str]:
        """Get all available hashes for the file."""
        result = {}
        if self.md5_digest:
            result["md5"] = self.md5_digest
        if self.sha256_digest:
            result["sha256"] = self.sha256_digest
        if self.blake2_256_digest:
            result["blake2b_256"] = self.blake2_256_digest
        return result
