from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AttendanceSyncOutbox


def enqueue_attendance_event(
    db: AsyncSession,
    *,
    source_event_id: str,
    session_id: uuid.UUID,
    student_id: uuid.UUID,
    mark: str,
    marked_at: datetime,
    actor_user_id: uuid.UUID | None,
    correction_of: str | None = None,
    correction_reason: str | None = None,
) -> AttendanceSyncOutbox:
    event_id = uuid.uuid5(uuid.NAMESPACE_URL, f"verity-attendance:{source_event_id}")
    payload = {
        "event_id": str(event_id),
        "source_event_id": source_event_id,
        "session_id": str(session_id),
        "student_id": str(student_id),
        "mark": mark,
        "marked_at": marked_at.astimezone(UTC).isoformat(),
        "actor_user_id": str(actor_user_id) if actor_user_id else None,
    }
    if correction_reason is not None:
        payload.update(
            {
                "correction": True,
                "correction_of": correction_of,
                "correction_reason": correction_reason,
            }
        )
    event = AttendanceSyncOutbox(
        event_id=event_id,
        payload=payload,
    )
    db.add(event)
    return event


async def sync_pending_outbox(
    db: AsyncSession, *, batch_size: int = 100, timeout_seconds: float = 5.0
) -> dict[str, int]:
    endpoint = os.getenv("VERITY_SYNC_URL", "").strip().rstrip("/")
    token = os.getenv("VERITY_SYNC_TOKEN", "")
    parsed = urlparse(endpoint)
    if not endpoint or not token:
        raise HTTPException(
            status_code=503,
            detail="Set VERITY_SYNC_URL and VERITY_SYNC_TOKEN to enable central synchronization.",
        )
    if parsed.scheme != "https" and parsed.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise HTTPException(status_code=503, detail="Attendance sync requires HTTPS.")
    statement = (
        select(AttendanceSyncOutbox)
        .where(AttendanceSyncOutbox.status == "pending")
        .order_by(AttendanceSyncOutbox.created_at)
        .limit(batch_size)
    )
    events = list((await db.scalars(statement)).all())
    result = {"sent": 0, "conflicts": 0, "retrying": 0}
    for event in events:
        event.attempt_count += 1
        event.last_attempt_at = datetime.now(UTC)
        body = json.dumps(event.payload, separators=(",", ":")).encode()
        request = Request(
            f"{endpoint}/api/v1/sync/attendance",
            data=body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
                "Idempotency-Key": str(event.event_id),
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                if response.status not in (200, 201):
                    event.last_error = f"http_{response.status}"
                    result["retrying"] += 1
                else:
                    event.status = "synced"
                    event.synced_at = datetime.now(UTC)
                    event.last_error = None
                    result["sent"] += 1
        except HTTPError as error:
            if error.code == 409:
                event.status = "conflict"
                event.last_error = "http_409"
                result["conflicts"] += 1
            else:
                event.last_error = f"http_{error.code}"
                result["retrying"] += 1
        except (URLError, TimeoutError, OSError):
            event.last_error = "network_unavailable"
            result["retrying"] += 1
    await db.commit()
    return result
