"""Temporary identity lookup used until authentication is introduced."""

from fastapi import HTTPException
from shared.enums import UserRole
from shared.models import User
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


async def individual_owner_id(feature: str) -> int:
    owner_id = await development_owner_id()
    async with session_factory()() as session:
        owner = await session.get(User, owner_id)
        if owner is None or owner.role is not UserRole.INDIVIDUAL:
            raise HTTPException(
                status_code=403, detail=f"{feature} are only available to individuals"
            )
    return owner_id
