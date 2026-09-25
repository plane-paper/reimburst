from datetime import UTC, date, datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from shared.enums import ExtractionStatus, OutboundRequestStatus
from shared.models import Category, LineItem, OutboundRequest, OutboundRequestItem, Receipt
from sqlalchemy import select

from app.database import session_factory
from app.jobs import enqueue
from app.ownership import individual_owner_id

router = APIRouter(prefix="/outbound-requests", tags=["outbound requests"])


class OutboundItemDetail(BaseModel):
    line_item_id: int
    receipt_id: int
    description: str
    amount_cents: int
    currency: str | None
    merchant: str | None
    receipt_date: date | None
    category: str | None


class OutboundRequestDetail(BaseModel):
    id: int
    external_payer: str | None
    synopsis: str | None
    subject: str | None
    body: str | None
    status: OutboundRequestStatus
    generation_status: ExtractionStatus
    generation_error: str | None
    created_at: datetime
    sent_at: datetime | None
    items: list[OutboundItemDetail]


class OutboundRequestCreate(BaseModel):
    external_payer: str = Field(min_length=1, max_length=255)
    line_item_ids: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_line_items(self) -> "OutboundRequestCreate":
        if len(self.line_item_ids) != len(set(self.line_item_ids)):
            raise ValueError("Each line item may only be selected once")
        return self


class OutboundRequestUpdate(BaseModel):
    external_payer: str | None = Field(default=None, min_length=1, max_length=255)
    synopsis: str | None = Field(default=None, min_length=1)
    subject: str | None = Field(default=None, min_length=1)
    body: str | None = Field(default=None, min_length=1)


async def request_detail(request_id: int, owner_id: int) -> OutboundRequestDetail:
    async with session_factory()() as session:
        request = await session.get(OutboundRequest, request_id)
        if request is None or request.user_id != owner_id:
            raise HTTPException(status_code=404, detail="Outbound request not found")
        rows = (
            await session.execute(
                select(LineItem, Receipt, Category.name)
                .join(OutboundRequestItem, OutboundRequestItem.line_item_id == LineItem.id)
                .join(Receipt, Receipt.id == LineItem.receipt_id)
                .outerjoin(Category, Category.id == LineItem.category_id)
                .where(OutboundRequestItem.outbound_request_id == request.id)
                .order_by(Receipt.date, Receipt.id, LineItem.id)
            )
        ).all()
        artifact = request.artifact or {}
        return OutboundRequestDetail(
            id=request.id,
            external_payer=request.external_payer,
            synopsis=request.synopsis,
            subject=artifact.get("subject"),
            body=artifact.get("body"),
            status=request.status,
            generation_status=request.generation_status,
            generation_error=request.generation_error,
            created_at=request.created_at,
            sent_at=request.sent_at,
            items=[
                OutboundItemDetail(
                    line_item_id=item.id,
                    receipt_id=receipt.id,
                    description=item.description,
                    amount_cents=item.amount_cents,
                    currency=receipt.currency,
                    merchant=receipt.merchant,
                    receipt_date=receipt.date,
                    category=category,
                )
                for item, receipt, category in rows
            ],
        )


