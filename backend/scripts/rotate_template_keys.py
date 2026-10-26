from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.db.models import AuditEvent, FaceTemplate
from app.db.session import get_engine, get_sessionmaker
from app.services.biometric_crypto import TemplateCipher


async def _run() -> None:
    cipher = TemplateCipher.from_environment()
    rotated = 0
    async with get_sessionmaker()() as db:
        templates = list(
            (
                await db.scalars(
                    select(FaceTemplate).where(
                        FaceTemplate.encryption_key_id != cipher.active_key_id
                    )
                )
            ).all()
        )
        for template in templates:
            embedding = cipher.decrypt(
                template.encrypted_template,
                template.encryption_key_id,
                template.student_id,
                template.model_version,
            )
            encrypted = cipher.encrypt(
                embedding,
                template.student_id,
                template.model_version,
            )
            before_key_id = template.encryption_key_id
            template.encrypted_template = encrypted.ciphertext
            template.encryption_key_id = encrypted.key_id
            db.add(
                AuditEvent(
                    actor_user_id=None,
                    action="face_templates.key_rotation",
                    entity_type="face_template",
                    entity_id=str(template.id),
                    before={"encryption_key_id": before_key_id},
                    after={"encryption_key_id": encrypted.key_id},
                    request_id=f"key-rotation:{uuid.uuid4()}",
                    ip_hash="",
                )
            )
            rotated += 1
        await db.commit()
    print(f"Re-encrypted {rotated} face template(s) with the active key.")
    await get_engine().dispose()


if __name__ == "__main__":
    asyncio.run(_run())
