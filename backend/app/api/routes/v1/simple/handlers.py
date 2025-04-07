import logging
import re
from urllib.parse import urlparse

from app.api.routes.v1.simple.models import (
    PackageFile,
    ProjectDetail,
    ProjectList,
    ProjectReference,
)
from app.core.clients.postgres import PostgresClient
from app.core.clients.s3 import S3Client
from app.core.clients.valkey import ValkeyClient

logger = logging.getLogger(__name__)


def normalize_name(name: str) -> str:
    """
    Normalize a package name according to PEP 503.

    This replaces runs of non-alphanumeric characters with a single '-'
    and lowercase the name.
    """
    return re.sub(r"[-_.]+", "-", name).lower()


async def get_all_projects(
    postgres: PostgresClient, valkey: ValkeyClient | None = None
) -> ProjectList:
    """Get all projects for the root `/simple/` endpoint."""
    # In a real implementation, we would fetch projects from the database
    # For now, return a simple mock response
    projects = [
        ProjectReference(name="example-package"),
        ProjectReference(name="another-package"),
    ]

    return ProjectList(projects=projects)


async def get_project_detail(
    project_name: str,
    postgres: PostgresClient,
    s3: S3Client,
    valkey: ValkeyClient | None = None,
) -> ProjectDetail:
    """Get project details and files for the `/simple/{project_name}/` endpoint."""
    # Normalize project name as per PEP 503
    normalized_name = normalize_name(project_name)

    # In a real implementation, we would fetch project details from the database
    # and file information from S3
    # For now, return a simple mock response
    files = [
        PackageFile(
            filename=f"{normalized_name}-1.0.tar.gz",
            url=f"/files/{normalized_name}-1.0.tar.gz",
            hashes={"sha256": "abcdef123456"},
            requires_python=">=3.7",
            yanked="Had a vulnerability",
            gpg_sig=True,
            size=123456,
        ),
        PackageFile(
            filename=f"{normalized_name}-1.0-py3-none-any.whl",
            url=f"/files/{normalized_name}-1.0-py3-none-any.whl",
            hashes={"sha256": "fedcba654321"},
            requires_python=">=3.7",
            core_metadata={"sha256": "987654321abc"},
            provenance=f"https://example.com/files/{normalized_name}-1.0-py3-none-any.whl.provenance",
            size=1337,
        ),
    ]

    return ProjectDetail(name=normalized_name, files=files, versions=["1.0"])


async def check_project_exists(
    project_name: str, postgres: PostgresClient, valkey: ValkeyClient | None = None
) -> bool:
    """Verify if a project exists before fetching its details."""
    # In a real implementation, we would check the database
    # For now, return True for the example packages
    normalized_name = normalize_name(project_name)
    return normalized_name in ["example-package", "another-package"]


def validate_provenance_url(url: str) -> bool:
    """
    Validate provenance URL per PEP 740 requirements.

    Ensures URL is fully qualified and uses HTTPS (except localhost).
    """
    if not url:
        return False

    # Check if the URL is fully qualified
    if not url.startswith(("https://", "http://")):
        logger.warning(f"Rejecting provenance URL: not fully qualified: {url}")
        return False

    # Parse the URL
    parsed_url = urlparse(url)

    # Check for secure protocol
    if parsed_url.scheme != "https" and parsed_url.netloc != "localhost":
        logger.warning(f"Rejecting provenance URL: not using HTTPS: {url}")
        return False

    return True


def validate_requires_python(requires_python: str) -> bool:
    """
    Validate requires-python string format per PEP 440.

    Handles version specifiers, ranges, exclusions, and wildcards.
    """
    if not requires_python:
        return True  # Empty is valid (means no constraints)

    # Special case for '*' which means any version
    if requires_python.strip() == "*":
        return True

    # Pattern for valid version specifiers - handles common cases
    # Covers most of the common version specifier formats
    PATTERN = r"^\s*(?:(?:<=|>=|<|>|!=|==|~=)\s*[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?(?:\.dev[0-9]+)?(?:\s*,\s*)?)+\s*$"

    # Special case: Just a version without operator means ">="
    # For example, "3.6" is equivalent to ">=3.6"
    VERSION_ONLY_PATTERN = r"^\s*[0-9]+(?:\.[0-9]+)*(?:(?:a|b|rc)[0-9]+)?(?:\.post[0-9]+)?(?:\.dev[0-9]+)?\s*$"

    # Special case for exclusion markers - more complex syntax that's valid but not captured by the simple regex
    # These are patterns like "!=3.0.*, !=3.1.*, !=3.2.*, !=3.3.*"
    EXCLUSION_PATTERN = r"^\s*(?:!=\s*[0-9]+(?:\.[0-9]+)*\.\*\s*,?\s*)+$"

    if (
        re.match(PATTERN, requires_python)
        or re.match(VERSION_ONLY_PATTERN, requires_python)
        or re.match(EXCLUSION_PATTERN, requires_python)
    ):
        return True

    logger.warning(f"Invalid requires-python format: {requires_python}")
    return False


def escape_html(text: str) -> str:
    """Escape HTML special characters for safe output in templates."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#39;")
    )
