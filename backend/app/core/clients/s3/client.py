import io
import logging
import traceback
from typing import Any

import aiobotocore.session
from botocore.exceptions import ClientError

from app.core.clients.base import BaseClient
from app.core.config import S3Settings

logger = logging.getLogger(__name__)


class MissingBucketError(ValueError):
    """Raised when bucket name is not provided and no default bucket is set."""

    def __init__(self) -> None:
        super().__init__("Bucket name must be provided or set as default_bucket")


class S3Client(BaseClient[S3Settings]):
    """Client for interacting with S3-compatible object storage."""

    def __init__(self, config: S3Settings) -> None:
        super().__init__(config)
        self._session = aiobotocore.session.AioSession()
        self._client = None
        self._initialized: bool = False

    async def initialize(self) -> None:
        """Initialize the S3 client."""
        if self._initialized:
            return

        logger.info(f"Initializing S3 client with endpoint {self.config.endpoint_url}")
        try:
            # Just validate the config, don't create the client yet
            # We'll create a new client for each operation
            self._initialized = True
            logger.info("S3 client initialization successful")
        except Exception:
            logger.exception(
                f"Failed to initialize S3 client with endpoint={self.config.endpoint_url}, region={self.config.region_name}"
            )
            logger.debug(traceback.format_exc())
            raise

    def _get_client(self) -> Any:
        """Get a new S3 client instance."""
        return self._session.create_client(
            "s3",
            region_name=self.config.region_name,
            endpoint_url=self.config.endpoint_url,
            aws_access_key_id=self.config.access_key_id,
            aws_secret_access_key=self.config.secret_access_key,
            use_ssl=self.config.use_ssl,
            verify=self.config.verify,
        )

    async def cleanup(self) -> None:
        """Close the S3 client."""
        # Nothing to clean up when using the context manager approach
        self._initialized = False

    async def get_metrics(self) -> dict[str, Any]:
        """Get client metrics (limited for S3)."""
        return {
            "status": "initialized" if self._initialized else "not_initialized",
            "endpoint": self.config.endpoint_url,
            "region": self.config.region_name,
        }

    async def health_check(self) -> bool:
        """Check connectivity by listing buckets."""
        if not self._initialized:
            logger.warning("S3 health check failed: client not initialized")
            return False

        try:
            logger.info("Performing S3 health check")
            async with self._get_client() as client:
                result = await client.list_buckets()
                buckets = [b["Name"] for b in result.get("Buckets", [])]
                logger.info(f"S3 health check successful. Buckets: {buckets}")

                # Also check if the default bucket exists
                if (
                    self.config.default_bucket
                    and self.config.default_bucket not in buckets
                ):
                    logger.warning(
                        f"Default bucket '{self.config.default_bucket}' not found in available buckets"
                    )
        except Exception:
            logger.exception("S3 health check failed")
            logger.debug(traceback.format_exc())
            return False
        else:
            return True

    async def upload_file(
        self,
        bucket: str | None,
        key: str,
        data: bytes | str | io.IOBase,
        content_type: str | None = None,
        metadata: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """
        Upload a file to S3.

        Args:
            bucket: The bucket name (uses default_bucket if None)
            key: The object key
            data: The file data as bytes, string, or file-like object
            content_type: The content type of the file
            metadata: Optional metadata to attach to the object

        Returns:
            Response metadata from S3

        """
        if not self._initialized:
            await self.initialize()

        bucket_name = bucket or self.config.default_bucket
        if not bucket_name:
            raise MissingBucketError()

        # Prepare the data for upload
        if isinstance(data, str):
            body: bytes | io.IOBase = data.encode("utf-8")
        elif isinstance(data, io.IOBase):
            body = data
        else:
            # Assume bytes
            body = data

        # Prepare upload parameters
        params: dict[str, Any] = {"Bucket": bucket_name, "Key": key, "Body": body}

        if content_type:
            params["ContentType"] = content_type

        if metadata:
            # Ensure metadata is a dict of strings as required by S3
            str_metadata: dict[str, str] = {str(k): str(v) for k, v in metadata.items()}
            params["Metadata"] = str_metadata

        async with self._get_client() as client:
            response = await client.put_object(**params)
            return response

    async def download_file(self, bucket: str | None, key: str) -> bytes:
        """
        Download a file from S3.

        Args:
            bucket: The bucket name (uses default_bucket if None)
            key: The object key

        Returns:
            The file contents as bytes

        """
        if not self._initialized:
            await self.initialize()

        bucket_name = bucket or self.config.default_bucket
        if not bucket_name:
            raise MissingBucketError()

        async with self._get_client() as client:
            response = await client.get_object(Bucket=bucket_name, Key=key)
            async with response["Body"] as stream:
                return await stream.read()

    async def list_objects(
        self, bucket: str | None, prefix: str = "", max_keys: int = 1000
    ) -> list[dict[str, Any]]:
        """
        List objects in a bucket with a given prefix.

        Args:
            bucket: The bucket name (uses default_bucket if None)
            prefix: Key prefix to filter results
            max_keys: Maximum number of keys to return

        Returns:
            List of object information

        """
        if not self._initialized:
            await self.initialize()

        bucket_name = bucket or self.config.default_bucket
        if not bucket_name:
            raise MissingBucketError()

        objects = []
        async with self._get_client() as client:
            paginator = client.get_paginator("list_objects_v2")
            async for page in paginator.paginate(
                Bucket=bucket_name, Prefix=prefix, MaxKeys=max_keys
            ):
                if "Contents" in page:
                    objects.extend(page["Contents"])

        return objects

    async def delete_object(self, bucket: str | None, key: str) -> dict[str, Any]:
        """
        Delete an object from S3.

        Args:
            bucket: The bucket name (uses default_bucket if None)
            key: The object key

        Returns:
            Response metadata from S3

        """
        if not self._initialized:
            await self.initialize()

        bucket_name = bucket or self.config.default_bucket
        if not bucket_name:
            raise MissingBucketError()

        async with self._get_client() as client:
            response = await client.delete_object(Bucket=bucket_name, Key=key)
            return response

    async def object_exists(self, bucket: str | None, key: str) -> bool:
        """
        Check if an object exists in S3.

        Args:
            bucket: The bucket name (uses default_bucket if None)
            key: The object key

        Returns:
            True if the object exists, False otherwise

        """
        if not self._initialized:
            await self.initialize()

        bucket_name = bucket or self.config.default_bucket
        if not bucket_name:
            raise MissingBucketError()

        try:
            async with self._get_client() as client:
                await client.head_object(Bucket=bucket_name, Key=key)
                return True
        except ClientError as e:
            if e.response["Error"]["Code"] == "404":
                return False
            raise
