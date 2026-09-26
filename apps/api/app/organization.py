"""Development-facing organization reimbursement workflow endpoints.

P5 replaces the development actor dependency with an authenticated principal.
All workflow authorization checks remain here so that replacement does not
change the state machine's security rules.
"""

from datetime import date, datetime

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from shared.enums import ExtractionStatus, RequestStatus, UserRole
from shared.models import AuditEvent, Category, LineItem, Receipt, ReimbursementRequest
from shared.workflow import InvalidRequestTransition, transition_audit_event
from sqlalchemy import select

from app.database import session_factory
from app.jobs import enqueue
from app.ownership import development_organization_actor

router = APIRouter(prefix="/organization/requests", tags=["organization requests"])


class OrganizationRequestCreate(BaseModel):
    receipt_ids: list[int] = Field(min_length=1)

    @model_validator(mode="after")
    def unique_receipt_ids(self) -> "OrganizationRequestCreate":
        if len(set(self.receipt_ids)) != len(self.receipt_ids):
            raise ValueError("Each receipt may only be submitted once")
        return self


class TransitionNote(BaseModel):
    note: str | None = Field(default=None, max_length=1000)


class AuditEventDetail(BaseModel):
    id: int
    actor_id: int
    action: str
    payload: dict[str, str] | None
    created_at: datetime


class OrganizationLineItemDetail(BaseModel):
    id: int
    description: str
    amount_cents: int
    category: str | None


class OrganizationReceiptDetail(BaseModel):
    id: int
    image_key: str
    merchant: str | None
    date: date | None
    total_cents: int | None
    tax_cents: int | None
    currency: str | None
    line_items: list[OrganizationLineItemDetail]


class OrganizationRequestDetail(BaseModel):
    id: int
    employee_id: int
    status: RequestStatus
    currency: str
    synopsis: str | None
    synopsis_status: ExtractionStatus
    synopsis_error: str | None
    receipt_ids: list[int]
    receipts: list[OrganizationReceiptDetail]
    audit_events: list[AuditEventDetail]


async def request_detail(request_id: int) -> OrganizationRequestDetail:
    async with session_factory()() as session:
        reimbursement = await session.get(ReimbursementRequest, request_id)
        if reimbursement is None:
            raise HTTPException(status_code=404, detail="Organization request not found")
        receipts = list(
            await session.scalars(
                select(Receipt)
                .where(Receipt.request_id == reimbursement.id)
                .order_by(Receipt.id)
            )
        )
        item_rows = (
            await session.execute(
                select(LineItem, Category.name)
                .join(Receipt, Receipt.id == LineItem.receipt_id)
                .outerjoin(Category, Category.id == LineItem.category_id)
                .where(Receipt.request_id == reimbursement.id)
                .order_by(Receipt.id, LineItem.id)
            )
        ).all()
        items_by_receipt: dict[int, list[OrganizationLineItemDetail]] = {
            receipt.id: [] for receipt in receipts
        }
        for item, category in item_rows:
            items_by_receipt[item.receipt_id].append(
                OrganizationLineItemDetail(
                    id=item.id,
                    description=item.description,
                    amount_cents=item.amount_cents,
                    category=category,
                )
            )
        events = list(
            await session.scalars(
                select(AuditEvent)
                .where(AuditEvent.request_id == reimbursement.id)
                .order_by(AuditEvent.id)
            )
        )
        return OrganizationRequestDetail(
            id=reimbursement.id,
            employee_id=reimbursement.employee_id,
            status=reimbursement.status,
            currency=reimbursement.currency,
            synopsis=reimbursement.synopsis,
            synopsis_status=reimbursement.synopsis_status,
            synopsis_error=reimbursement.synopsis_error,
            receipt_ids=[receipt.id for receipt in receipts],
            receipts=[
                OrganizationReceiptDetail(
                    id=receipt.id,
                    image_key=receipt.image_key,
                    merchant=receipt.merchant,
                    date=receipt.date,
                    total_cents=receipt.total_cents,
                    tax_cents=receipt.tax_cents,
                    currency=receipt.currency,
                    line_items=items_by_receipt[receipt.id],
                )
                for receipt in receipts
            ],
            audit_events=[
                AuditEventDetail(
                    id=event.id,
                    actor_id=event.actor_id,
                    action=event.action,
                    payload=event.payload,
                    created_at=event.created_at,
                )
                for event in events
            ],
        )


@router.post("", response_model=OrganizationRequestDetail, status_code=status.HTTP_201_CREATED)
async def create_organization_request(
    payload: OrganizationRequestCreate,
) -> OrganizationRequestDetail:
    actor = await development_organization_actor(UserRole.EMPLOYEE)
    if actor.org_id is None:
        raise HTTPException(status_code=409, detail="Employee must belong to an organization")
    async with session_factory()() as session:
        receipts = list(
            await session.scalars(
                select(Receipt)
                .where(Receipt.id.in_(payload.receipt_ids))
                .order_by(Receipt.id)
            )
        )
        if len(receipts) != len(payload.receipt_ids) or any(
            receipt.owner_id != actor.id
            or receipt.confirmed_at is None
            or receipt.request_id is not None
            for receipt in receipts
        ):
            raise HTTPException(
                status_code=422,
                detail="Receipts must be confirmed, unassigned receipts owned by the employee",
            )
        currencies = {receipt.currency for receipt in receipts}
        if len(currencies) != 1 or None in currencies:
            raise HTTPException(
                status_code=422,
                detail="All request receipts must have the same extracted currency",
            )
        reimbursement = ReimbursementRequest(
            org_id=actor.org_id,
            employee_id=actor.id,
            currency=currencies.pop(),
        )
        session.add(reimbursement)
        await session.flush()
        for receipt in receipts:
            receipt.request_id = reimbursement.id
        await session.commit()
        request_id = reimbursement.id
    return await request_detail(request_id)


