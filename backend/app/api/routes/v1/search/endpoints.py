from typing import Annotated, Any

from fastapi import APIRouter, Depends, Query, Request

from app.api.dependencies.services import get_project_service
from app.services.project_service import ProjectService

router = APIRouter()


@router.get("")
async def search_packages(
    request: Request,
    project_service: Annotated[ProjectService, Depends(get_project_service)],
    q: Annotated[str, Query(description="Search query")],
) -> dict[str, Any]:
    """
    Search for packages by name or description.

    This endpoint allows searching for packages in the repository. It's similar
    to PyPI's search functionality but simplified.

    Args:
        q: The search query

    Returns:
        JSON response with search results

    """
    # Search for projects
    projects = await project_service.search_projects(q)

    # Build response
    results = []
    for project in projects:
        # Get the latest release for each project
        releases = await project_service.get_project_releases(project.name)
        latest_release = None
        if releases:
            # Simple sorting by upload time; in a real implementation, you'd use proper version comparison
            latest_release = sorted(
                releases, key=lambda r: r.uploaded_at, reverse=True
            )[0]

        # Build project result with explicit typing
        result: dict[str, str | list[str] | dict[str, str] | None] = {
            "name": project.name,
            "version": latest_release.version if latest_release else "",
            "description": latest_release.description
            if latest_release and latest_release.description
            else project.description,
            "summary": latest_release.summary
            if latest_release and latest_release.summary
            else None,
        }

        # Add extra metadata if available
        if latest_release:
            if latest_release.author:
                result["author"] = latest_release.author
            if latest_release.author_email:
                result["author_email"] = latest_release.author_email
            if latest_release.home_page:
                result["home_page"] = latest_release.home_page
            if latest_release.license:
                result["license"] = latest_release.license
            if latest_release.requires_python:
                result["requires_python"] = latest_release.requires_python
            if latest_release.classifiers:
                # Convert to proper type to avoid mypy errors
                classifier_list: list[str] = []
                if isinstance(latest_release.classifiers, list):
                    classifier_list = latest_release.classifiers
                result["classifiers"] = classifier_list

        results.append(result)

    return {"data": {"count": len(results), "results": results}}


@router.get("/advanced")
async def advanced_search(
    request: Request,
    project_service: Annotated[ProjectService, Depends(get_project_service)],
    name: Annotated[str | None, Query(description="Package name")] = None,
    description: Annotated[
        str | None, Query(description="Description contains")
    ] = None,
    author: Annotated[str | None, Query(description="Author name")] = None,
    license: Annotated[str | None, Query(description="License type")] = None,
    classifier: Annotated[str | None, Query(description="Classifier")] = None,
    requires_python: Annotated[str | None, Query(description="Python version")] = None,
) -> dict[str, Any]:
    """
    Advanced search for packages with multiple criteria.

    This endpoint allows searching for packages by multiple criteria such as name,
    description, author, license, classifier, and Python version requirement.

    Returns:
        JSON response with search results matching all provided criteria

    """
    # First get all projects (we'll filter in memory for simplicity)
    # In a real implementation, you'd use database queries for filtering
    all_projects = await project_service.get_all_projects()

    results = []
    for project in all_projects:
        # Skip immediately if name doesn't match
        if name and name.lower() not in project.name.lower():
            continue

        # Skip if description doesn't match
        if description and (
            not project.description
            or description.lower() not in project.description.lower()
        ):
            continue

        # Get all releases for the project to check other criteria
        releases = await project_service.get_project_releases(project.name)

        # Skip if no releases
        if not releases:
            continue

        # Get the latest release
        latest_release = sorted(releases, key=lambda r: r.uploaded_at, reverse=True)[0]

        # Check release-specific criteria
        if author and (
            not latest_release.author
            or author.lower() not in latest_release.author.lower()
        ):
            continue

        if license and (
            not latest_release.license
            or license.lower() not in latest_release.license.lower()
        ):
            continue

        if classifier and (
            not latest_release.classifiers
            or not any(
                classifier.lower() in c.lower() for c in latest_release.classifiers
            )
        ):
            continue

        if requires_python and (
            not latest_release.requires_python
            or requires_python not in latest_release.requires_python
        ):
            continue

        # Build project result
        result = {
            "name": project.name,
            "version": latest_release.version,
            "description": latest_release.description
            if latest_release.description
            else project.description,
            "summary": latest_release.summary,
            "author": latest_release.author,
            "author_email": latest_release.author_email,
            "home_page": latest_release.home_page,
            "license": latest_release.license,
            "requires_python": latest_release.requires_python,
            "classifiers": latest_release.classifiers,
        }

        # Filter out None values
        result = {k: v for k, v in result.items() if v is not None}

        results.append(result)

    return {"data": {"count": len(results), "results": results}}
