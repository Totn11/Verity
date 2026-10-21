from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import Request

from app.auth.sessions import hash_ip
from app.db.models import AuditEvent, User
from app.repositories.protocols import AuditRepository


class AuditService:
    def __init__(self, request: Request, repository: AuditRepository) -> None:
        self._request = request
        self._repository = repository

    async def record(
        self,
        actor: User | None,
        action: str,
        entity_type: str,
        entity_id: str,
        before: Mapping[str, Any],
        after: Mapping[str, Any],
    ) -> AuditEvent:
        # Audit and business writes share the request transaction so either both commit or both roll back.
        event = AuditEvent(
            actor_user_id=actor.id if actor is not None else None,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            before=dict(before),
            after=dict(after),
            request_id=self._request.state.request_id,
            ip_hash=hash_ip(self._request),
        )
        return await self._repository.create(event)