@router.post("/{request_id}/submit", response_model=OrganizationRequestDetail)
async def submit_organization_request(
    request_id: int, request: Request
) -> OrganizationRequestDetail:
    actor = await development_organization_actor(UserRole.EMPLOYEE)
    async with session_factory()() as session:
        reimbursement = await session.get(ReimbursementRequest, request_id)
        if reimbursement is None or reimbursement.org_id != actor.org_id:
            raise HTTPException(status_code=404, detail="Organization request not found")
        if reimbursement.employee_id != actor.id:
            raise HTTPException(
                status_code=403, detail="Only the submitting employee may submit this request"
            )
        receipts = list(
            await session.scalars(select(Receipt).where(Receipt.request_id == reimbursement.id))
        )
        if not receipts or any(receipt.confirmed_at is None for receipt in receipts):
            raise HTTPException(status_code=409, detail="Every request receipt must be confirmed")
        try:
            event = transition_audit_event(
                reimbursement.id, actor.id, reimbursement.status, RequestStatus.SUBMITTED
            )
        except InvalidRequestTransition as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        reimbursement.status = RequestStatus.SUBMITTED
        reimbursement.synopsis_status = ExtractionStatus.PENDING
        reimbursement.synopsis_error = None
        session.add(event)
        await session.commit()
    await enqueue(
        request,
        "generate_reimbursement_synopsis",
        request_id,
        unavailable_detail="Synopsis generation is temporarily unavailable",
    )
    return await request_detail(request_id)


@router.get("/pending", response_model=list[OrganizationRequestDetail])
async def pending_organization_requests() -> list[OrganizationRequestDetail]:
    actor = await development_organization_actor(UserRole.APPROVER)
    async with session_factory()() as session:
        request_ids = list(
            await session.scalars(
                select(ReimbursementRequest.id)
                .where(
                    ReimbursementRequest.org_id == actor.org_id,
                    ReimbursementRequest.status == RequestStatus.SUBMITTED,
                )
                .order_by(ReimbursementRequest.created_at, ReimbursementRequest.id)
            )
        )
    return [await request_detail(request_id) for request_id in request_ids]


@router.post("/{request_id}/approve", response_model=OrganizationRequestDetail)
async def approve_organization_request(
    request_id: int, payload: TransitionNote
) -> OrganizationRequestDetail:
    return await review_organization_request(request_id, RequestStatus.APPROVED, payload.note)


@router.post("/{request_id}/reject", response_model=OrganizationRequestDetail)
async def reject_organization_request(
    request_id: int, payload: TransitionNote
) -> OrganizationRequestDetail:
    return await review_organization_request(request_id, RequestStatus.REJECTED, payload.note)


async def review_organization_request(
    request_id: int, target_status: RequestStatus, note: str | None
) -> OrganizationRequestDetail:
    actor = await development_organization_actor(UserRole.APPROVER)
    async with session_factory()() as session:
        reimbursement = await session.get(ReimbursementRequest, request_id)
        if reimbursement is None or reimbursement.org_id != actor.org_id:
            raise HTTPException(status_code=404, detail="Organization request not found")
        if reimbursement.employee_id == actor.id:
            raise HTTPException(
                status_code=403, detail="Employees cannot approve their own requests"
            )
        try:
            event = transition_audit_event(
                reimbursement.id, actor.id, reimbursement.status, target_status, note
            )
        except InvalidRequestTransition as error:
            raise HTTPException(status_code=409, detail=str(error)) from error
        reimbursement.status = target_status
        session.add(event)
        await session.commit()
    return await request_detail(request_id)


@router.get("/mine", response_model=list[OrganizationRequestDetail])
async def my_organization_requests() -> list[OrganizationRequestDetail]:
    actor = await development_organization_actor(UserRole.EMPLOYEE)
    async with session_factory()() as session:
        request_ids = list(
            await session.scalars(
                select(ReimbursementRequest.id)
                .where(ReimbursementRequest.employee_id == actor.id)
                .order_by(ReimbursementRequest.created_at.desc(), ReimbursementRequest.id.desc())
            )
        )
    return [await request_detail(request_id) for request_id in request_ids]


@router.get("/{request_id}", response_model=OrganizationRequestDetail)
async def get_organization_request(request_id: int) -> OrganizationRequestDetail:
    actor = await development_organization_actor(UserRole.EMPLOYEE)
    async with session_factory()() as session:
        reimbursement = await session.get(ReimbursementRequest, request_id)
        if reimbursement is None or reimbursement.org_id != actor.org_id:
            raise HTTPException(status_code=404, detail="Organization request not found")
    return await request_detail(request_id)
