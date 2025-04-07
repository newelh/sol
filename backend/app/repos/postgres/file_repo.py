import json
from datetime import datetime
from typing import Any

from app.core.clients.postgres import PostgresClient
from app.domain.models import File
from app.repos.interfaces import FileRepository

# Error messages
CANNOT_CONVERT_NONE = "Cannot convert None to File object"


class PostgresFileRepository(FileRepository):
    """Repository for managing package file storage and retrieval in PostgreSQL."""

    def __init__(self, postgres: PostgresClient):
        self.postgres = postgres

    async def get_files_for_release(self, release_id: int) -> list[File]:
        """
        Get all files for a release.

        Uses the indexed release_id column for efficient lookup, then sorts by
        filename which is commonly the order needed by clients.
        This query benefits from a compound index on (release_id, filename).
        """
        query = """
        SELECT
            id, release_id, filename, size, md5_digest, sha256_digest,
            blake2_256_digest, upload_time, uploaded_by, path, content_type,
            packagetype, python_version, requires_python, has_signature,
            has_metadata, metadata_sha256, is_yanked, yank_reason,
            metadata_version, summary, description, description_content_type,
            author, author_email, maintainer, maintainer_email, license,
            keywords, classifiers, platform, home_page, download_url,
            requires_dist, provides_dist, obsoletes_dist, requires_external,
            project_urls
        FROM files
        WHERE release_id = $1
        ORDER BY filename
        """
        rows = await self.postgres.fetch(query, release_id)
        return [self._row_to_file(row) for row in rows]

    async def get_file_by_filename(self, release_id: int, filename: str) -> File | None:
        """Get a file by filename within a release."""
        query = """
        SELECT
            id, release_id, filename, size, md5_digest, sha256_digest,
            blake2_256_digest, upload_time, uploaded_by, path, content_type,
            packagetype, python_version, requires_python, has_signature,
            has_metadata, metadata_sha256, is_yanked, yank_reason,
            metadata_version, summary, description, description_content_type,
            author, author_email, maintainer, maintainer_email, license,
            keywords, classifiers, platform, home_page, download_url,
            requires_dist, provides_dist, obsoletes_dist, requires_external,
            project_urls
        FROM files
        WHERE release_id = $1 AND filename = $2
        """
        row = await self.postgres.fetchrow(query, release_id, filename)
        if row is None:
            return None
        return self._row_to_file(row)

    async def create_file(self, file: File) -> File:
        """Create a new file."""
        # Convert list fields to JSON strings for PostgreSQL
        classifiers_json = json.dumps(file.classifiers) if file.classifiers else "[]"
        requires_dist_json = (
            json.dumps(file.requires_dist) if file.requires_dist else "[]"
        )
        provides_dist_json = (
            json.dumps(file.provides_dist) if file.provides_dist else "[]"
        )
        obsoletes_dist_json = (
            json.dumps(file.obsoletes_dist) if file.obsoletes_dist else "[]"
        )
        requires_external_json = (
            json.dumps(file.requires_external) if file.requires_external else "[]"
        )
        project_urls_json = json.dumps(file.project_urls) if file.project_urls else "{}"

        query = """
        INSERT INTO files (
            release_id, filename, size, md5_digest, sha256_digest,
            blake2_256_digest, uploaded_by, path, content_type,
            packagetype, python_version, requires_python, has_signature,
            has_metadata, metadata_sha256, is_yanked, yank_reason,
            metadata_version, summary, description, description_content_type,
            author, author_email, maintainer, maintainer_email, license,
            keywords, classifiers, platform, home_page, download_url,
            requires_dist, provides_dist, obsoletes_dist, requires_external,
            project_urls
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13, $14, $15,
            $16, $17, $18, $19, $20, $21, $22, $23, $24, $25, $26, $27, $28,
            $29, $30, $31, $32, $33, $34, $35, $36
        )
        RETURNING
            id, release_id, filename, size, md5_digest, sha256_digest,
            blake2_256_digest, upload_time, uploaded_by, path, content_type,
            packagetype, python_version, requires_python, has_signature,
            has_metadata, metadata_sha256, is_yanked, yank_reason,
            metadata_version, summary, description, description_content_type,
            author, author_email, maintainer, maintainer_email, license,
            keywords, classifiers, platform, home_page, download_url,
            requires_dist, provides_dist, obsoletes_dist, requires_external,
            project_urls
        """
        row = await self.postgres.fetchrow(
            query,
            file.release_id,
            file.filename,
            file.size,
            file.md5_digest,
            file.sha256_digest,
            file.blake2_256_digest,
            file.uploaded_by,
            file.path,
            file.content_type,
            file.packagetype,
            file.python_version,
            file.requires_python,
            file.has_signature,
            file.has_metadata,
            file.metadata_sha256,
            file.is_yanked,
            file.yank_reason,
            file.metadata_version,
            file.summary,
            file.description,
            file.description_content_type,
            file.author,
            file.author_email,
            file.maintainer,
            file.maintainer_email,
            file.license,
            file.keywords,
            classifiers_json,
            file.platform,
            file.home_page,
            file.download_url,
            requires_dist_json,
            provides_dist_json,
            obsoletes_dist_json,
            requires_external_json,
            project_urls_json,
        )
        return self._row_to_file(row)

    async def update_file(self, file: File) -> File:
        """Update an existing file."""
        # Convert list fields to JSON strings for PostgreSQL
        classifiers_json = json.dumps(file.classifiers) if file.classifiers else "[]"
        requires_dist_json = (
            json.dumps(file.requires_dist) if file.requires_dist else "[]"
        )
        provides_dist_json = (
            json.dumps(file.provides_dist) if file.provides_dist else "[]"
        )
        obsoletes_dist_json = (
            json.dumps(file.obsoletes_dist) if file.obsoletes_dist else "[]"
        )
        requires_external_json = (
            json.dumps(file.requires_external) if file.requires_external else "[]"
        )
        project_urls_json = json.dumps(file.project_urls) if file.project_urls else "{}"

        query = """
        UPDATE files
        SET
            size = $3,
            md5_digest = $4,
            sha256_digest = $5,
            blake2_256_digest = $6,
            uploaded_by = $7,
            path = $8,
            content_type = $9,
            packagetype = $10,
            python_version = $11,
            requires_python = $12,
            has_signature = $13,
            has_metadata = $14,
            metadata_sha256 = $15,
            is_yanked = $16,
            yank_reason = $17,
            metadata_version = $18,
            summary = $19,
            description = $20,
            description_content_type = $21,
            author = $22,
            author_email = $23,
            maintainer = $24,
            maintainer_email = $25,
            license = $26,
            keywords = $27,
            classifiers = $28,
            platform = $29,
            home_page = $30,
            download_url = $31,
            requires_dist = $32,
            provides_dist = $33,
            obsoletes_dist = $34,
            requires_external = $35,
            project_urls = $36
        WHERE id = $1 AND release_id = $2
        RETURNING
            id, release_id, filename, size, md5_digest, sha256_digest,
            blake2_256_digest, upload_time, uploaded_by, path, content_type,
            packagetype, python_version, requires_python, has_signature,
            has_metadata, metadata_sha256, is_yanked, yank_reason,
            metadata_version, summary, description, description_content_type,
            author, author_email, maintainer, maintainer_email, license,
            keywords, classifiers, platform, home_page, download_url,
            requires_dist, provides_dist, obsoletes_dist, requires_external,
            project_urls
        """
        row = await self.postgres.fetchrow(
            query,
            file.id,
            file.release_id,
            file.size,
            file.md5_digest,
            file.sha256_digest,
            file.blake2_256_digest,
            file.uploaded_by,
            file.path,
            file.content_type,
            file.packagetype,
            file.python_version,
            file.requires_python,
            file.has_signature,
            file.has_metadata,
            file.metadata_sha256,
            file.is_yanked,
            file.yank_reason,
            file.metadata_version,
            file.summary,
            file.description,
            file.description_content_type,
            file.author,
            file.author_email,
            file.maintainer,
            file.maintainer_email,
            file.license,
            file.keywords,
            classifiers_json,
            file.platform,
            file.home_page,
            file.download_url,
            requires_dist_json,
            provides_dist_json,
            obsoletes_dist_json,
            requires_external_json,
            project_urls_json,
        )
        return self._row_to_file(row)

    async def delete_file(self, file_id: int) -> bool:
        """Delete a file."""
        query = """
        DELETE FROM files
        WHERE id = $1
        """
        result = await self.postgres.execute(query, file_id)
        return "DELETE 1" in result

    async def yank_file(self, file_id: int, reason: str | None = None) -> bool:
        """Mark a file as yanked."""
        query = """
        UPDATE files
        SET is_yanked = TRUE, yank_reason = $2
        WHERE id = $1
        """
        result = await self.postgres.execute(query, file_id, reason)
        return "UPDATE 1" in result

    async def unyank_file(self, file_id: int) -> bool:
        """Unmark a file as yanked."""
        query = """
        UPDATE files
        SET is_yanked = FALSE, yank_reason = NULL
        WHERE id = $1
        """
        result = await self.postgres.execute(query, file_id)
        return "UPDATE 1" in result

    def _row_to_file(self, row: dict[str, Any] | None) -> File:
        """Transform database row into File domain object with JSON field parsing."""
        if row is None:
            raise ValueError(CANNOT_CONVERT_NONE)

        # Parse JSON strings for list and dict fields
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

        # Handle JSONB columns
        classifiers = parse_json_list(row.get("classifiers"))
        requires_dist = parse_json_list(row.get("requires_dist"))
        provides_dist = parse_json_list(row.get("provides_dist"))
        obsoletes_dist = parse_json_list(row.get("obsoletes_dist"))
        requires_external = parse_json_list(row.get("requires_external"))
        project_urls = parse_json_dict(row.get("project_urls"))

        return File(
            id=row["id"],
            release_id=row["release_id"],
            filename=row["filename"],
            size=row["size"],
            md5_digest=row.get("md5_digest"),
            sha256_digest=row["sha256_digest"],
            blake2_256_digest=row.get("blake2_256_digest"),
            upload_time=row.get("upload_time", datetime.utcnow()),
            uploaded_by=row.get("uploaded_by"),
            path=row["path"],
            content_type=row["content_type"],
            packagetype=row["packagetype"],
            python_version=row["python_version"],
            requires_python=row.get("requires_python"),
            has_signature=row.get("has_signature", False),
            has_metadata=row.get("has_metadata", False),
            metadata_sha256=row.get("metadata_sha256"),
            is_yanked=row.get("is_yanked", False),
            yank_reason=row.get("yank_reason"),
            metadata_version=row.get("metadata_version"),
            summary=row.get("summary"),
            description=row.get("description"),
            description_content_type=row.get("description_content_type"),
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
