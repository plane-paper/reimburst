import asyncio

import pytest
from app import receipts
from fastapi import HTTPException
from shared.enums import ExtractionStatus
from shared.models import Category, LineItem, Receipt


class ConfirmationScalars:
    def __init__(self, values: list[object]) -> None:
        self.values = values

    def __iter__(self):  # type: ignore[no-untyped-def]
        return iter(self.values)


class ConfirmationExecuteResult:
    def __init__(self, rows: list[tuple[LineItem, str]]) -> None:
        self.rows = rows

    def all(self) -> list[tuple[LineItem, str]]:
        return self.rows


class ConfirmationSession:
    def __init__(self) -> None:
        self.receipt = Receipt(
            id=2,
            owner_id=1,
            image_key="receipts/example.png",
            extraction_status=ExtractionStatus.SUCCEEDED,
            categorization_status=ExtractionStatus.SUCCEEDED,
            total_cents=1200,
            currency="USD",
        )
        self.item = LineItem(
            id=3,
            receipt_id=2,
            description="Lunch",
            amount_cents=1200,
            category_id=1,
            needs_category_review=True,
        )
        self.category = Category(id=1, name="food")
        self.scalar_calls = 0
        self.committed = False

    async def __aenter__(self) -> "ConfirmationSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    async def get(self, _: type[Receipt], __: int) -> Receipt:
        return self.receipt

    async def scalars(self, _: object) -> ConfirmationScalars:
        self.scalar_calls += 1
        return ConfirmationScalars([self.item] if self.scalar_calls == 1 else [self.category])

    async def execute(self, _: object) -> ConfirmationExecuteResult:
        return ConfirmationExecuteResult([(self.item, self.category.name)])

    async def commit(self) -> None:
        self.committed = True


def test_confirmation_requires_explicit_mismatch_acknowledgement(monkeypatch) -> None:
    session = ConfirmationSession()
    monkeypatch.setattr(receipts, "session_factory", lambda: lambda: session)
    confirmation = receipts.ReceiptConfirmation(
        line_items=[
            receipts.ConfirmedLineItem(
                id=3, description="Lunch", amount_cents=1100, category="food"
            )
        ]
    )

    async def run() -> None:
        with pytest.raises(HTTPException, match="explicitly acknowledge") as error:
            await receipts.confirm_receipt(2, confirmation)
        assert error.value.status_code == 409
        assert not session.committed

    asyncio.run(run())


def test_confirmation_persists_reviewed_items_after_acknowledgement(monkeypatch) -> None:
    session = ConfirmationSession()
    monkeypatch.setattr(receipts, "session_factory", lambda: lambda: session)
    confirmation = receipts.ReceiptConfirmation(
        line_items=[
            receipts.ConfirmedLineItem(
                id=3, description="Team lunch", amount_cents=1100, category="food"
            )
        ],
        acknowledge_reconciliation_mismatch=True,
    )

    async def run() -> None:
        result = await receipts.confirm_receipt(2, confirmation)
        assert session.committed
        assert session.item.description == "Team lunch"
        assert session.item.amount_cents == 1100
        assert not session.item.needs_category_review
        assert result.reconciliation.difference_cents == -100
        assert result.confirmed_at is not None

    asyncio.run(run())
