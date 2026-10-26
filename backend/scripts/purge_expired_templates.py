from __future__ import annotations

import asyncio
import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from app.db.models import AuditEvent, FaceTemplate
from app.db.session import get_engine, get_sessionmaker


async def _run() -> None:
    now = datetime.now(UTC)
    async with get_sessionmaker()() as db:
        templates = list(
            (
                await db.scalars(
                    select(FaceTemplate).where(
                        (FaceTemplate.expires_at <= now) | FaceTemplate.revoked_at.is_not(None)
                    )
                )
            ).all()
        )
        for template in templates:
            db.add(
                AuditEvent(
                    actor_user_id=None,
                    action="face_templates.retention_delete",
                    entity_type="face_template",
                    entity_id=str(template.id),
                    before={
                        "student_id": str(template.student_id),
                        "model_version": template.model_version,
                        "expires_at": template.expires_at.isoformat()
                        if template.expires_at
                        else None,
                        "revoked_at": template.revoked_at.isoformat()
                        if template.revoked_at
                        else None,
                    },
                    after={"deleted": True, "reason": "retention_or_revocation"},
                    request_id=f"retention-job:{uuid.uuid4()}",
                    ip_hash="",
                )
            )
            await db.delete(template)
        await db.commit()
    print(f"Deleted {len(templates)} expired or revoked face template(s).")
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(_run())
