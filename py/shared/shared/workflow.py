"""Organization reimbursement request state-machine primitives.

The API owns persistence and authorization; this module owns the transition
rules so every caller applies the same finite-state machine.
"""

from typing import Final

from shared.enums import RequestStatus
from shared.models import AuditEvent


class InvalidRequestTransition(ValueError):
    """Raised when a request is moved outside the approved workflow."""


_ALLOWED_TRANSITIONS: Final[dict[RequestStatus, frozenset[RequestStatus]]] = {
    RequestStatus.DRAFT: frozenset({RequestStatus.SUBMITTED}),
    RequestStatus.SUBMITTED: frozenset({RequestStatus.APPROVED, RequestStatus.REJECTED}),
    RequestStatus.APPROVED: frozenset({RequestStatus.PAID}),
    RequestStatus.REJECTED: frozenset(),
    RequestStatus.PAID: frozenset(),
}


def can_transition(current: RequestStatus, target: RequestStatus) -> bool:
    """Return whether the explicit reimbursement workflow permits a transition."""
    return target in _ALLOWED_TRANSITIONS[current]


def require_transition(current: RequestStatus, target: RequestStatus) -> None:
    """Validate a request transition, raising a stable domain error if invalid."""
    if not can_transition(current, target):
        raise InvalidRequestTransition(f"Cannot transition request from {current} to {target}")


def transition_audit_event(
    request_id: int,
    actor_id: int,
    previous_status: RequestStatus,
    target_status: RequestStatus,
    note: str | None = None,
) -> AuditEvent:
    """Build an append-only audit record for one validated state transition."""
    require_transition(previous_status, target_status)
    payload: dict[str, str] = {
        "from_status": previous_status.value,
        "to_status": target_status.value,
    }
    if note:
        payload["note"] = note
    return AuditEvent(
        request_id=request_id,
        actor_id=actor_id,
        action=f"request.{target_status.value}",
        payload=payload,
    )
