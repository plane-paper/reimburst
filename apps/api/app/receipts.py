import mimetypes
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel, Field, model_validator
from shared.enums import ExtractionStatus
from shared.models import Category, LineItem, Receipt
from shared.storage import ObjectStorage, object_storage_from_environment
from sqlalchemy import select

from app.database import session_factory
from app.jobs import enqueue
from app.ownership import development_owner_id

router = APIRouter(prefix="/receipts", tags=["receipts"])


class ReceiptCreated(BaseModel):
    id: int
    image_key: str
    extraction_status: ExtractionStatus


class LineItemDetail(BaseModel):
    id: int
    description: str
    amount_cents: int
    category: str | None
    needs_category_review: bool


class ReconciliationDetail(BaseModel):
    line_items_total_cents: int
    receipt_total_cents: int | None
    difference_cents: int | None
    matches: bool


class ReceiptDetail(ReceiptCreated):
    merchant: str | None
    total_cents: int | None
    tax_cents: int | None
    currency: str | None = None
    extraction_error: str | None
    categorization_status: ExtractionStatus
    categorization_error: str | None
    line_items: list[LineItemDetail]
    reconciliation: ReconciliationDetail
    confirmed_at: datetime | None


def object_storage(request: Request) -> ObjectStorage:
    storage: ObjectStorage | None = getattr(request.app.state, "object_storage", None)
    return storage if storage is not None else object_storage_from_environment()


@router.post("", response_model=ReceiptCreated, status_code=status.HTTP_202_ACCEPTED)
async def create_receipt(
    request: Request,
    image: Annotated[UploadFile, File(description="Receipt image to extract")],
) -> ReceiptCreated:
    content_type = image.content_type or mimetypes.guess_type(image.filename or "")[0]
    if content_type not in {"image/jpeg", "image/png", "image/webp"}:
        raise HTTPException(status_code=415, detail="Upload a JPEG, PNG, or WebP receipt image")

    content = await image.read()
    if not content:
        raise HTTPException(status_code=422, detail="Receipt image is empty")
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Receipt image must be 10 MB or smaller")

    suffix = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp"}[content_type]
    image_key = f"receipts/{uuid.uuid4()}{suffix}"
    await object_storage(request).put(image_key, content)

    owner_id = await development_owner_id()
    async with session_factory()() as session:
        receipt = Receipt(owner_id=owner_id, image_key=image_key)
        session.add(receipt)
        await session.commit()
        await session.refresh(receipt)

    await enqueue(
        request,
        "extract_receipt",
        receipt.id,
        content_type,
        unavailable_detail="Receipt processing is temporarily unavailable",
    )
    return ReceiptCreated(
        id=receipt.id, image_key=receipt.image_key, extraction_status=receipt.extraction_status
    )


class CategoryDetail(BaseModel):
    id: int
    name: str


@router.get("/taxonomy", response_model=list[CategoryDetail])
async def get_taxonomy() -> list[CategoryDetail]:
    """The active global taxonomy. Organization scoping is added with P4/P5 auth."""
    async with session_factory()() as session:
        categories = list(
            await session.scalars(
                select(Category).where(Category.org_id.is_(None)).order_by(Category.id)
            )
        )
    return [CategoryDetail(id=category.id, name=category.name) for category in categories]


def reconciliation_for(receipt: Receipt, line_items: list[LineItem]) -> ReconciliationDetail:
    line_items_total_cents = sum(item.amount_cents for item in line_items)
    difference_cents = (
        line_items_total_cents - receipt.total_cents if receipt.total_cents is not None else None
    )
    return ReconciliationDetail(
        line_items_total_cents=line_items_total_cents,
        receipt_total_cents=receipt.total_cents,
        difference_cents=difference_cents,
        matches=difference_cents == 0,
    )


def receipt_detail(receipt: Receipt, item_rows: list[tuple[LineItem, str | None]]) -> ReceiptDetail:
    line_items = [item for item, _ in item_rows]
    return ReceiptDetail(
        id=receipt.id,
        image_key=receipt.image_key,
        extraction_status=receipt.extraction_status,
        merchant=receipt.merchant,
        total_cents=receipt.total_cents,
        tax_cents=receipt.tax_cents,
        currency=receipt.currency,
        extraction_error=receipt.extraction_error,
        categorization_status=receipt.categorization_status,
        categorization_error=receipt.categorization_error,
        line_items=[
            LineItemDetail(
                id=item.id,
                description=item.description,
                amount_cents=item.amount_cents,
                category=category,
                needs_category_review=item.needs_category_review,
            )
            for item, category in item_rows
        ],
        reconciliation=reconciliation_for(receipt, line_items),
        confirmed_at=receipt.confirmed_at,
    )


