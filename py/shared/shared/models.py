import datetime as dt
from typing import Any

from sqlalchemy import JSON, Date, DateTime, Enum, ForeignKey, String, Text, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from shared.enums import (
    ExtractionStatus,
    OutboundRequestStatus,
    PayoutStatus,
    RequestStatus,
    UserRole,
)


class Base(DeclarativeBase):
    pass


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    email: Mapped[str] = mapped_column(String(320), unique=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole, name="user_role", native_enum=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Category(Base):
    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int | None] = mapped_column(ForeignKey("organizations.id"))
    name: Mapped[str] = mapped_column(String(100))


class ReimbursementRequest(Base):
    __tablename__ = "reimbursement_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    org_id: Mapped[int] = mapped_column(ForeignKey("organizations.id"))
    employee_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    status: Mapped[RequestStatus] = mapped_column(
        Enum(RequestStatus, name="request_status", native_enum=True),
        default=RequestStatus.DRAFT,
    )
    synopsis: Mapped[str | None] = mapped_column(Text)
    currency: Mapped[str] = mapped_column(String(3))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Receipt(Base):
    __tablename__ = "receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    request_id: Mapped[int | None] = mapped_column(ForeignKey("reimbursement_requests.id"))
    image_key: Mapped[str] = mapped_column(String(512))
    raw_extraction: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    merchant: Mapped[str | None] = mapped_column(String(255))
    date: Mapped[dt.date | None] = mapped_column(Date)
    currency: Mapped[str | None] = mapped_column(String(3))
    total_cents: Mapped[int | None] = mapped_column()
    tax_cents: Mapped[int | None] = mapped_column()
    extraction_status: Mapped[ExtractionStatus] = mapped_column(
        Enum(ExtractionStatus, name="extraction_status", native_enum=True),
        default=ExtractionStatus.PENDING,
        server_default=ExtractionStatus.PENDING.value,
    )
    extraction_error: Mapped[str | None] = mapped_column(Text)
    categorization_status: Mapped[ExtractionStatus] = mapped_column(
        Enum(ExtractionStatus, name="extraction_status", native_enum=True),
        default=ExtractionStatus.PENDING,
        server_default=ExtractionStatus.PENDING.value,
    )
    categorization_error: Mapped[str | None] = mapped_column(Text)
    confirmed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    receipt_id: Mapped[int] = mapped_column(ForeignKey("receipts.id"))
    description: Mapped[str] = mapped_column(String(255))
    amount_cents: Mapped[int] = mapped_column()
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"))
    needs_category_review: Mapped[bool] = mapped_column(default=True, server_default="true")


class OutboundRequest(Base):
    __tablename__ = "outbound_requests"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    synopsis: Mapped[str | None] = mapped_column(Text)
    artifact: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    external_payer: Mapped[str | None] = mapped_column(String(255))
    generation_status: Mapped[ExtractionStatus] = mapped_column(
        Enum(ExtractionStatus, name="extraction_status", native_enum=True),
        default=ExtractionStatus.PENDING,
        server_default=ExtractionStatus.PENDING.value,
    )
    generation_error: Mapped[str | None] = mapped_column(Text)
    status: Mapped[OutboundRequestStatus] = mapped_column(
        Enum(OutboundRequestStatus, name="outbound_request_status", native_enum=True),
        default=OutboundRequestStatus.DRAFT,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    sent_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class OutboundRequestItem(Base):
    __tablename__ = "outbound_request_items"

    outbound_request_id: Mapped[int] = mapped_column(
        ForeignKey("outbound_requests.id"), primary_key=True
    )
    line_item_id: Mapped[int] = mapped_column(ForeignKey("line_items.id"), primary_key=True)


class Payout(Base):
    __tablename__ = "payouts"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int] = mapped_column(ForeignKey("reimbursement_requests.id"))
    provider: Mapped[str] = mapped_column(String(50))
    idempotency_key: Mapped[str] = mapped_column(String(255), unique=True)
    status: Mapped[PayoutStatus] = mapped_column(
        Enum(PayoutStatus, name="payout_status", native_enum=True),
        default=PayoutStatus.PENDING,
    )
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class AuditEvent(Base):
    """Append-only: rows are inserted, never updated or deleted."""

    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(primary_key=True)
    request_id: Mapped[int | None] = mapped_column(ForeignKey("reimbursement_requests.id"))
    actor_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(100))
    payload: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
