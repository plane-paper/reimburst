import asyncio
from datetime import UTC, datetime

import pytest
from app import organization
from fastapi import HTTPException
from shared.enums import ExtractionStatus, RequestStatus, UserRole
from shared.models import AuditEvent, LineItem, Receipt, ReimbursementRequest, User
from starlette.requests import Request


class ScalarRows:
    def __init__(self, values: list[Receipt]) -> None:
        self.values = values

    def __iter__(self):
        return iter(self.values)


class WorkflowSession:
    def __init__(self, reimbursement: ReimbursementRequest, receipts: list[Receipt]) -> None:
        self.reimbursement = reimbursement
        self.receipts = receipts
        self.events: list[AuditEvent] = []
        self.commit_count = 0

    async def __aenter__(self) -> "WorkflowSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    async def get(self, _: type[ReimbursementRequest], __: int) -> ReimbursementRequest:
        return self.reimbursement

    async def scalars(self, _: object) -> ScalarRows:
        return ScalarRows(self.receipts)

    def add(self, value: object) -> None:
        if isinstance(value, AuditEvent):
            value.id = len(self.events) + 1
            self.events.append(value)

    async def commit(self) -> None:
        self.commit_count += 1


class ExecuteRows:
    def __init__(self, values: list[tuple[LineItem, str | None]]) -> None:
        self.values = values

    def all(self) -> list[tuple[LineItem, str | None]]:
        return self.values


class DetailSession:
    def __init__(
        self,
        reimbursement: ReimbursementRequest,
        receipts: list[Receipt],
        item_rows: list[tuple[LineItem, str | None]],
        events: list[AuditEvent],
    ) -> None:
        self.reimbursement = reimbursement
        self.receipts = receipts
        self.item_rows = item_rows
        self.events = events
        self.scalar_calls = 0

    async def __aenter__(self) -> "DetailSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    async def get(self, _: type[ReimbursementRequest], __: int) -> ReimbursementRequest:
        return self.reimbursement

    async def scalars(self, _: object) -> ScalarRows:
        self.scalar_calls += 1
        return ScalarRows(self.receipts if self.scalar_calls == 1 else self.events)  # type: ignore[arg-type]

    async def execute(self, _: object) -> ExecuteRows:
        return ExecuteRows(self.item_rows)


def request_detail(reimbursement: ReimbursementRequest) -> organization.OrganizationRequestDetail:
    return organization.OrganizationRequestDetail(
        id=reimbursement.id,
        employee_id=reimbursement.employee_id,
        status=reimbursement.status,
        currency=reimbursement.currency,
        synopsis=reimbursement.synopsis,
        synopsis_status=reimbursement.synopsis_status,
        synopsis_error=reimbursement.synopsis_error,
        receipt_ids=[],
        receipts=[],
        audit_events=[],
    )


def test_submit_transitions_audits_and_enqueues_synopsis(monkeypatch) -> None:
    reimbursement = ReimbursementRequest(
        id=7,
        org_id=3,
        employee_id=2,
        currency="USD",
        status=RequestStatus.DRAFT,
        synopsis_status=ExtractionStatus.PENDING,
    )
    receipt = Receipt(
        id=4,
        owner_id=2,
        request_id=7,
        image_key="receipts/test.jpg",
        confirmed_at=datetime.now(UTC),
    )
    session = WorkflowSession(reimbursement, [receipt])
    employee = User(id=2, org_id=3, email="employee@example.test", role=UserRole.EMPLOYEE)
    queued: list[tuple[str, tuple[object, ...]]] = []

    async def actor(_: UserRole) -> User:
        return employee

    async def detail(_: int) -> organization.OrganizationRequestDetail:
        return request_detail(reimbursement)

    async def enqueue(_: Request, function: str, *args: object, unavailable_detail: str) -> None:
        assert unavailable_detail == "Synopsis generation is temporarily unavailable"
        queued.append((function, args))

    monkeypatch.setattr(organization, "session_factory", lambda: lambda: session)
    monkeypatch.setattr(organization, "development_organization_actor", actor)
    monkeypatch.setattr(organization, "request_detail", detail)
    monkeypatch.setattr(organization, "enqueue", enqueue)

    async def run() -> None:
        result = await organization.submit_organization_request(
            reimbursement.id, Request({"type": "http", "headers": []})
        )
        assert result.status is RequestStatus.SUBMITTED

    asyncio.run(run())

    assert reimbursement.status is RequestStatus.SUBMITTED
    assert reimbursement.synopsis_status is ExtractionStatus.PENDING
    assert queued == [("generate_reimbursement_synopsis", (reimbursement.id,))]
    assert len(session.events) == 1
    assert session.events[0].actor_id == employee.id
    assert session.events[0].payload == {"from_status": "draft", "to_status": "submitted"}