@router.get("/{receipt_id}", response_model=ReceiptDetail)
async def get_receipt(receipt_id: int) -> ReceiptDetail:
    async with session_factory()() as session:
        receipt = await session.get(Receipt, receipt_id)
        line_items = [
            (item, category)
            for item, category in (
                await session.execute(
                    select(LineItem, Category.name)
                    .outerjoin(Category, LineItem.category_id == Category.id)
                    .where(LineItem.receipt_id == receipt_id)
                    .order_by(LineItem.id)
                )
            ).all()
        ]
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
    return receipt_detail(receipt, line_items)


class ConfirmedLineItem(BaseModel):
    id: int
    description: str = Field(min_length=1, max_length=255)
    amount_cents: int
    category: str = Field(min_length=1, max_length=100)


class ReceiptConfirmation(BaseModel):
    line_items: list[ConfirmedLineItem]
    acknowledge_reconciliation_mismatch: bool = False

    @model_validator(mode="after")
    def unique_line_item_ids(self) -> "ReceiptConfirmation":
        if len({item.id for item in self.line_items}) != len(self.line_items):
            raise ValueError("Each line item may only be submitted once")
        return self


@router.put("/{receipt_id}/confirmation", response_model=ReceiptDetail)
async def confirm_receipt(receipt_id: int, confirmation: ReceiptConfirmation) -> ReceiptDetail:
    """Persist the reviewed breakdown, requiring an explicit mismatch acknowledgement."""
    async with session_factory()() as session:
        receipt = await session.get(Receipt, receipt_id)
        if receipt is None:
            raise HTTPException(status_code=404, detail="Receipt not found")
        if receipt.extraction_status is not ExtractionStatus.SUCCEEDED:
            raise HTTPException(status_code=409, detail="Receipt extraction has not completed")
        if receipt.confirmed_at is not None:
            raise HTTPException(status_code=409, detail="Receipt has already been confirmed")
        if receipt.total_cents is None:
            raise HTTPException(
                status_code=409, detail="Receipt total is unavailable for reconciliation"
            )

        existing_items = list(
            await session.scalars(
                select(LineItem).where(LineItem.receipt_id == receipt_id).order_by(LineItem.id)
            )
        )
        submitted_by_id = {item.id: item for item in confirmation.line_items}
        if set(submitted_by_id) != {item.id for item in existing_items}:
            raise HTTPException(
                status_code=422, detail="Confirmation must include every receipt line item"
            )
        categories = {
            category.name: category.id
            for category in list(
                await session.scalars(select(Category).where(Category.org_id.is_(None)))
            )
        }
        invalid_categories = sorted(
            {item.category for item in confirmation.line_items}.difference(categories)
        )
        if invalid_categories:
            raise HTTPException(
                status_code=422,
                detail=f"Unknown category: {', '.join(invalid_categories)}",
            )

        submitted_total_cents = sum(item.amount_cents for item in confirmation.line_items)
        if (
            submitted_total_cents != receipt.total_cents
            and not confirmation.acknowledge_reconciliation_mismatch
        ):
            raise HTTPException(
                status_code=409,
                detail=(
                    "Line-item total does not match the receipt total; explicitly acknowledge "
                    "the difference to confirm"
                ),
            )

        for item in existing_items:
            submitted = submitted_by_id[item.id]
            item.description = submitted.description
            item.amount_cents = submitted.amount_cents
            item.category_id = categories[submitted.category]
            item.needs_category_review = False
        receipt.confirmed_at = datetime.now(UTC)
        await session.commit()
        item_rows = [
            (item, category)
            for item, category in (
                await session.execute(
                    select(LineItem, Category.name)
                    .outerjoin(Category, LineItem.category_id == Category.id)
                    .where(LineItem.receipt_id == receipt_id)
                    .order_by(LineItem.id)
                )
            ).all()
        ]
    return receipt_detail(receipt, item_rows)
