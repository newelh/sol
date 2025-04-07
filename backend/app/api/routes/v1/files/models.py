from pydantic import BaseModel, Field


class FileMetadata(BaseModel):
    """Metadata for a package file."""

    filename: str
    project: str
    version: str
    content_type: str
    size: int
    sha256: str
    upload_time: str
    uploaded_by: str | None = None
    requires_python: str | None = None
    is_yanked: bool = False
    yank_reason: str | None = None
    has_signature: bool = False
    has_metadata: bool = False
    metadata_sha256: str | None = None
    custom_metadata: dict[str, str] = Field(default_factory=dict)
