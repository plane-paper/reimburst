"""Temporary identity lookup used until authentication is introduced."""

from fastapi import HTTPException
from shared.enums import UserRole
from shared.models import Organization, User
from sqlalchemy import select

from app.database import session_factory

DEVELOPMENT_EMAIL = "local@reimburst.test"


async def development_owner_id() -> int:
    """Return the local individual account used by the unauthenticated prototype."""
    async with session_factory()() as session:
        owner = await session.scalar(select(User).where(User.email == DEVELOPMENT_EMAIL))
        if owner is None:
            owner = User(email=DEVELOPMENT_EMAIL, role=UserRole.INDIVIDUAL)
            session.add(owner)
            await session.commit()
            await session.refresh(owner)
        return owner.id


async def development_organization_actor(role: UserRole) -> User:
    """Return a seeded organization actor for local organization-flow development."""
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


async def individual_owner_id(feature: str) -> int:
    owner_id = await development_owner_id()
    async with session_factory()() as session:
        owner = await session.get(User, owner_id)
        if owner is None or owner.role is not UserRole.INDIVIDUAL:
            raise HTTPException(
                status_code=403, detail=f"{feature} are only available to individuals"
            )
    return owner_id
