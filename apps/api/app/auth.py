"""Password authentication and request-scoped principal resolution for P5."""

import base64
import hashlib
import hmac
import os
import secrets
from contextvars import ContextVar, Token
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field
from shared.enums import UserRole
from shared.models import User
from sqlalchemy import select

from app.database import session_factory

router = APIRouter(prefix="/auth", tags=["auth"])
_principal: ContextVar[User | None] = ContextVar("principal", default=None)
_iterations = 600_000


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=320, pattern=r"^[^\s@]+@[^\s@]+\.[^\s@]+$")
    password: str = Field(min_length=12, max_length=256)


class AuthenticatedUser(BaseModel):
    id: int
    email: str
    role: UserRole
    org_id: int | None


class Session(AuthenticatedUser):
    access_token: str


def _secret() -> bytes:
    value = os.environ.get("AUTH_SECRET")
    if not value:
        raise RuntimeError("AUTH_SECRET must be configured")
    return value.encode()


def hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _iterations)
    return f"pbkdf2_sha256${_iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, encoded: str | None) -> bool:
    if not encoded:
        return False
    try:
        scheme, iterations, salt, digest = encoded.split("$", 3)
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt), int(iterations)
        ).hex()
    except (TypeError, ValueError):
        return False
    return scheme == "pbkdf2_sha256" and hmac.compare_digest(candidate, digest)


def issue_token(user: User) -> str:
    expires = int((datetime.now(UTC) + timedelta(hours=12)).timestamp())
    payload = f"{user.id}.{expires}".encode()
    signature = hmac.new(_secret(), payload, hashlib.sha256).digest()
    return base64.urlsafe_b64encode(payload + b"." + signature).decode().rstrip("=")


async def user_from_bearer(authorization: str | None) -> User | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.removeprefix("Bearer ")
    try:
        raw = base64.urlsafe_b64decode(token + "=" * (-len(token) % 4))
        payload, signature = raw.rsplit(b".", 1)
        user_id, expires = payload.decode().split(".", 1)
        expected_signature = hmac.new(_secret(), payload, hashlib.sha256).digest()
        valid = hmac.compare_digest(expected_signature, signature)
        if not valid or int(expires) < int(datetime.now(UTC).timestamp()):
            return None
    except (UnicodeDecodeError, ValueError):
        return None
    async with session_factory()() as db:
        return await db.get(User, int(user_id))


async def authenticate_request(request: Request) -> Token[User | None]:
    return _principal.set(await user_from_bearer(request.headers.get("Authorization")))


def clear_principal(token: Token[User | None]) -> None:
    _principal.reset(token)


def current_user() -> User:
    user = _principal.get()
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required"
        )
    return user


def serialize(user: User) -> AuthenticatedUser:
    return AuthenticatedUser(id=user.id, email=user.email, role=user.role, org_id=user.org_id)


@router.post("/register", response_model=Session, status_code=status.HTTP_201_CREATED)
async def register(credentials: Credentials) -> Session:
    """Create an individual account; organization roles are provisioned by an administrator."""
    async with session_factory()() as db:
        existing = await db.scalar(select(User).where(User.email == str(credentials.email).lower()))
        if existing is not None:
            raise HTTPException(status_code=409, detail="An account already exists for this email")
        user = User(
            email=str(credentials.email).lower(),
            password_hash=hash_password(credentials.password),
            role=UserRole.INDIVIDUAL,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    return Session(**serialize(user).model_dump(), access_token=issue_token(user))


@router.post("/login", response_model=Session)
async def login(credentials: Credentials) -> Session:
    async with session_factory()() as db:
        user = await db.scalar(select(User).where(User.email == str(credentials.email).lower()))
    if user is None or not verify_password(credentials.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    return Session(**serialize(user).model_dump(), access_token=issue_token(user))


@router.get("/me", response_model=AuthenticatedUser)
async def me() -> AuthenticatedUser:
    return serialize(current_user())
