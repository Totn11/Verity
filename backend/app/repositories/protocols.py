from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime
from typing import Protocol

from app.db.models import AttendanceEvent, AuditEvent, Person, Room


class PeopleRepository(Protocol):
    async def list_page(
        self,
        *,
        limit: int,
        cursor: Mapping[str, str] | None,
        query: str | None,
        status: str | None,
    ) -> list[Person]:
        """Return a keyset page of matching people, with one extra row when another page exists."""

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Person]:
        """Return people ordered by name with pagination applied."""

    async def get(self, person_id: uuid.UUID) -> Person | None:
        """Return the person with this identifier, or None when absent."""

    async def create(self, person: Person) -> Person:
        """Persist and return the supplied person."""

    async def update(
        self, person_id: uuid.UUID, changes: Mapping[str, object]
    ) -> Person | None:
        """Apply named editable field changes, or return None when absent."""


class RoomsRepository(Protocol):
    async def list_page(
        self, *, limit: int, cursor: Mapping[str, str] | None
    ) -> list[Room]:
        """Return a keyset page of rooms ordered by code and identifier."""

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Room]:
        """Return rooms ordered by code with pagination applied."""

    async def get(self, room_id: uuid.UUID) -> Room | None:
        """Return the room with this identifier, or None when absent."""

    async def create(self, room: Room) -> Room:
        """Persist and return the supplied room."""

    async def update(self, room_id: uuid.UUID, changes: Mapping[str, object]) -> Room | None:
        """Apply named editable field changes, or return None when absent."""


class AttendanceRepository(Protocol):
    async def list_page(
        self,
        *,
        limit: int,
        cursor: Mapping[str, str] | None,
        person_id: uuid.UUID | None,
        from_time: datetime | None,
        to_time: datetime | None,
    ) -> list[AttendanceEvent]:
        """Return a filtered keyset page of attendance events newest first."""

    async def attendance_summary_page(
        self,
        *,
        limit: int,
        cursor: Mapping[str, str] | None,
        from_time: datetime | None,
        to_time: datetime | None,
    ) -> list[dict[str, object]]:
        """Return daily per-room attendance counts in stable keyset order."""

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[AttendanceEvent]:
        """Return attendance events newest first with pagination applied."""

    async def get(self, event_id: uuid.UUID) -> AttendanceEvent | None:
        """Return the attendance event with this identifier, or None when absent."""

    async def create(self, event: AttendanceEvent) -> AttendanceEvent:
        """Persist and return an attendance event without idempotency handling."""

    async def update(
        self, event_id: uuid.UUID, changes: Mapping[str, object]
    ) -> AttendanceEvent | None:
        """Apply named editable field changes, or return None when absent."""

    async def record_event(self, event: AttendanceEvent) -> AttendanceEvent:
        """Create an event once per non-null source/source_event_id pair, returning its existing row on replay."""

    async def current_occupancy(self, room_id: uuid.UUID) -> int:
        """Count people whose latest attendance event is a check-in to this room."""

    async def person_timeline(self, person_id: uuid.UUID) -> list[AttendanceEvent]:
        """Return one person's attendance events newest first."""


class AuditRepository(Protocol):
    async def list(self, *, limit: int = 100, offset: int = 0) -> list[AuditEvent]:
        """Return audit events newest first with pagination applied."""

    async def get(self, event_id: int) -> AuditEvent | None:
        """Return the audit event with this identifier, or None when absent."""

    async def create(self, event: AuditEvent) -> AuditEvent:
        """Persist and return the supplied audit event."""

    async def update(self, event_id: int, changes: Mapping[str, object]) -> AuditEvent | None:
        """Apply named field changes, or return None when absent."""
