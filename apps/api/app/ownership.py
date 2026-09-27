"""Role checks backed by the authenticated, request-scoped principal."""

from fastapi import HTTPException
from shared.enums import UserRole
from shared.models import User

from app.auth import current_user


async def development_organization_actor(role: UserRole) -> User:
    """Require an authenticated organization member with the requested role."""
    actor = current_user()
    permitted = {role}
    if role is UserRole.APPROVER:
        permitted.add(UserRole.ADMIN)
    if actor.role not in permitted:
        raise HTTPException(status_code=403, detail=f"This action requires the {role.value} role")
    if actor.org_id is None:
        raise HTTPException(status_code=403, detail="Organization membership is required")
    return actor


async def individual_owner_id(feature: str) -> int:
    owner = current_user()
    if owner.role is not UserRole.INDIVIDUAL:
        raise HTTPException(status_code=403, detail=f"{feature} are only available to individuals")
    return owner.id


async def development_owner_id() -> int:
    """Compatibility boundary for personal receipt routes during their auth migration."""
    return await individual_owner_id("Personal receipts")
