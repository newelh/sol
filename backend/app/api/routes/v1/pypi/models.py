from pydantic import BaseModel, Field, HttpUrl


class ProjectInfo(BaseModel):
    """Project info for the PyPI JSON API."""

    name: str
    version: str
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
    home_page: HttpUrl | None = None
    download_url: HttpUrl | None = None
    requires_python: str | None = None
    requires_dist: list[str] = Field(default_factory=list)
    provides_dist: list[str] = Field(default_factory=list)
    obsoletes_dist: list[str] = Field(default_factory=list)
    requires_external: list[str] = Field(default_factory=list)
    project_url: dict[str, str] | None = None
    yanked: bool | None = None
    yanked_reason: str | None = None


class ReleaseFile(BaseModel):
    """Release file information for the PyPI JSON API."""

    filename: str
    url: str
    size: int
    digests: dict[str, str]
    requires_python: str | None = None
    upload_time: str
    upload_time_iso_8601: str
    packagetype: str
    python_version: str
    yanked: bool = False
    yanked_reason: str | None = None
    has_sig: bool = False
    comment_text: str | None = None


class ProjectJSONResponse(BaseModel):
    """Full project response for the PyPI JSON API."""

    info: ProjectInfo
    last_serial: int
    releases: dict[str, list[ReleaseFile]]
    urls: list[ReleaseFile] = Field(default_factory=list)
