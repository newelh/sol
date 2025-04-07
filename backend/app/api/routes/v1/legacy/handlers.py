import hashlib
import logging
import re

logger = logging.getLogger(__name__)


def is_valid_package_name(name: str) -> bool:
    """Validate package name according to PEP 508 naming requirements."""
    pattern = r"^([A-Za-z0-9]|[A-Za-z0-9][A-Za-z0-9._-]*[A-Za-z0-9])$"
    return bool(re.match(pattern, name))


def is_valid_version(version: str) -> bool:
    """Validate version string using simplified PEP 440 rules."""
    # This is a simplified pattern, not a full PEP 440 validator
    pattern = r"^([0-9]+)(\.[0-9]+)*([a-zA-Z0-9.-]*)$"
    return bool(re.match(pattern, version))


def get_file_hashes(content: bytes) -> dict[str, str]:
    """Calculate hashes for a file using secure algorithms (SHA256 and BLAKE2)."""
    # Use MD5 only for backwards compatibility, marked as not for security purposes
    md5_digest = hashlib.md5(content, usedforsecurity=False).hexdigest()
    sha256_digest = hashlib.sha256(content).hexdigest()

    # For Blake2, if available
    blake2_digest = ""
    if hasattr(hashlib, "blake2b"):
        blake2_digest = hashlib.blake2b(content, digest_size=32).hexdigest()

    return {"md5": md5_digest, "sha256": sha256_digest, "blake2b_256": blake2_digest}


def determine_package_type(filename: str) -> tuple[str, str]:
    """Extract package type and Python version from filename."""
    packagetype = "sdist"
    python_version = "source"

    if filename.endswith(".whl"):
        packagetype = "bdist_wheel"
        # Parse Python version from wheel filename
        # Example: package-1.0-py3-none-any.whl
        parts = filename.split("-")
        if len(parts) >= 3:
            python_version = parts[-3]
    elif filename.endswith(".egg"):
        packagetype = "bdist_egg"
        # Try to extract Python version
        match = re.search(r"py([0-9\.]+)", filename)
        if match:
            python_version = f"py{match.group(1)}"

    return packagetype, python_version
