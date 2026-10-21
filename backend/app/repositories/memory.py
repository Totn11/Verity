from __future__ import annotations

import threading
import uuid
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime

from app.db.models import (
    AttendanceEvent,
    AttendanceKind,
    AuditEvent,
    Person,
    Room,
)


class _MemoryRepository:
    def __init__(self) -> None:
        self._lock = threading.RLock()

    @staticmethod
    def _validate_changes(model: type, changes: Mapping[str, object]) -> None:
        for name in changes:
            if name == "id" or name not in model.__table__.columns:
                raise ValueError(f"Cannot update field {name!r}.")

    @staticmethod
    def _apply_changes(row: object, changes: Mapping[str, object]) -> None:
        for name, value in changes.items():
            setattr(row, name, value)


class InMemoryPeopleRepository(_MemoryRepository):
    def __init__(self, people: Iterable[Person] = ()) -> None:
        super().__init__()
        self._people = {person.id: person for person in people if person.id is not None}

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Person]:
        with self._lock:
            rows = sorted(self._people.values(), key=lambda person: (person.full_name, person.id))
            return rows[offset : offset + limit]

    async def list_page(
        self,
        *,
        limit: int,
        cursor: Mapping[str, str] | None,
        query: str | None,
        status: str | None,
    ) -> list[Person]:
        term = query.strip().casefold() if query else ""
        with self._lock:
            rows = [
                person
                for person in self._people.values()
                if (not term or term in " ".join(
                    (person.full_name, person.email, person.external_ref)
                ).casefold())
                and (
                    not status
                    or getattr(person.status, "value", person.status) == status
                )
            ]
            rows.sort(key=lambda person: (person.full_name, person.id))
            if cursor:
                name = cursor.get("name")
                raw_id = cursor.get("id")
                if name is None or raw_id is None:
                    raise ValueError("Invalid cursor.")
                try:
                    person_id = uuid.UUID(raw_id)
                except ValueError as error:
                    raise ValueError("Invalid cursor.") from error
                rows = [
                    person
                    for person in rows
                    if (person.full_name, person.id) > (name, person_id)
                ]
            return rows[: limit + 1]

    async def get(self, person_id: uuid.UUID) -> Person | None:
        with self._lock:
            return self._people.get(person_id)

    async def create(self, person: Person) -> Person:
        with self._lock:
            if person.id is None:
                person.id = uuid.uuid4()
            now = datetime.now(UTC)
            if person.created_at is None:
                person.created_at = now
            if person.updated_at is None:
                person.updated_at = now
            self._people[person.id] = person
            return person

    async def update(
        self, person_id: uuid.UUID, changes: Mapping[str, object]
    ) -> Person | None:
        self._validate_changes(Person, changes)
        with self._lock:
            person = self._people.get(person_id)
            if person is None:
                return None
            self._apply_changes(person, changes)
            person.updated_at = datetime.now(UTC)
            return person


class InMemoryRoomsRepository(_MemoryRepository):
    def __init__(self, rooms: Iterable[Room] = ()) -> None:
        super().__init__()
        self._rooms = {room.id: room for room in rooms if room.id is not None}

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Room]:
        with self._lock:
            rows = sorted(self._rooms.values(), key=lambda room: (room.code, room.id))
            return rows[offset : offset + limit]

    async def list_page(
        self, *, limit: int, cursor: Mapping[str, str] | None
    ) -> list[Room]:
        with self._lock:
            rows = sorted(self._rooms.values(), key=lambda room: (room.code, room.id))
            if cursor:
                code = cursor.get("code")
                raw_id = cursor.get("id")
                if code is None or raw_id is None:
                    raise ValueError("Invalid cursor.")
                try:
                    room_id = uuid.UUID(raw_id)
                except ValueError as error:
                    raise ValueError("Invalid cursor.") from error
                rows = [
                    room for room in rows if (room.code, room.id) > (code, room_id)
                ]
            return rows[: limit + 1]

    async def get(self, room_id: uuid.UUID) -> Room | None:
        with self._lock:
            return self._rooms.get(room_id)

    def get_cached(self, room_id: uuid.UUID) -> Room | None:
        with self._lock:
            return self._rooms.get(room_id)

    async def create(self, room: Room) -> Room:
        with self._lock:
            if room.id is None:
                room.id = uuid.uuid4()
            self._rooms[room.id] = room
            return room

    async def update(self, room_id: uuid.UUID, changes: Mapping[str, object]) -> Room | None:
        self._validate_changes(Room, changes)
        with self._lock:
            room = self._rooms.get(room_id)
            if room is None:
                return None
            self._apply_changes(room, changes)
            return room


