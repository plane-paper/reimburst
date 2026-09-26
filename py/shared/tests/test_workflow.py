import pytest
from shared.enums import RequestStatus
from shared.workflow import InvalidRequestTransition, can_transition, transition_audit_event


def test_request_state_machine_allows_only_specified_transitions() -> None:
    assert can_transition(RequestStatus.DRAFT, RequestStatus.SUBMITTED)
    assert can_transition(RequestStatus.SUBMITTED, RequestStatus.APPROVED)
    assert can_transition(RequestStatus.SUBMITTED, RequestStatus.REJECTED)
    assert can_transition(RequestStatus.APPROVED, RequestStatus.PAID)
    assert not can_transition(RequestStatus.DRAFT, RequestStatus.APPROVED)
    assert not can_transition(RequestStatus.REJECTED, RequestStatus.SUBMITTED)
    assert not can_transition(RequestStatus.PAID, RequestStatus.PAID)


def test_transition_audit_event_captures_actor_statuses_and_optional_note() -> None:
    event = transition_audit_event(
        request_id=42,
        actor_id=7,
        previous_status=RequestStatus.SUBMITTED,
        target_status=RequestStatus.REJECTED,
        note="Missing client receipt reference",
    )

    assert event.request_id == 42
    assert event.actor_id == 7
    assert event.action == "request.rejected"
    assert event.payload == {
        "from_status": "submitted",
        "to_status": "rejected",
        "note": "Missing client receipt reference",
    }


def test_transition_audit_event_rejects_invalid_transition() -> None:
    with pytest.raises(InvalidRequestTransition, match="draft to approved"):
        transition_audit_event(42, 7, RequestStatus.DRAFT, RequestStatus.APPROVED)
