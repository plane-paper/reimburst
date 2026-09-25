"""Development-facing organization reimbursement workflow endpoints.

P5 replaces ``development_actor`` with an authenticated principal dependency.
All workflow authorization checks remain here so that replacement does not
change the state machine's security rules.
"""

import os
from datetime import datetime
from typing import Protocol

from arq import create_pool
from arq.connections import RedisSettings
from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field, model_validator
from shared.enums import ExtractionStatus, RequestStatus, UserRole
from shared.models import AuditEvent, Organization, Receipt, ReimbursementRequest, User
from shared.workflow import InvalidRequestTransition, transition_audit_event
from sqlalchemy import select

from app.database import session_factory

router = APIRouter(prefix="/organization/requests", tags=["organization requests"])


class JobQueue(Protocol):
    async def enqueue_job(self, function: str, *args: object) -> object: ...

    async def close(self) -> None: ...


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


class OrganizationRequestDetail(BaseModel):
    id: int
    employee_id: int
    status: RequestStatus
    currency: str
    synopsis: str | None
    synopsis_status: ExtractionStatus
    synopsis_error: str | None
    receipt_ids: list[int]
    audit_events: list[AuditEventDetail]


async def development_actor(role: UserRole) -> User:
    """Temporary P4 identity source, intentionally isolated for P5 auth replacement."""
    email = f"local-{role.value}@reimburst.test"
    async with session_factory()() as session:
        actor = await session.scalar(select(User).where(User.email == email))
        if actor is not None:
            return actor
        organization = await session.scalar(select(Organization).order_by(Organization.id))
        if organization is None:
            organization = Organization(name="Development organization")
            session.add(organization)
            await session.flush()
        actor = User(email=email, org_id=organization.id, role=role)
        session.add(actor)
        await session.commit()
        await session.refresh(actor)
        return actor


async def request_detail(request_id: int) -> OrganizationRequestDetail:
    async with session_factory()() as session:
        reimbursement = await session.get(ReimbursementRequest, request_id)
        if reimbursement is None:
            raise HTTPException(status_code=404, detail="Organization request not found")
        receipt_ids = list(
            await session.scalars(
                select(Receipt.id)
                .where(Receipt.request_id == reimbursement.id)
                .order_by(Receipt.id)
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
            receipt_ids=receipt_ids,
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
    actor = await development_actor(UserRole.EMPLOYEE)
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


async def enqueue_synopsis(request: Request, request_id: int) -> None:
    queue: JobQueue | None = getattr(request.app.state, "job_queue", None)
    close_queue = False
    if queue is None:
        redis_url = os.environ.get("REDIS_URL")
        if not redis_url:
            raise HTTPException(
                status_code=503, detail="Synopsis generation is temporarily unavailable"
            )
        queue = await create_pool(RedisSettings.from_dsn(redis_url))
        close_queue = True
    try:
        await queue.enqueue_job("generate_reimbursement_synopsis", request_id)
    finally:
        if close_queue:
            await queue.close()


@router.post("/{request_id}/submit", response_model=OrganizationRequestDetail)
async def submit_organization_request(
    request_id: int, request: Request
) -> OrganizationRequestDetail:
    actor = await development_actor(UserRole.EMPLOYEE)
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
    await enqueue_synopsis(request, request_id)
    return await request_detail(request_id)


@router.get("/pending", response_model=list[OrganizationRequestDetail])
async def pending_organization_requests() -> list[OrganizationRequestDetail]:
    actor = await development_actor(UserRole.APPROVER)
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
    actor = await development_actor(UserRole.APPROVER)
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
    actor = await development_actor(UserRole.EMPLOYEE)
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
    actor = await development_actor(UserRole.EMPLOYEE)
    async with session_factory()() as session:
        reimbursement = await session.get(ReimbursementRequest, request_id)
        if reimbursement is None or reimbursement.org_id != actor.org_id:
            raise HTTPException(status_code=404, detail="Organization request not found")
    return await request_detail(request_id)
