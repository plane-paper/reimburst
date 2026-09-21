import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


def session_factory() -> async_sessionmaker[AsyncSession]:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL must be configured before uploading receipts")
    engine = create_async_engine(database_url)
    return async_sessionmaker(engine, expire_on_commit=False)