class InMemoryAttendanceRepository(_MemoryRepository):
    def __init__(
        self,
        events: Iterable[AttendanceEvent] = (),
        *,
        rooms: InMemoryRoomsRepository | None = None,
    ) -> None:
        super().__init__()
        self._events = {
            event.id: event for event in events if event.id is not None
        }
        self._rooms = rooms

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[AttendanceEvent]:
        with self._lock:
            rows = sorted(
                self._events.values(),
                key=lambda event: (event.occurred_at or datetime.min.replace(tzinfo=UTC), event.id),
                reverse=True,
            )
            return rows[offset : offset + limit]

    async def list_page(
        self,
        *,
        limit: int,
        cursor: Mapping[str, str] | None,
        person_id: uuid.UUID | None,
        from_time: datetime | None,
        to_time: datetime | None,
    ) -> list[AttendanceEvent]:
        with self._lock:
            rows = [
                event
                for event in self._events.values()
                if (person_id is None or event.person_id == person_id)
                and (from_time is None or event.occurred_at >= from_time)
                and (to_time is None or event.occurred_at <= to_time)
            ]
            rows.sort(
                key=lambda event: (
                    event.occurred_at or datetime.min.replace(tzinfo=UTC),
                    event.id,
                ),
                reverse=True,
            )
            if cursor:
                raw_time = cursor.get("occurred_at")
                raw_id = cursor.get("id")
                if raw_time is None or raw_id is None:
                    raise ValueError("Invalid cursor.")
                try:
                    occurred_at = datetime.fromisoformat(raw_time)
                    event_id = uuid.UUID(raw_id)
                except ValueError as error:
                    raise ValueError("Invalid cursor.") from error
                if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
                    raise ValueError("Invalid cursor.")
                rows = [
                    event
                    for event in rows
                    if (event.occurred_at, event.id) < (occurred_at, event_id)
                ]
            return rows[: limit + 1]

    async def attendance_summary_page(
        self,
        *,
        limit: int,
        cursor: Mapping[str, str] | None,
        from_time: datetime | None,
        to_time: datetime | None,
    ) -> list[dict[str, object]]:
        groups: dict[tuple[datetime, str, str], dict[str, object]] = {}
        with self._lock:
            for event in self._events.values():
                occurred_at = event.occurred_at or datetime.now(UTC)
                if from_time is not None and occurred_at < from_time:
                    continue
                if to_time is not None and occurred_at > to_time:
                    continue
                day = occurred_at.astimezone(UTC).replace(
                    hour=0, minute=0, second=0, microsecond=0
                )
                room = event.room
                if room is None and event.room_id is not None and self._rooms is not None:
                    room = self._rooms.get_cached(event.room_id)
                room_code = room.code if room is not None else None
                room_name = room.name if room is not None else None
                room_key = room_code or ""
                room_id_key = str(event.room_id) if event.room_id is not None else ""
                key = (day, room_key, room_id_key)
                summary = groups.setdefault(
                    key,
                    {
                        "day": day,
                        "room_id": event.room_id,
                        "room_code": room_code,
                        "room_name": room_name,
                        "check_ins": 0,
                        "check_outs": 0,
                    },
                )
                field = (
                    "check_ins"
                    if event.kind == AttendanceKind.CHECK_IN
                    else "check_outs"
                )
                summary[field] = int(summary[field]) + 1
        rows = [(key, summary) for key, summary in groups.items()]
        rows.sort(key=lambda item: (-item[0][0].timestamp(), item[0][1], item[0][2]))
        if cursor:
            raw_day = cursor.get("day")
            room_key = cursor.get("room_key")
            room_id_key = cursor.get("room_id_key")
            if raw_day is None or room_key is None or room_id_key is None:
                raise ValueError("Invalid cursor.")
            try:
                day = datetime.fromisoformat(raw_day)
            except ValueError as error:
                raise ValueError("Invalid cursor.") from error
            if day.tzinfo is None or day.utcoffset() is None:
                raise ValueError("Invalid cursor.")
            rows = [
                item
                for item in rows
                if item[0][0] < day
                or (
                    item[0][0] == day
                    and (item[0][1], item[0][2]) > (room_key, room_id_key)
                )
            ]
        return [summary for _, summary in rows[: limit + 1]]

    async def get(self, event_id: uuid.UUID) -> AttendanceEvent | None:
        with self._lock:
            return self._events.get(event_id)

    async def create(self, event: AttendanceEvent) -> AttendanceEvent:
        with self._lock:
            if event.id is None:
                event.id = uuid.uuid4()
            now = datetime.now(UTC)
            if event.occurred_at is None:
                event.occurred_at = now
            if event.created_at is None:
                event.created_at = now
            self._events[event.id] = event
            return event

    async def update(
        self, event_id: uuid.UUID, changes: Mapping[str, object]
    ) -> AttendanceEvent | None:
        self._validate_changes(AttendanceEvent, changes)
        with self._lock:
            event = self._events.get(event_id)
            if event is None:
                return None
            self._apply_changes(event, changes)
            return event

    async def record_event(self, event: AttendanceEvent) -> AttendanceEvent:
        with self._lock:
            if event.source_event_id is not None:
                existing = next(
                    (
                        saved
                        for saved in self._events.values()
                        if saved.source == event.source
                        and saved.source_event_id == event.source_event_id
                    ),
                    None,
                )
                if existing is not None:
                    return existing
            if event.id is None:
                event.id = uuid.uuid4()
            now = datetime.now(UTC)
            if event.occurred_at is None:
                event.occurred_at = now
            if event.created_at is None:
                event.created_at = now
            self._events[event.id] = event
            return event

    async def current_occupancy(self, room_id: uuid.UUID) -> int:
        with self._lock:
            latest_by_person: dict[uuid.UUID, AttendanceEvent] = {}
            for event in self._events.values():
                current = latest_by_person.get(event.person_id)
                event_order = (
                    event.occurred_at or datetime.min.replace(tzinfo=UTC),
                    event.created_at or datetime.min.replace(tzinfo=UTC),
                    event.id,
                )
                current_order = (
                    (current.occurred_at or datetime.min.replace(tzinfo=UTC)),
                    (current.created_at or datetime.min.replace(tzinfo=UTC)),
                    current.id,
                ) if current is not None else None
                if current_order is None or event_order > current_order:
                    latest_by_person[event.person_id] = event
            return sum(
                1
                for event in latest_by_person.values()
                if event.kind == AttendanceKind.CHECK_IN and event.room_id == room_id
            )

    async def person_timeline(self, person_id: uuid.UUID) -> list[AttendanceEvent]:
        with self._lock:
            return sorted(
                (event for event in self._events.values() if event.person_id == person_id),
                key=lambda event: (
                    event.occurred_at or datetime.min.replace(tzinfo=UTC),
                    event.created_at or datetime.min.replace(tzinfo=UTC),
                    event.id,
                ),
                reverse=True,
            )


class InMemoryAuditRepository(_MemoryRepository):
    def __init__(self, events: Iterable[AuditEvent] = ()) -> None:
        super().__init__()
        self._events = {event.id: event for event in events if event.id is not None}
        self._next_id = max(self._events, default=0) + 1

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[AuditEvent]:
        with self._lock:
            rows = sorted(
                self._events.values(),
                key=lambda event: (
                    event.created_at or datetime.min.replace(tzinfo=UTC),
                    event.id,
                ),
                reverse=True,
            )
            return rows[offset : offset + limit]

    async def get(self, event_id: int) -> AuditEvent | None:
        with self._lock:
            return self._events.get(event_id)

    async def create(self, event: AuditEvent) -> AuditEvent:
        with self._lock:
            if event.id is None:
                event.id = self._next_id
                self._next_id += 1
            if event.created_at is None:
                event.created_at = datetime.now(UTC)
            self._events[event.id] = event
            return event

    async def update(
        self, event_id: int, changes: Mapping[str, object]
    ) -> AuditEvent | None:
        self._validate_changes(AuditEvent, changes)
        with self._lock:
            event = self._events.get(event_id)
            if event is None:
                return None
            self._apply_changes(event, changes)
            return event
