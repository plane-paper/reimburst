import asyncio

from app import receipts
from app.main import app
from shared.enums import ExtractionStatus, UserRole
from shared.models import Receipt, User
from starlette.requests import Request


class FakeStorage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def put(self, key: str, content: bytes) -> None:
        self.objects[key] = content

    async def get(self, key: str) -> bytes:
        return self.objects[key]


class FakeUpload:
    filename = "receipt.png"
    content_type = "image/png"

    async def read(self) -> bytes:
        return b"receipt bytes"


class FakeQueue:
    def __init__(self) -> None:
        self.jobs: list[tuple[str, tuple[object, ...]]] = []

    async def enqueue_job(self, function: str, *args: object) -> None:
        self.jobs.append((function, args))

    async def close(self) -> None:
        pass


class FakeScalarResult:
    def __iter__(self):
        return iter(())


class FakeExecuteResult:
    def all(self) -> list[tuple[object, ...]]:
        return []


class FakeSession:
    def __init__(self) -> None:
        self.owner = User(id=1, email="local@reimburst.test", role=UserRole.INDIVIDUAL)
        self.receipt: Receipt | None = None

    async def __aenter__(self) -> "FakeSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    async def scalar(self, _: object) -> User:
        return self.owner

    async def get(self, _: type[Receipt], __: int) -> Receipt | None:
        return self.receipt

    async def scalars(self, _: object) -> FakeScalarResult:
        return FakeScalarResult()

    async def execute(self, _: object) -> FakeExecuteResult:
        return FakeExecuteResult()

    def add(self, value: object) -> None:
        if isinstance(value, Receipt):
            value.id = 2
            value.extraction_status = ExtractionStatus.PENDING
            value.categorization_status = ExtractionStatus.PENDING
            self.receipt = value

    async def commit(self) -> None:
        pass

    async def refresh(self, _: object) -> None:
        pass


def test_upload_persists_pending_receipt_and_enqueues_extraction(monkeypatch) -> None:
    session = FakeSession()
    monkeypatch.setattr(receipts, "session_factory", lambda: lambda: session)
    storage = FakeStorage()
    queue = FakeQueue()
    app.state.object_storage = storage
    app.state.job_queue = queue
    try:
        async def run() -> None:
            request = Request({"type": "http", "app": app, "headers": []})
            image = FakeUpload()
            created = await receipts.create_receipt(request, image)
            assert created.extraction_status.value == "pending"
            assert created.image_key in storage.objects
            assert queue.jobs == [("extract_receipt", (created.id, "image/png"))]

            detail = await receipts.get_receipt(created.id)
            assert detail.model_dump() == {
                "id": created.id,
                "image_key": created.image_key,
                "extraction_status": created.extraction_status,
                "merchant": None,
                "total_cents": None,
                "tax_cents": None,
                "currency": None,
                "extraction_error": None,
                "categorization_status": ExtractionStatus.PENDING,
                "categorization_error": None,
                "line_items": [],
            }

        asyncio.run(run())
    finally:
        del app.state.object_storage
        del app.state.job_queue
