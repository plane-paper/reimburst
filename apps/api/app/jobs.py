"""Queue access shared by endpoints that start asynchronous work."""

import os
from typing import Protocol

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import HTTPException, Request


class JobQueue(Protocol):
    async def enqueue_job(self, function: str, *args: object) -> object: ...

    async def close(self) -> None: ...


async def queue_for(request: Request, unavailable_detail: str) -> tuple[JobQueue, bool]:
    """Return the app queue, or a short-lived Redis queue when not injected."""
    queue: JobQueue | None = getattr(request.app.state, "job_queue", None)
    if queue is not None:
        return queue, False
    redis_url = os.environ.get("REDIS_URL")
    if not redis_url:
        raise HTTPException(status_code=503, detail=unavailable_detail)
    return await create_pool(RedisSettings.from_dsn(redis_url)), True


async def enqueue(request: Request, function: str, *args: object, unavailable_detail: str) -> None:
    queue, close_queue = await queue_for(request, unavailable_detail)
    try:
        await queue.enqueue_job(function, *args)
    finally:
        if close_queue:
            await queue.close()
