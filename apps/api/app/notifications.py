"""Authenticated in-app workflow notifications."""

from datetime import UTC, datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from shared.models import Notification
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import current_user
from app.database import session_factory

router = APIRouter(prefix="/notifications", tags=["notifications"])


class NotificationDetail(BaseModel):
    id: int
    request_id: int | None
    kind: str
    title: str
    body: str
    read_at: datetime | None
    created_at: datetime


def serialize(notification: Notification) -> NotificationDetail:
    return NotificationDetail(
        id=notification.id,
        request_id=notification.request_id,
        kind=notification.kind,
        title=notification.title,
        body=notification.body,
        read_at=notification.read_at,
        created_at=notification.created_at,
    )


def create_notifications(
    session: AsyncSession,
    user_ids: list[int],
    *,
    request_id: int,
    kind: str,
    title: str,
    body: str,
) -> None:
    """Queue distinct notifications in the caller's workflow transaction."""
    for user_id in set(user_ids):
        session.add(
            Notification(
                user_id=user_id,
                request_id=request_id,
                kind=kind,
                title=title,
                body=body,
            )
        )


@router.get("", response_model=list[NotificationDetail])
async def list_notifications() -> list[NotificationDetail]:
    user = current_user()
    async with session_factory()() as session:
        notifications = list(
            await session.scalars(
                select(Notification)
                .where(Notification.user_id == user.id)
                .order_by(Notification.read_at.is_not(None), Notification.created_at.desc())
            )
        )
    return [serialize(notification) for notification in notifications]


@router.post("/{notification_id}/read", response_model=NotificationDetail)
async def mark_notification_read(notification_id: int) -> NotificationDetail:
    user = current_user()
    async with session_factory()() as session:
        notification = await session.get(Notification, notification_id)
        if notification is None or notification.user_id != user.id:
            raise HTTPException(status_code=404, detail="Notification not found")
        if notification.read_at is None:
            notification.read_at = datetime.now(UTC)
            await session.commit()
        return serialize(notification)
