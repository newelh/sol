import hashlib
from typing import Any

from botocore.exceptions import ClientError

from app.core.clients.s3 import S3Client
from app.repos.interfaces import StorageRepository


class S3StorageFileNotFoundError(FileNotFoundError):
    """Raised when a file is not found in S3 storage."""

    def __init__(self, path: str) -> None:
        super().__init__(f"File not found: {path}")


class S3StorageRepository(StorageRepository):
    """S3 implementation of the storage repository."""

    def __init__(self, s3: S3Client):
        self.s3 = s3

    async def get_file(self, path: str) -> bytes:
        """Get a file from storage."""
        bucket = self.s3.config.default_bucket
        try:
            return await self.s3.download_file(bucket, path)
        except ClientError as e:
            if e.response["Error"]["Code"] == "NoSuchKey":
                raise S3StorageFileNotFoundError(path) from e
            raise

    async def put_file(self, path: str, content: bytes, content_type: str) -> bool:
        """Store a file in storage."""
        bucket = self.s3.config.default_bucket
        # Calculate hashes for metadata
        # Use MD5 only for backwards compatibility with S3 ETag, not for security
        md5_hash = hashlib.md5(content, usedforsecurity=False).hexdigest()
        sha256_hash = hashlib.sha256(content).hexdigest()

        # Add metadata to the file
        metadata = {
            "sha256": sha256_hash,
            "md5": md5_hash,
            "content-type": content_type,
        }

        try:
            # Upload the file
            await self.s3.upload_file(
                bucket=bucket,
                key=path,
                data=content,
                content_type=content_type,
                metadata=metadata,
            )
        except Exception:
            return False
        else:
            return True

    async def delete_file(self, path: str) -> bool:
        """Delete a file from storage."""
        bucket = self.s3.config.default_bucket
        try:
            await self.s3.delete_object(bucket, path)
        except Exception:
            return False
        else:
            return True

    async def file_exists(self, path: str) -> bool:
        """Check if a file exists in storage."""
        bucket = self.s3.config.default_bucket
        return await self.s3.object_exists(bucket, path)

    async def get_file_metadata(self, path: str) -> dict[str, Any]:
        """Get metadata for a file in storage."""
        bucket = self.s3.config.default_bucket
        try:
            async with self.s3._get_client() as client:
                response = await client.head_object(Bucket=bucket, Key=path)

                # Extract metadata
                result = {
                    "size": response.get("ContentLength", 0),
                    "last_modified": response.get("LastModified"),
                    "content_type": response.get("ContentType"),
                    "etag": response.get("ETag", "").strip('"'),
                }

                # Add any custom metadata
                if "Metadata" in response:
                    for key, value in response["Metadata"].items():
                        result[key] = value

                return result
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                raise S3StorageFileNotFoundError(path) from e
            raise
