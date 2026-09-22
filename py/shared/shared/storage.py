"""Object storage adapters shared by the API and extraction worker."""

import asyncio
import os
from pathlib import Path
from typing import Any, Protocol

import boto3  # type: ignore[import-untyped]


class ObjectStorage(Protocol):
    async def put(self, key: str, content: bytes) -> None: ...

    async def get(self, key: str) -> bytes: ...


class LocalObjectStorage:
    def __init__(self, root: Path) -> None:
        self.root = root

    @classmethod
    def from_environment(cls) -> "LocalObjectStorage":
        return cls(Path(os.environ.get("LOCAL_STORAGE_PATH", "/tmp/reimburst-uploads")))

    async def put(self, key: str, content: bytes) -> None:
        path = self.root / key
        await asyncio.to_thread(path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(path.write_bytes, content)

    async def get(self, key: str) -> bytes:
        return await asyncio.to_thread((self.root / key).read_bytes)


class S3ObjectStorage:
    """S3-compatible storage; credentials use boto3's standard provider chain."""

    def __init__(self, bucket: str, client: Any) -> None:
        self.bucket = bucket
        self.client = client

    @classmethod
    def from_environment(cls) -> "S3ObjectStorage":
        bucket = os.environ.get("S3_BUCKET")
        if not bucket:
            raise RuntimeError("S3_BUCKET must be configured when STORAGE_BACKEND=s3")
        client_kwargs: dict[str, str] = {}
        endpoint_url = os.environ.get("S3_ENDPOINT_URL")
        region_name = os.environ.get("AWS_REGION")
        if endpoint_url:
            client_kwargs["endpoint_url"] = endpoint_url
        if region_name:
            client_kwargs["region_name"] = region_name
        return cls(bucket=bucket, client=boto3.client("s3", **client_kwargs))

    async def put(self, key: str, content: bytes) -> None:
        await asyncio.to_thread(self.client.put_object, Bucket=self.bucket, Key=key, Body=content)

    async def get(self, key: str) -> bytes:
        response = await asyncio.to_thread(self.client.get_object, Bucket=self.bucket, Key=key)
        return await asyncio.to_thread(response["Body"].read)


def object_storage_from_environment() -> ObjectStorage:
    """Build the configured storage adapter for both API and worker processes.

    Local storage is deliberately the default for development and tests. Deployment
    environments must set ``STORAGE_BACKEND=s3`` and provide ``S3_BUCKET``.
    """

    backend = os.environ.get("STORAGE_BACKEND", "local").lower()
    if backend == "local":
        return LocalObjectStorage.from_environment()
    if backend == "s3":
        return S3ObjectStorage.from_environment()
    raise RuntimeError("STORAGE_BACKEND must be either 'local' or 's3'")
