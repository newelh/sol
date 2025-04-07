from pydantic import BaseModel, Field, HttpUrl


class ProjectReference(BaseModel):
    """Reference to a project in the simple index."""

    name: str


class FileHash(BaseModel):
    """Hash of a file."""

    algorithm: str
    value: str


class PackageFile(BaseModel):
    """File information for a package."""

    filename: str
    url: str | HttpUrl
    hashes: dict[str, str] = Field(default_factory=dict)
    requires_python: str | None = None
    core_metadata: bool | dict[str, str] | None = None
    dist_info_metadata: bool | dict[str, str] | None = None
    gpg_sig: bool | None = None
    yanked: bool | str | None = None
    size: int
    upload_time: str | None = None
    provenance: str | None = None


class ProjectDetail(BaseModel):
    """Project detail response model."""

    name: str
    files: list[PackageFile]
    versions: list[str] = Field(default_factory=list)
    meta: dict[str, str] = Field(default_factory=lambda: {"api-version": "1.3"})


class ProjectList(BaseModel):
    """Project list response model."""

    projects: list[ProjectReference]
    meta: dict[str, str] = Field(default_factory=lambda: {"api-version": "1.3"})
