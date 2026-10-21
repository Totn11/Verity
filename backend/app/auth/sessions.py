from __future__ import annotations

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.db.models import Session as UserSession
from app.db.models import User

COOKIE_NAME = "verity_session"
SESSION_TTL = timedelta(hours=8)
SESSION_TTL_SECONDS = int(SESSION_TTL.total_seconds())


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def hash_ip(request: Request) -> str:
    client_ip = request.client.host if request.client is not None else ""
    return hashlib.sha256(client_ip.encode("utf-8")).hexdigest()


async def create_session(
    user: User,
    request: Request,
    response: Response,
    db: AsyncSession,
) -> str:
    token = secrets.token_urlsafe(48)
    now = datetime.now(UTC)
    db.add(
        UserSession(
            user_id=user.id,
            token_hash=hash_token(token),
            issued_at=now,
            expires_at=now + SESSION_TTL,
            user_agent=request.headers.get("user-agent", ""),
            ip_hash=hash_ip(request),
        )
    )
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=SESSION_TTL_SECONDS,
        expires=SESSION_TTL_SECONDS,
        httponly=True,
        secure=True,
        samesite="lax",
        path="/api",
    )
    return token


async def read_session(request: Request, db: AsyncSession) -> User | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None

    now = datetime.now(UTC)
    result = await db.execute(
        select(UserSession)
        .options(joinedload(UserSession.user))
        .where(
            UserSession.token_hash == hash_token(token),
            UserSession.revoked_at.is_(None),
            UserSession.expires_at > now,
            User.is_active.is_(True),
        )
        .join(UserSession.user)
    )
    session = result.scalar_one_or_none()
    if (
        session is None
        or session.revoked_at is not None
        or session.expires_at <= now
        or not session.user.is_active
    ):
        return None
    return session.user


async def revoke_session(request: Request, db: AsyncSession) -> bool:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return False
    result = await db.execute(
        select(UserSession).where(
            UserSession.token_hash == hash_token(token),
            UserSession.revoked_at.is_(None),
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        return False
    session.revoked_at = datetime.now(UTC)
    return True
