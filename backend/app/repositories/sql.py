from __future__ import annotations

import uuid
from collections.abc import Mapping
from datetime import datetime

from sqlalchemy import String, and_, case, cast, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AttendanceEvent, AttendanceKind, AuditEvent, Person, Room
from app.repositories.protocols import (
    AttendanceRepository,
    AuditRepository,
    PeopleRepository,
    RoomsRepository,
)


class _SqlRepository:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def _update(self, model, object_id, changes: Mapping[str, object]):
        row = await self.session.get(model, object_id)
        if row is None:
            return None
        for name, value in changes.items():
            if name == "id" or name not in model.__table__.columns:
                raise ValueError(f"Cannot update field {name!r}.")
            setattr(row, name, value)
        await self.session.flush()
        return row


class SqlPeopleRepository(_SqlRepository):
    async def list_page(
        self,
        *,
        limit: int,
        cursor: Mapping[str, str] | None,
        query: str | None,
        status: str | None,
    ) -> list[Person]:
        statement = select(Person)
        if query:
            term = f"%{query.strip()}%"
            statement = statement.where(
                or_(
                    Person.full_name.ilike(term),
                    Person.email.ilike(term),
                    Person.external_ref.ilike(term),
                )
            )
        if status:
            statement = statement.where(Person.status == status)
        if cursor:
            name = cursor.get("name")
            raw_id = cursor.get("id")
            if name is None or raw_id is None:
                raise ValueError("Invalid cursor.")
            try:
                person_id = uuid.UUID(raw_id)
            except ValueError as error:
                raise ValueError("Invalid cursor.") from error
            statement = statement.where(
                or_(Person.full_name > name, and_(Person.full_name == name, Person.id > person_id))
            )
        result = await self.session.scalars(
            statement.order_by(Person.full_name, Person.id).limit(limit + 1)
        )
        return list(result)

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Person]:
        result = await self.session.scalars(
            select(Person).order_by(Person.full_name, Person.id).limit(limit).offset(offset)
        )
        return list(result)

    async def get(self, person_id: uuid.UUID) -> Person | None:
        return await self.session.get(Person, person_id)

    async def create(self, person: Person) -> Person:
        self.session.add(person)
        await self.session.flush()
        return person

    async def update(
        self, person_id: uuid.UUID, changes: Mapping[str, object]
    ) -> Person | None:
        return await self._update(Person, person_id, changes)


class SqlRoomsRepository(_SqlRepository):
    async def list_page(
        self, *, limit: int, cursor: Mapping[str, str] | None
    ) -> list[Room]:
        statement = select(Room)
        if cursor:
            code = cursor.get("code")
            raw_id = cursor.get("id")
            if code is None or raw_id is None:
                raise ValueError("Invalid cursor.")
            try:
                room_id = uuid.UUID(raw_id)
            except ValueError as error:
                raise ValueError("Invalid cursor.") from error
            statement = statement.where(
                or_(Room.code > code, and_(Room.code == code, Room.id > room_id))
            )
        result = await self.session.scalars(
            statement.order_by(Room.code, Room.id).limit(limit + 1)
        )
        return list(result)

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[Room]:
        result = await self.session.scalars(
            select(Room).order_by(Room.code, Room.id).limit(limit).offset(offset)
        )
        return list(result)

    async def get(self, room_id: uuid.UUID) -> Room | None:
        return await self.session.get(Room, room_id)

    async def create(self, room: Room) -> Room:
        self.session.add(room)
        await self.session.flush()
        return room

    async def update(self, room_id: uuid.UUID, changes: Mapping[str, object]) -> Room | None:
        return await self._update(Room, room_id, changes)


