"""Object storage boundary. The filesystem adapter is only for local development/tests."""

import asyncio
import os
from pathlib import Path
from typing import Protocol


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
