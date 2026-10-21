from __future__ import annotations

from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.sessions import hash_ip
from app.db.models import AuditEvent

LOGIN_FAILURE_ACTION = "auth.login_failed"
LOGIN_SUCCESS_ACTION = "auth.login"


async def count_recent_login_failures(
    request: Request,
    db: AsyncSession,
    *,
    since: datetime,
) -> int:
    ip_hash = hash_ip(request)
    lock_id = int.from_bytes(bytes.fromhex(ip_hash[:16]), byteorder="big", signed=True)
    await db.execute(
        text("SELECT pg_advisory_xact_lock(:lock_id)"),
        {"lock_id": lock_id},
    )
    result = await db.execute(
        select(func.count(AuditEvent.id)).where(
            AuditEvent.action == LOGIN_FAILURE_ACTION,
            AuditEvent.ip_hash == ip_hash,
            AuditEvent.created_at >= since,
        )
    )
    return int(result.scalar_one())


def utc_now() -> datetime:
    return datetime.now(UTC)
