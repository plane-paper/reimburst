import asyncio

from app import database


def test_session_factory_reuses_one_engine_until_shutdown(monkeypatch) -> None:
    created: list[object] = []

    class Engine:
        async def dispose(self) -> None:
            pass

    def create_engine(_: str) -> Engine:
        engine = Engine()
        created.append(engine)
        return engine

    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://example.test/reimburst")
    monkeypatch.setattr(database, "create_async_engine", create_engine)
    database._engine = None
    try:
        database.session_factory()
        database.session_factory()
        assert len(created) == 1
    finally:
        asyncio.run(database.dispose_engine())