class SqlAttendanceRepository(_SqlRepository):
    async def list_page(
        self,
        *,
        limit: int,
        cursor: Mapping[str, str] | None,
        person_id: uuid.UUID | None,
        from_time: datetime | None,
        to_time: datetime | None,
    ) -> list[AttendanceEvent]:
        statement = select(AttendanceEvent)
        if person_id is not None:
            statement = statement.where(AttendanceEvent.person_id == person_id)
        if from_time is not None:
            statement = statement.where(AttendanceEvent.occurred_at >= from_time)
        if to_time is not None:
            statement = statement.where(AttendanceEvent.occurred_at <= to_time)
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
            statement = statement.where(
                or_(
                    AttendanceEvent.occurred_at < occurred_at,
                    and_(
                        AttendanceEvent.occurred_at == occurred_at,
                        AttendanceEvent.id < event_id,
                    ),
                )
            )
        result = await self.session.scalars(
            statement.order_by(
                AttendanceEvent.occurred_at.desc(), AttendanceEvent.id.desc()
            ).limit(limit + 1)
        )
        return list(result)

    async def attendance_summary_page(
        self,
        *,
        limit: int,
        cursor: Mapping[str, str] | None,
        from_time: datetime | None,
        to_time: datetime | None,
    ) -> list[dict[str, object]]:
        day = func.timezone(
            "UTC",
            func.date_trunc(
                "day", func.timezone("UTC", AttendanceEvent.occurred_at)
            ),
        ).label("day")
        room_key = func.coalesce(Room.code, "").label("room_key")
        room_id_key = func.coalesce(cast(Room.id, String), "").label("room_id_key")
        check_ins = func.sum(
            case((AttendanceEvent.kind == AttendanceKind.CHECK_IN, 1), else_=0)
        ).label("check_ins")
        check_outs = func.sum(
            case((AttendanceEvent.kind == AttendanceKind.CHECK_OUT, 1), else_=0)
        ).label("check_outs")
        statement = (
            select(
                day,
                AttendanceEvent.room_id.label("room_id"),
                Room.code.label("room_code"),
                Room.name.label("room_name"),
                room_key,
                room_id_key,
                check_ins,
                check_outs,
            )
            .outerjoin(Room, AttendanceEvent.room_id == Room.id)
        )
        if from_time is not None:
            statement = statement.where(AttendanceEvent.occurred_at >= from_time)
        if to_time is not None:
            statement = statement.where(AttendanceEvent.occurred_at <= to_time)
        if cursor:
            raw_day = cursor.get("day")
            cursor_room_key = cursor.get("room_key")
            cursor_room_id_key = cursor.get("room_id_key")
            if raw_day is None or cursor_room_key is None or cursor_room_id_key is None:
                raise ValueError("Invalid cursor.")
            try:
                cursor_day = datetime.fromisoformat(raw_day)
            except ValueError as error:
                raise ValueError("Invalid cursor.") from error
            if cursor_day.tzinfo is None or cursor_day.utcoffset() is None:
                raise ValueError("Invalid cursor.")
            statement = statement.having(
                or_(
                    day < cursor_day,
                    and_(
                        day == cursor_day,
                        or_(
                            room_key > cursor_room_key,
                            and_(
                                room_key == cursor_room_key,
                                room_id_key > cursor_room_id_key,
                            ),
                        ),
                    ),
                )
            )
        statement = (
            statement.group_by(
                day, AttendanceEvent.room_id, Room.code, Room.name, Room.id
            )
            .order_by(day.desc(), room_key.asc(), room_id_key.asc())
            .limit(limit + 1)
        )
        rows = (await self.session.execute(statement)).mappings()
        return [
            {
                "day": row["day"],
                "room_id": row["room_id"],
                "room_code": row["room_code"],
                "room_name": row["room_name"],
                "check_ins": int(row["check_ins"] or 0),
                "check_outs": int(row["check_outs"] or 0),
            }
            for row in rows
        ]

    async def list(self, *, limit: int = 100, offset: int = 0) -> list[AttendanceEvent]:
        result = await self.session.scalars(
            select(AttendanceEvent)
            .order_by(AttendanceEvent.occurred_at.desc(), AttendanceEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result)

    async def get(self, event_id: uuid.UUID) -> AttendanceEvent | None:
        return await self.session.get(AttendanceEvent, event_id)

    async def create(self, event: AttendanceEvent) -> AttendanceEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def update(
        self, event_id: uuid.UUID, changes: Mapping[str, object]
    ) -> AttendanceEvent | None:
        return await self._update(AttendanceEvent, event_id, changes)

    async def record_event(self, event: AttendanceEvent) -> AttendanceEvent:
        if event.source_event_id is None:
            return await self.create(event)

        if event.id is None:
            event.id = uuid.uuid4()
        values = {
            column.name: getattr(event, column.name)
            for column in AttendanceEvent.__table__.columns
            if getattr(event, column.name, None) is not None
        }
        statement = (
            pg_insert(AttendanceEvent)
            .values(**values)
            .on_conflict_do_nothing(
                index_elements=[
                    AttendanceEvent.source,
                    AttendanceEvent.source_event_id,
                ],
                index_where=AttendanceEvent.source_event_id.is_not(None),
            )
            .returning(AttendanceEvent.id)
        )
        inserted_id = await self.session.scalar(statement)
        if inserted_id is None:
            existing = await self.session.scalar(
                select(AttendanceEvent).where(
                    AttendanceEvent.source == event.source,
                    AttendanceEvent.source_event_id == event.source_event_id,
                )
            )
            if existing is None:
                raise RuntimeError("An idempotent attendance insert conflicted without an existing row.")
            return existing
        inserted_event = await self.session.get(AttendanceEvent, inserted_id)
        if inserted_event is None:
            raise RuntimeError("The inserted attendance event could not be loaded.")
        return inserted_event

    async def current_occupancy(self, room_id: uuid.UUID) -> int:
        latest_events = (
            select(
                AttendanceEvent.person_id.label("person_id"),
                AttendanceEvent.kind.label("kind"),
                AttendanceEvent.room_id.label("room_id"),
                func.row_number()
                .over(
                    partition_by=AttendanceEvent.person_id,
                    order_by=(
                        AttendanceEvent.occurred_at.desc(),
                        AttendanceEvent.created_at.desc(),
                        AttendanceEvent.id.desc(),
                    ),
                )
                .label("event_rank"),
            )
            .subquery()
        )
        result = await self.session.scalar(
            select(func.count())
            .select_from(latest_events)
            .where(
                latest_events.c.event_rank == 1,
                latest_events.c.kind == AttendanceKind.CHECK_IN,
                latest_events.c.room_id == room_id,
            )
        )
        return int(result or 0)

    async def person_timeline(self, person_id: uuid.UUID) -> list[AttendanceEvent]:
        result = await self.session.scalars(
            select(AttendanceEvent)
            .where(AttendanceEvent.person_id == person_id)
            .order_by(AttendanceEvent.occurred_at.desc(), AttendanceEvent.id.desc())
        )
        return list(result)


class SqlAuditRepository(_SqlRepository):
    async def list(self, *, limit: int = 100, offset: int = 0) -> list[AuditEvent]:
        result = await self.session.scalars(
            select(AuditEvent)
            .order_by(AuditEvent.created_at.desc(), AuditEvent.id.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result)

    async def get(self, event_id: int) -> AuditEvent | None:
        return await self.session.get(AuditEvent, event_id)

    async def create(self, event: AuditEvent) -> AuditEvent:
        self.session.add(event)
        await self.session.flush()
        return event

    async def update(
        self, event_id: int, changes: Mapping[str, object]
    ) -> AuditEvent | None:
        return await self._update(AuditEvent, event_id, changes)
