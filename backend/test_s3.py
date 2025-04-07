#!/usr/bin/env python3
"""
Test S3 connection script.
"""

import asyncio
import logging
import os

import aiobotocore.session
import boto3

# Configure logging
logging.basicConfig(
    level=logging.DEBUG, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

logger = logging.getLogger("test_s3")

# S3 settings
S3_ENDPOINT_URL = os.environ.get("S3_ENDPOINT_URL", "http://localhost:9000")
S3_REGION_NAME = os.environ.get("S3_REGION_NAME", "us-east-1")
S3_ACCESS_KEY_ID = os.environ.get("S3_ACCESS_KEY_ID", "minioadmin")
S3_SECRET_ACCESS_KEY = os.environ.get("S3_SECRET_ACCESS_KEY", "minioadmin")
S3_DEFAULT_BUCKET = os.environ.get("S3_DEFAULT_BUCKET", "pypi")
S3_USE_SSL = os.environ.get("S3_USE_SSL", "false").lower() == "true"
S3_VERIFY = os.environ.get("S3_VERIFY", "false").lower() == "true"


async def test_aiobotocore():
    """Test S3 connection using aiobotocore (async)."""
    logger.info(f"Testing aiobotocore S3 connection to {S3_ENDPOINT_URL}")
    logger.info(
        f"Settings: region={S3_REGION_NAME}, bucket={S3_DEFAULT_BUCKET}, use_ssl={S3_USE_SSL}, verify={S3_VERIFY}"
    )

    session = aiobotocore.session.AioSession()

    try:
        async with session.create_client(
            "s3",
            region_name=S3_REGION_NAME,
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=S3_ACCESS_KEY_ID,
            aws_secret_access_key=S3_SECRET_ACCESS_KEY,
            use_ssl=S3_USE_SSL,
            verify=S3_VERIFY,
        ) as client:
            # List buckets
            logger.info("Listing buckets...")
            resp = await client.list_buckets()
            buckets = [bucket["Name"] for bucket in resp["Buckets"]]
            logger.info(f"Found buckets: {buckets}")

            # List objects in default bucket
            if S3_DEFAULT_BUCKET in buckets:
                logger.info(f"Listing objects in bucket {S3_DEFAULT_BUCKET}...")
                resp = await client.list_objects_v2(Bucket=S3_DEFAULT_BUCKET)
                if "Contents" in resp:
                    objects = [obj["Key"] for obj in resp["Contents"]]
                    logger.info(f"Found objects: {objects}")
                else:
                    logger.info("No objects found in bucket.")

                # Try to upload a test file
                logger.info("Uploading test file...")
                await client.put_object(
                    Bucket=S3_DEFAULT_BUCKET, Key="test.txt", Body=b"Hello, S3!"
                )
                logger.info("Upload successful!")

                # Download the test file
                logger.info("Downloading test file...")
                resp = await client.get_object(Bucket=S3_DEFAULT_BUCKET, Key="test.txt")
                async with resp["Body"] as stream:
                    data = await stream.read()
                logger.info(f"Downloaded content: {data.decode('utf-8')}")

                # Delete the test file
                logger.info("Deleting test file...")
                await client.delete_object(Bucket=S3_DEFAULT_BUCKET, Key="test.txt")
                logger.info("Delete successful!")
            else:
                logger.warning(
                    f"Bucket {S3_DEFAULT_BUCKET} not found, can't test object operations"
                )

            logger.info("S3 aiobotocore test completed successfully!")
    except Exception as e:
        logger.error(f"S3 aiobotocore test failed: {e!s}", exc_info=True)


def test_boto3():
    """Test S3 connection using boto3 (sync)."""
    logger.info(f"Testing boto3 S3 connection to {S3_ENDPOINT_URL}")
    logger.info(
        f"Settings: region={S3_REGION_NAME}, bucket={S3_DEFAULT_BUCKET}, use_ssl={S3_USE_SSL}, verify={S3_VERIFY}"
    )

    try:
        s3 = boto3.client(
            "s3",
            region_name=S3_REGION_NAME,
            endpoint_url=S3_ENDPOINT_URL,
            aws_access_key_id=S3_ACCESS_KEY_ID,
            aws_secret_access_key=S3_SECRET_ACCESS_KEY,
            use_ssl=S3_USE_SSL,
            verify=S3_VERIFY,
        )

        # List buckets
        logger.info("Listing buckets...")
        resp = s3.list_buckets()
        buckets = [bucket["Name"] for bucket in resp["Buckets"]]
        logger.info(f"Found buckets: {buckets}")

        # List objects in default bucket
        if S3_DEFAULT_BUCKET in buckets:
            logger.info(f"Listing objects in bucket {S3_DEFAULT_BUCKET}...")
            resp = s3.list_objects_v2(Bucket=S3_DEFAULT_BUCKET)
            if "Contents" in resp:
                objects = [obj["Key"] for obj in resp["Contents"]]
                logger.info(f"Found objects: {objects}")
            else:
                logger.info("No objects found in bucket.")

            # Try to upload a test file
            logger.info("Uploading test file...")
            s3.put_object(Bucket=S3_DEFAULT_BUCKET, Key="test.txt", Body=b"Hello, S3!")
            logger.info("Upload successful!")

            # Download the test file
            logger.info("Downloading test file...")
            resp = s3.get_object(Bucket=S3_DEFAULT_BUCKET, Key="test.txt")
            data = resp["Body"].read()
            logger.info(f"Downloaded content: {data.decode('utf-8')}")

            # Delete the test file
            logger.info("Deleting test file...")
            s3.delete_object(Bucket=S3_DEFAULT_BUCKET, Key="test.txt")
            logger.info("Delete successful!")
        else:
            logger.warning(
                f"Bucket {S3_DEFAULT_BUCKET} not found, can't test object operations"
            )

        logger.info("S3 boto3 test completed successfully!")
    except Exception as e:
        logger.error(f"S3 boto3 test failed: {e!s}", exc_info=True)


if __name__ == "__main__":
    # Run sync test
    logger.info("=== Starting boto3 (sync) test ===")
    test_boto3()

    # Run async test
    logger.info("\n=== Starting aiobotocore (async) test ===")
    asyncio.run(test_aiobotocore())
