import mimetypes
import os
import uuid
from typing import Annotated, Protocol

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from pydantic import BaseModel
from shared.enums import ExtractionStatus, UserRole
from shared.models import Category, LineItem, Receipt, User
from shared.storage import ObjectStorage, object_storage_from_environment
from sqlalchemy import select

from app.database import session_factory

router = APIRouter(prefix="/receipts", tags=["receipts"])


class JobQueue(Protocol):
    async def enqueue_job(self, function: str, *args: object) -> object: ...

    async def close(self) -> None: ...


class ReceiptCreated(BaseModel):
    id: int
    image_key: str
    extraction_status: ExtractionStatus


class LineItemDetail(BaseModel):
    description: str
    amount_cents: int
    category: str | None
    needs_category_review: bool


class ReceiptDetail(ReceiptCreated):
    merchant: str | None
    total_cents: int | None
    tax_cents: int | None
    currency: str | None = None
    extraction_error: str | None
    categorization_status: ExtractionStatus
    categorization_error: str | None
    line_items: list[LineItemDetail]


def object_storage(request: Request) -> ObjectStorage:
    storage: ObjectStorage | None = getattr(request.app.state, "object_storage", None)
    return storage if storage is not None else object_storage_from_environment()


async def development_owner_id() -> int:
    """Temporary no-auth owner for P1; replaced by the authenticated subject in P5."""
    async with session_factory()() as session:
        owner = await session.scalar(select(User).where(User.email == "local@reimburst.test"))
        if owner is None:
            owner = User(email="local@reimburst.test", role=UserRole.INDIVIDUAL)
            session.add(owner)
            await session.commit()
            await session.refresh(owner)
        return owner.id


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

    queue: JobQueue | None = getattr(request.app.state, "job_queue", None)
    close_queue = False
    if queue is None:
        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            raise HTTPException(
                status_code=503, detail="Receipt processing is temporarily unavailable"
            )
        queue = await create_pool(RedisSettings.from_dsn(redis_url))
        close_queue = True
    try:
        await queue.enqueue_job("extract_receipt", receipt.id, content_type)
    finally:
        if close_queue:
            await queue.close()
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


@router.get("/{receipt_id}", response_model=ReceiptDetail)
async def get_receipt(receipt_id: int) -> ReceiptDetail:
    async with session_factory()() as session:
        receipt = await session.get(Receipt, receipt_id)
        line_items = list(
            (
                await session.execute(
                    select(LineItem, Category.name)
                    .outerjoin(Category, LineItem.category_id == Category.id)
                    .where(LineItem.receipt_id == receipt_id)
                    .order_by(LineItem.id)
                )
            ).all()
        )
    if receipt is None:
        raise HTTPException(status_code=404, detail="Receipt not found")
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
                description=item.description,
                amount_cents=item.amount_cents,
                category=category,
                needs_category_review=item.needs_category_review,
            )
            for item, category in line_items
        ],
    )
