import enum


class UserRole(enum.StrEnum):
    INDIVIDUAL = "individual"
    EMPLOYEE = "employee"
    APPROVER = "approver"
    ADMIN = "admin"


class RequestStatus(enum.StrEnum):
    DRAFT = "draft"
    SUBMITTED = "submitted"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID = "paid"


class OutboundRequestStatus(enum.StrEnum):
    DRAFT = "draft"
    GENERATED = "generated"
    SENT = "sent"


class PayoutStatus(enum.StrEnum):
    PENDING = "pending"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
