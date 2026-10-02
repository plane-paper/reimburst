import asyncio

from app import organization
from shared.enums import PayoutStatus, RequestStatus, UserRole
from shared.models import AuditEvent, Payout, ReimbursementRequest, User


class PayoutSession:
    def __init__(self, reimbursement: ReimbursementRequest, employee: User) -> None:
        self.reimbursement = reimbursement
        self.employee = employee
        self.payout: Payout | None = None
        self.events: list[AuditEvent] = []
        self.commits = 0

    async def __aenter__(self) -> "PayoutSession":
        return self

    async def __aexit__(self, *_: object) -> None:
        pass

    async def get(self, model: object, _: int) -> object:
        if model is ReimbursementRequest:
            return self.reimbursement
        return self.employee

    async def scalar(self, _: object) -> Payout | int | None:
        if self.payout is None:
            # The first call looks up the payout, and the second totals line items.
            if not hasattr(self, "looked_up"):
                self.looked_up = True
                return None
            return 12345
        return self.payout

    def add(self, value: object) -> None:
        if isinstance(value, Payout):
            self.payout = value
        if isinstance(value, AuditEvent):
            self.events.append(value)

    async def commit(self) -> None:
        self.commits += 1


def test_csv_payout_is_idempotent_and_freezes_the_export(monkeypatch) -> None:
    reimbursement = ReimbursementRequest(
        id=17,
        org_id=3,
        employee_id=2,
        currency="USD",
        status=RequestStatus.APPROVED,
    )
    employee = User(id=2, org_id=3, email="employee@example.test", role=UserRole.EMPLOYEE)
    admin = User(id=5, org_id=3, email="admin@example.test", role=UserRole.ADMIN)
    session = PayoutSession(reimbursement, employee)

    async def actor(_: UserRole) -> User:
        return admin

    monkeypatch.setattr(organization, "session_factory", lambda: lambda: session)
    monkeypatch.setattr(organization, "development_organization_actor", actor)

    first = asyncio.run(organization.export_csv_payout(reimbursement.id))
    second = asyncio.run(organization.export_csv_payout(reimbursement.id))

    assert first.body == second.body
    assert first.body.decode().endswith("17,employee@example.test,12345,USD,csv:payout:17\r\n")
    assert reimbursement.status is RequestStatus.PAID
    assert session.payout is not None
    assert session.payout.status is PayoutStatus.SUCCEEDED
    assert session.payout.idempotency_key == "csv:payout:17"
    assert session.commits == 1
    assert len(session.events) == 1
    assert session.events[0].payload == {
        "from_status": "approved",
        "to_status": "paid",
        "amount_cents": "12345",
        "currency": "USD",
        "idempotency_key": "csv:payout:17",
    }
