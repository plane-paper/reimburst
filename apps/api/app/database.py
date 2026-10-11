import os

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

_engine: AsyncEngine | None = None


def session_factory() -> async_sessionmaker[AsyncSession]:
    global _engine
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be configured before uploading receipts")
    if _engine is None:
        _engine = create_async_engine(database_url)
    return async_sessionmaker(_engine, expire_on_commit=False)


async def dispose_engine() -> None:
    """Release the process-wide database pool during application shutdown."""
    global _engine
    if _engine is not None:
        await _engine.dispose()
        _engine = None
