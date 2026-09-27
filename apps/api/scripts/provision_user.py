"""Provision a user and, optionally, its organization from a trusted shell."""

import argparse
import asyncio

from app.auth import hash_password
from app.database import session_factory
from shared.enums import UserRole
from shared.models import Organization, User
from sqlalchemy import select


async def provision(
    email: str, password: str, role: UserRole, organization_name: str | None
) -> None:
    async with session_factory()() as session:
        existing = await session.scalar(select(User).where(User.email == email.lower()))
        if existing is not None:
            raise ValueError(f"A user already exists for {email}")
        organization = None
        if organization_name:
            organization = await session.scalar(
                select(Organization).where(Organization.name == organization_name)
            )
            if organization is None:
                organization = Organization(name=organization_name)
                session.add(organization)
                await session.flush()
        if role is UserRole.INDIVIDUAL and organization is not None:
            raise ValueError("Individual users cannot be assigned to an organization")
        if role is not UserRole.INDIVIDUAL and organization is None:
            raise ValueError("Organization roles require --organization")
        session.add(
            User(
                email=email.lower(),
                password_hash=hash_password(password),
                role=role,
                org_id=organization.id if organization else None,
            )
        )
        await session.commit()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--role", required=True, choices=[role.value for role in UserRole])
    parser.add_argument("--organization")
    args = parser.parse_args()
    asyncio.run(provision(args.email, args.password, UserRole(args.role), args.organization))


if __name__ == "__main__":
    main()
