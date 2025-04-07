import json
from datetime import datetime
from typing import Any

from app.core.clients.postgres import PostgresClient
from app.domain.models import Release
from app.repos.interfaces import ReleaseRepository


class PostgresReleaseRepository(ReleaseRepository):
    """PostgreSQL implementation of the release repository."""

    def __init__(self, postgres: PostgresClient):
        self.postgres = postgres

    async def get_all_releases(self, project_id: int) -> list[Release]:
        """Get all releases for a project."""
        query = """
        SELECT
            id, project_id, version, requires_python, is_prerelease,
            yanked, yank_reason, uploaded_at, summary, description,
            author, author_email, maintainer, maintainer_email,
            license, keywords, classifiers, platform, home_page,
            download_url, requires_dist, provides_dist, obsoletes_dist,
            requires_external, project_urls
        FROM releases
        WHERE project_id = $1
        ORDER BY uploaded_at DESC
        """
        rows = await self.postgres.fetch(query, project_id)
        return [self._row_to_release(row) for row in rows]

    async def get_release(self, project_id: int, version: str) -> Release | None:
        """Get a release by project_id and version."""
        query = """
        SELECT
            id, project_id, version, requires_python, is_prerelease,
            yanked, yank_reason, uploaded_at, summary, description,
            author, author_email, maintainer, maintainer_email,
            license, keywords, classifiers, platform, home_page,
            download_url, requires_dist, provides_dist, obsoletes_dist,
            requires_external, project_urls
        FROM releases
        WHERE project_id = $1 AND version = $2
        """
        row = await self.postgres.fetchrow(query, project_id, version)
        if row is None:
            return None
        return self._row_to_release(row)

    async def create_release(self, release: Release) -> Release:
        """Create a new release."""
        # Convert list fields to JSON strings for PostgreSQL
        classifiers_json = (
            json.dumps(release.classifiers) if release.classifiers else "[]"
        )
        requires_dist_json = (
            json.dumps(release.requires_dist) if release.requires_dist else "[]"
        )
        provides_dist_json = (
            json.dumps(release.provides_dist) if release.provides_dist else "[]"
        )
        obsoletes_dist_json = (
            json.dumps(release.obsoletes_dist) if release.obsoletes_dist else "[]"
        )
        requires_external_json = (
            json.dumps(release.requires_external) if release.requires_external else "[]"
        )
        project_urls_json = (
            json.dumps(release.project_urls) if release.project_urls else "{}"
        )

        query = """
        INSERT INTO releases (
            project_id, version, requires_python, is_prerelease,
            yanked, yank_reason, summary, description,
            author, author_email, maintainer, maintainer_email,
            license, keywords, classifiers, platform, home_page,
            download_url, requires_dist, provides_dist, obsoletes_dist,
            requires_external, project_urls
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13,
            $14, $15, $16, $17, $18, $19, $20, $21, $22, $23
        )
        RETURNING
            id, project_id, version, requires_python, is_prerelease,
            yanked, yank_reason, uploaded_at, summary, description,
            author, author_email, maintainer, maintainer_email,
            license, keywords, classifiers, platform, home_page,
            download_url, requires_dist, provides_dist, obsoletes_dist,
            requires_external, project_urls
        """
        row = await self.postgres.fetchrow(
            query,
            release.project_id,
            release.version,
            release.requires_python,
            release.is_prerelease,
            release.yanked,
            release.yank_reason,
            release.summary,
            release.description,
            release.author,
            release.author_email,
            release.maintainer,
            release.maintainer_email,
            release.license,
            release.keywords,
            classifiers_json,
            release.platform,
            release.home_page,
            release.download_url,
            requires_dist_json,
            provides_dist_json,
            obsoletes_dist_json,
            requires_external_json,
            project_urls_json,
        )
        return self._row_to_release(row)

    async def update_release(self, release: Release) -> Release:
        """Update an existing release."""
        query = """
        UPDATE releases
        SET
            requires_python = $3,
            is_prerelease = $4,
            yanked = $5,
            yank_reason = $6,
            summary = $7,
            description = $8,
            author = $9,
            author_email = $10,
            maintainer = $11,
            maintainer_email = $12,
            license = $13,
            keywords = $14,
            classifiers = $15,
            platform = $16,
            home_page = $17,
            download_url = $18,
            requires_dist = $19,
            provides_dist = $20,
            obsoletes_dist = $21,
            requires_external = $22,
            project_urls = $23
        WHERE id = $1 AND project_id = $2
        RETURNING
            id, project_id, version, requires_python, is_prerelease,
            yanked, yank_reason, uploaded_at, summary, description,
            author, author_email, maintainer, maintainer_email,
            license, keywords, classifiers, platform, home_page,
            download_url, requires_dist, provides_dist, obsoletes_dist,
            requires_external, project_urls
        """
        row = await self.postgres.fetchrow(
            query,
            release.id,
            release.project_id,
            release.requires_python,
            release.is_prerelease,
            release.yanked,
            release.yank_reason,
            release.summary,
            release.description,
            release.author,
            release.author_email,
            release.maintainer,
            release.maintainer_email,
            release.license,
            release.keywords,
            release.classifiers,
            release.platform,
            release.home_page,
            release.download_url,
            release.requires_dist,
            release.provides_dist,
            release.obsoletes_dist,
            release.requires_external,
            release.project_urls,
        )
        return self._row_to_release(row)

    async def delete_release(self, release_id: int) -> bool:
        """Delete a release."""
        query = """
        DELETE FROM releases
        WHERE id = $1
        """
        result = await self.postgres.execute(query, release_id)
        return "DELETE 1" in result

    async def yank_release(self, release_id: int, reason: str | None = None) -> bool:
        """Mark a release as yanked."""
        query = """
        UPDATE releases
        SET yanked = TRUE, yank_reason = $2
        WHERE id = $1
        """
        result = await self.postgres.execute(query, release_id, reason)
        return "UPDATE 1" in result

    async def unyank_release(self, release_id: int) -> bool:
        """Unmark a release as yanked."""
        query = """
        UPDATE releases
        SET yanked = FALSE, yank_reason = NULL
        WHERE id = $1
        """
        result = await self.postgres.execute(query, release_id)
        return "UPDATE 1" in result

    def _row_to_release(self, row: dict[str, Any] | None) -> Release:
        """Convert a database row to a Release model."""
        if row is None:
            # Return a minimal valid Release object if row is None
            return Release(
                id=0, project_id=0, version="", uploaded_at=datetime.utcnow()
            )

        # Handle JSONB columns that may be returned as strings
        # Parse JSON strings if needed
        def parse_json_list(value: Any) -> list[Any]:
            if isinstance(value, str):
                try:
                    result = json.loads(value)
                except json.JSONDecodeError:
                    return []
                else:
                    if isinstance(result, list):
                        return result
                    return []
            return value or []

        def parse_json_dict(value: Any) -> dict[str, Any]:
            if isinstance(value, str):
                try:
                    result = json.loads(value)
                except json.JSONDecodeError:
                    return {}
                else:
                    if isinstance(result, dict):
                        return result
                    return {}
            return value or {}

        classifiers = parse_json_list(row.get("classifiers"))
        requires_dist = parse_json_list(row.get("requires_dist"))
        provides_dist = parse_json_list(row.get("provides_dist"))
        obsoletes_dist = parse_json_list(row.get("obsoletes_dist"))
        requires_external = parse_json_list(row.get("requires_external"))
        project_urls = parse_json_dict(row.get("project_urls"))

        return Release(
            id=row["id"],
            project_id=row["project_id"],
            version=row["version"],
            requires_python=row.get("requires_python"),
            is_prerelease=row.get("is_prerelease", False),
            yanked=row.get("yanked", False),
            yank_reason=row.get("yank_reason"),
            uploaded_at=row.get("uploaded_at", datetime.utcnow()),
            summary=row.get("summary"),
            description=row.get("description"),
            author=row.get("author"),
            author_email=row.get("author_email"),
            maintainer=row.get("maintainer"),
            maintainer_email=row.get("maintainer_email"),
            license=row.get("license"),
            keywords=row.get("keywords"),
            classifiers=classifiers,
            platform=row.get("platform"),
            home_page=row.get("home_page"),
            download_url=row.get("download_url"),
            requires_dist=requires_dist,
            provides_dist=provides_dist,
            obsoletes_dist=obsoletes_dist,
            requires_external=requires_external,
            project_urls=project_urls,
        )
