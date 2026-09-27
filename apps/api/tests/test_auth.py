import asyncio

import pytest
from app import auth, ownership
from fastapi import HTTPException
from shared.enums import UserRole
from shared.models import User


def test_password_hashes_are_salted_and_verifiable() -> None:
    encoded = auth.hash_password("a-long-enough-password")

    assert auth.verify_password("a-long-enough-password", encoded)
    assert not auth.verify_password("not-the-password", encoded)


def test_session_token_is_signed_and_expires(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_SECRET", "test-secret")
    user = User(id=12, email="person@example.test", role=UserRole.INDIVIDUAL)

    token = auth.issue_token(user)

    assert token
    assert asyncio.run(auth.user_from_bearer("Bearer malformed")) is None


def test_individual_features_reject_organization_principals() -> None:
    token = auth._principal.set(
        User(id=2, org_id=1, email="employee@example.test", role=UserRole.EMPLOYEE)
    )
    try:
        with pytest.raises(HTTPException, match="only available to individuals"):
            asyncio.run(ownership.individual_owner_id("Personal spending"))
    finally:
        auth._principal.reset(token)


def test_approver_gate_allows_admin_but_not_employee() -> None:
    employee_token = auth._principal.set(
        User(id=2, org_id=1, email="employee@example.test", role=UserRole.EMPLOYEE)
    )
    try:
        with pytest.raises(HTTPException) as error:
            asyncio.run(ownership.development_organization_actor(UserRole.APPROVER))
        assert error.value.status_code == 403
    finally:
        auth._principal.reset(employee_token)

    admin_token = auth._principal.set(
        User(id=3, org_id=1, email="admin@example.test", role=UserRole.ADMIN)
    )
    try:
        assert asyncio.run(ownership.development_organization_actor(UserRole.APPROVER)).id == 3
    finally:
        auth._principal.reset(admin_token)