@router.post("", response_model=OutboundRequestDetail, status_code=status.HTTP_202_ACCEPTED)
async def create_outbound_request(
    request: Request, payload: OutboundRequestCreate
) -> OutboundRequestDetail:
    owner_id = await individual_owner_id("Outbound requests")
    async with session_factory()() as session:
        rows = (
            await session.execute(
                select(LineItem.id)
                .join(Receipt, Receipt.id == LineItem.receipt_id)
                .where(
                    LineItem.id.in_(payload.line_item_ids),
                    Receipt.owner_id == owner_id,
                    Receipt.confirmed_at.is_not(None),
                )
            )
        ).scalars().all()
        if set(rows) != set(payload.line_item_ids):
            raise HTTPException(
                status_code=422, detail="Items must be confirmed items in your personal history"
            )
        already_requested = (
            await session.execute(
                select(OutboundRequestItem.line_item_id)
                .join(
                    OutboundRequest,
                    OutboundRequest.id == OutboundRequestItem.outbound_request_id,
                )
                .where(
                    OutboundRequestItem.line_item_id.in_(payload.line_item_ids),
                    OutboundRequest.user_id == owner_id,
                    OutboundRequest.status.in_(
                        [OutboundRequestStatus.GENERATED, OutboundRequestStatus.SENT]
                    ),
                )
            )
        ).scalars().all()
        if already_requested:
            raise HTTPException(
                status_code=409, detail="Selected items are already covered by an outbound request"
            )
        outbound = OutboundRequest(user_id=owner_id, external_payer=payload.external_payer)
        session.add(outbound)
        await session.flush()
        session.add_all(
            [
                OutboundRequestItem(outbound_request_id=outbound.id, line_item_id=item_id)
                for item_id in payload.line_item_ids
            ]
        )
        await session.commit()
        outbound_id = outbound.id

    await enqueue(
        request,
        "generate_outbound_request",
        outbound_id,
        unavailable_detail="Request generation is temporarily unavailable",
    )
    return await request_detail(outbound_id, owner_id)


@router.get("", response_model=list[OutboundRequestDetail])
async def list_outbound_requests() -> list[OutboundRequestDetail]:
    owner_id = await individual_owner_id("Outbound requests")
    async with session_factory()() as session:
        ids = list(
            await session.scalars(
                select(OutboundRequest.id)
                .where(OutboundRequest.user_id == owner_id)
                .order_by(OutboundRequest.created_at.desc())
            )
        )
    return [await request_detail(request_id, owner_id) for request_id in ids]


@router.get("/{request_id}", response_model=OutboundRequestDetail)
async def get_outbound_request(request_id: int) -> OutboundRequestDetail:
    return await request_detail(request_id, await individual_owner_id("Outbound requests"))


@router.put("/{request_id}", response_model=OutboundRequestDetail)
async def update_outbound_request(
    request_id: int, payload: OutboundRequestUpdate
) -> OutboundRequestDetail:
    owner_id = await individual_owner_id("Outbound requests")
    if not payload.model_fields_set:
        raise HTTPException(status_code=422, detail="Provide at least one editable field")
    async with session_factory()() as session:
        outbound = await session.get(OutboundRequest, request_id)
        if outbound is None or outbound.user_id != owner_id:
            raise HTTPException(status_code=404, detail="Outbound request not found")
        if outbound.generation_status is not ExtractionStatus.SUCCEEDED:
            raise HTTPException(status_code=409, detail="Artifact generation has not completed")
        if outbound.status is OutboundRequestStatus.SENT:
            raise HTTPException(status_code=409, detail="Sent outbound requests cannot be edited")
        if payload.external_payer is not None:
            outbound.external_payer = payload.external_payer
        if payload.synopsis is not None:
            outbound.synopsis = payload.synopsis
        artifact = dict(outbound.artifact or {})
        if payload.subject is not None:
            artifact["subject"] = payload.subject
        if payload.body is not None:
            artifact["body"] = payload.body
        outbound.artifact = artifact
        await session.commit()
    return await request_detail(request_id, owner_id)


@router.post("/{request_id}/mark-sent", response_model=OutboundRequestDetail)
async def mark_outbound_request_sent(request_id: int) -> OutboundRequestDetail:
    owner_id = await individual_owner_id("Outbound requests")
    async with session_factory()() as session:
        outbound = await session.get(OutboundRequest, request_id)
        if outbound is None or outbound.user_id != owner_id:
            raise HTTPException(status_code=404, detail="Outbound request not found")
        if outbound.generation_status is not ExtractionStatus.SUCCEEDED:
            raise HTTPException(status_code=409, detail="Artifact generation has not completed")
        if outbound.status is not OutboundRequestStatus.SENT:
            outbound.status = OutboundRequestStatus.SENT
            outbound.sent_at = datetime.now(UTC)
            await session.commit()
    return await request_detail(request_id, owner_id)
