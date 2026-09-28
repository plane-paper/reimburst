from datetime import UTC, datetime

from app.notifications import serialize
from shared.models import Notification


def test_notification_serialization_preserves_read_state() -> None:
    created_at = datetime(2026, 9, 28, 12, tzinfo=UTC)
    notification = Notification(
        id=4,
        user_id=2,
        request_id=7,
        kind="request_submitted",
        title="Request #7 needs review",
        body="An employee submitted a reimbursement request.",
        created_at=created_at,
    )

    detail = serialize(notification)

    assert detail.model_dump() == {
        "id": 4,
        "request_id": 7,
        "kind": "request_submitted",
        "title": "Request #7 needs review",
        "body": "An employee submitted a reimbursement request.",
        "read_at": None,
        "created_at": created_at,
    }
