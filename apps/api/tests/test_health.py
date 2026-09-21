from app.main import health


def test_health() -> None:
    assert health().model_dump() == {"status": "ok"}
