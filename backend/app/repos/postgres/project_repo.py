import re
from string import Template

from app.core.clients.postgres import PostgresClient
from app.domain.models import Project
from app.repos.interfaces import ProjectRepository

# Error message templates
PROJECT_CREATE_ERROR = Template("Failed to create project: $name")
PROJECT_UPDATE_ERROR = Template("Failed to update project: $name")


def normalize_name(name: str) -> str:
    """Normalize a package name according to PEP 503."""
    return re.sub(r"[-_.]+", "-", name.lower())


class PostgresProjectRepository(ProjectRepository):
    """PostgreSQL implementation of the project repository."""

    def __init__(self, postgres: PostgresClient):
        self.postgres = postgres

    async def get_all_projects(self) -> list[Project]:
        """Get all projects in the repository."""
        query = """
        SELECT id, name, normalized_name, description, created_at, updated_at
        FROM projects
        ORDER BY normalized_name
        """
        rows = await self.postgres.fetch(query)
        return [Project(**row) for row in rows]

    async def get_project_by_name(self, name: str) -> Project | None:
        """Get a project by name."""
        normalized_name = normalize_name(name)
        query = """
        SELECT id, name, normalized_name, description, created_at, updated_at
        FROM projects
        WHERE normalized_name = $1
        """
        row = await self.postgres.fetchrow(query, normalized_name)
        if row is None:
            return None
        return Project(**row)

    async def create_project(self, project: Project) -> Project:
        """Create a new project."""
        query = """
        INSERT INTO projects (name, normalized_name, description)
        VALUES ($1, $2, $3)
        RETURNING id, name, normalized_name, description, created_at, updated_at
        """
        row = await self.postgres.fetchrow(
            query, project.name, project.normalized_name, project.description
        )
        if row is None:
            raise ValueError(PROJECT_CREATE_ERROR.substitute(name=project.name))
        return Project(**dict(row))

    async def update_project(self, project: Project) -> Project:
        """Update an existing project."""
        query = """
        UPDATE projects
        SET name = $2, description = $3, updated_at = NOW()
        WHERE id = $1
        RETURNING id, name, normalized_name, description, created_at, updated_at
        """
        row = await self.postgres.fetchrow(
            query, project.id, project.name, project.description
        )
        if row is None:
            raise ValueError(PROJECT_UPDATE_ERROR.substitute(name=project.name))
        return Project(**dict(row))

    async def delete_project(self, project_id: int) -> bool:
        """Delete a project."""
        query = """
        DELETE FROM projects
        WHERE id = $1
        """
        result = await self.postgres.execute(query, project_id)
        return "DELETE 1" in result

    async def search_projects(self, query: str) -> list[Project]:
        """Search for projects."""
        search_query = """
        SELECT id, name, normalized_name, description, created_at, updated_at
        FROM projects
        WHERE
            normalized_name LIKE $1 OR
            name ILIKE $1 OR
            description ILIKE $1
        ORDER BY normalized_name
        """
        pattern = f"%{query}%"
        rows = await self.postgres.fetch(search_query, pattern)
        return [Project(**row) for row in rows]