def test_request_detail_includes_receipt_breakdown(monkeypatch) -> None:
    reimbursement = ReimbursementRequest(
        id=7,
        org_id=3,
        employee_id=2,
        currency="USD",
        status=RequestStatus.SUBMITTED,
        synopsis_status=ExtractionStatus.SUCCEEDED,
        synopsis="Hotel stay for client meeting.",
    )
    receipt = Receipt(
        id=4,
        owner_id=2,
        request_id=7,
        image_key="receipts/hotel.jpg",
        merchant="Example Hotel",
        date=datetime(2026, 9, 25, tzinfo=UTC).date(),
        currency="USD",
        total_cents=12000,
        tax_cents=1000,
    )
    item = LineItem(
        id=8,
        receipt_id=receipt.id,
        description="One night stay",
        amount_cents=12000,
    )
    session = DetailSession(reimbursement, [receipt], [(item, "hotel")], [])
    monkeypatch.setattr(organization, "session_factory", lambda: lambda: session)

    detail = asyncio.run(organization.request_detail(reimbursement.id))

    assert detail.receipt_ids == [receipt.id]
    assert detail.receipts[0].model_dump() == {
        "id": 4,
        "image_key": "receipts/hotel.jpg",
        "merchant": "Example Hotel",
        "date": datetime(2026, 9, 25, tzinfo=UTC).date(),
        "total_cents": 12000,
        "tax_cents": 1000,
        "currency": "USD",
        "line_items": [
            {
                "id": 8,
                "description": "One night stay",
                "amount_cents": 12000,
                "category": "hotel",
            }
        ],
    }


def test_reject_records_approver_note(monkeypatch) -> None:
    reimbursement = ReimbursementRequest(
        id=7,
        org_id=3,
        employee_id=2,
        currency="USD",
        status=RequestStatus.SUBMITTED,
        synopsis_status=ExtractionStatus.PENDING,
    )
    session = WorkflowSession(reimbursement, [])
    approver = User(id=5, org_id=3, email="approver@example.test", role=UserRole.APPROVER)

    async def actor(_: UserRole) -> User:
        return approver

    async def detail(_: int) -> organization.OrganizationRequestDetail:
        return request_detail(reimbursement)

    monkeypatch.setattr(organization, "session_factory", lambda: lambda: session)
    monkeypatch.setattr(organization, "development_organization_actor", actor)
    monkeypatch.setattr(organization, "request_detail", detail)

    result = asyncio.run(
        organization.review_organization_request(
            reimbursement.id, RequestStatus.REJECTED, "Receipt total needs clarification"
        )
    )

    assert result.status is RequestStatus.REJECTED
    assert session.events[0].actor_id == approver.id
    assert session.events[0].payload == {
        "from_status": "submitted",
        "to_status": "rejected",
        "note": "Receipt total needs clarification",
    }


def test_approver_cannot_transition_draft_request(monkeypatch) -> None:
    reimbursement = ReimbursementRequest(
        id=7,
        org_id=3,
        employee_id=2,
        currency="USD",
        status=RequestStatus.DRAFT,
        synopsis_status=ExtractionStatus.PENDING,
    )
    session = WorkflowSession(reimbursement, [])
    approver = User(id=5, org_id=3, email="approver@example.test", role=UserRole.APPROVER)

    async def actor(_: UserRole) -> User:
        return approver

    monkeypatch.setattr(organization, "session_factory", lambda: lambda: session)
    monkeypatch.setattr(organization, "development_organization_actor", actor)

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            organization.review_organization_request(reimbursement.id, RequestStatus.APPROVED, None)
        )

    assert error.value.status_code == 409
    assert session.events == []
