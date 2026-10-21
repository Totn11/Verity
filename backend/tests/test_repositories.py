from __future__ import annotations

import asyncio
import os
import unittest
import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, Mock, patch

from sqlalchemy.dialects import postgresql

from app.db.models import AttendanceEvent, AttendanceKind, EventSource
from app.repositories.dependencies import RepositorySet, get_repositories
from app.repositories.memory import (
    InMemoryAttendanceRepository,
    InMemoryPeopleRepository,
    InMemoryRoomsRepository,
)
from app.repositories.sql import (
    SqlAttendanceRepository,
    SqlAuditRepository,
    SqlPeopleRepository,
    SqlRoomsRepository,
)


def make_event(
    *,
    person_id: uuid.UUID,
    room_id: uuid.UUID | None,
    kind: AttendanceKind,
    occurred_at: datetime,
    source_event_id: str | None = None,
) -> AttendanceEvent:
    return AttendanceEvent(
        person_id=person_id,
        room_id=room_id,
        kind=kind,
        occurred_at=occurred_at,
        source=EventSource.TERMINAL,
        source_event_id=source_event_id,
    )


class InMemoryRepositoryTests(unittest.TestCase):
    def test_record_event_returns_existing_source_event_pair(self) -> None:
        async def exercise() -> None:
            repository = InMemoryAttendanceRepository()
            person_id = uuid.uuid4()
            original = make_event(
                person_id=person_id,
                room_id=uuid.uuid4(),
                kind=AttendanceKind.CHECK_IN,
                occurred_at=datetime.now(UTC),
                source_event_id="terminal-123",
            )
            retry = make_event(
                person_id=person_id,
                room_id=uuid.uuid4(),
                kind=AttendanceKind.CHECK_OUT,
                occurred_at=datetime.now(UTC) + timedelta(minutes=1),
                source_event_id="terminal-123",
            )

            stored = await repository.record_event(original)
            replay = await repository.record_event(retry)

            self.assertIs(replay, stored)
            self.assertEqual(len(await repository.list()), 1)

        asyncio.run(exercise())

    def test_occupancy_uses_only_each_person_latest_event(self) -> None:
        async def exercise() -> None:
            repository = InMemoryAttendanceRepository()
            room_id = uuid.uuid4()
            other_room_id = uuid.uuid4()
            person_in_room = uuid.uuid4()
            person_checked_out = uuid.uuid4()
            person_moved = uuid.uuid4()
            timestamp = datetime.now(UTC)
            events = [
                make_event(
                    person_id=person_in_room,
                    room_id=room_id,
                    kind=AttendanceKind.CHECK_IN,
                    occurred_at=timestamp,
                ),
                make_event(
                    person_id=person_checked_out,
                    room_id=room_id,
                    kind=AttendanceKind.CHECK_IN,
                    occurred_at=timestamp,
                ),
                make_event(
                    person_id=person_checked_out,
                    room_id=room_id,
                    kind=AttendanceKind.CHECK_OUT,
                    occurred_at=timestamp + timedelta(minutes=1),
                ),
                make_event(
                    person_id=person_moved,
                    room_id=room_id,
                    kind=AttendanceKind.CHECK_IN,
                    occurred_at=timestamp,
                ),
                make_event(
                    person_id=person_moved,
                    room_id=other_room_id,
                    kind=AttendanceKind.CHECK_IN,
                    occurred_at=timestamp + timedelta(minutes=1),
                ),
            ]
            for event in events:
                await repository.record_event(event)

            self.assertEqual(await repository.current_occupancy(room_id), 1)
            self.assertEqual(await repository.current_occupancy(other_room_id), 1)
            timeline = await repository.person_timeline(person_moved)
            self.assertEqual(len(timeline), 2)
            self.assertGreater(timeline[0].occurred_at, timeline[1].occurred_at)

        asyncio.run(exercise())

    def test_default_dependency_reuses_in_memory_implementations_without_database_url(self) -> None:
        async def exercise() -> None:
            with patch.dict(os.environ, {}, clear=True):
                first = await anext(get_repositories())
                second = await anext(get_repositories())
            self.assertIs(first, second)
            self.assertIsInstance(first.people, InMemoryPeopleRepository)
            self.assertIsInstance(first.rooms, InMemoryRoomsRepository)
            self.assertIsInstance(first.attendance, InMemoryAttendanceRepository)

        asyncio.run(exercise())

    def test_sql_dependency_yields_all_sql_repositories_and_commits(self) -> None:
        async def exercise() -> None:
            session = Mock()
            session.commit = AsyncMock()
            session.rollback = AsyncMock()
            session_context = AsyncMock()
            session_context.__aenter__.return_value = session
            session_context.__aexit__.return_value = None
            sessionmaker = Mock(return_value=session_context)

            with (
                patch.dict(os.environ, {"DATABASE_URL": "postgresql+asyncpg://test"}, clear=True),
                patch(
                    "app.repositories.dependencies.get_sessionmaker",
                    return_value=sessionmaker,
                ),
            ):
                dependency = get_repositories()
                repositories = await anext(dependency)
                with self.assertRaises(StopAsyncIteration):
                    await anext(dependency)

            self.assertIsInstance(repositories, RepositorySet)
            self.assertIsInstance(repositories.people, SqlPeopleRepository)
            self.assertIsInstance(repositories.rooms, SqlRoomsRepository)
            self.assertIsInstance(repositories.attendance, SqlAttendanceRepository)
            self.assertIsInstance(repositories.audit, SqlAuditRepository)
            session.commit.assert_awaited_once()

        asyncio.run(exercise())


class SqlAttendanceRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_attendance_page_uses_keyset_filter_without_offset(self) -> None:
        occurred_at = datetime.now(UTC)
        session = Mock()
        session.scalars = AsyncMock(return_value=[])

        await SqlAttendanceRepository(session).list_page(
            limit=20,
            cursor={"occurred_at": occurred_at.isoformat(), "id": str(uuid.uuid4())},
            person_id=uuid.uuid4(),
            from_time=occurred_at - timedelta(days=1),
            to_time=occurred_at + timedelta(days=1),
        )

        statement = session.scalars.await_args.args[0]
        rendered = str(statement.compile(dialect=postgresql.dialect()))
        self.assertNotIn(" OFFSET ", rendered)
        self.assertIn("attendance_events.occurred_at <", rendered)
        self.assertIn("attendance_events.person_id =", rendered)
        self.assertIn("LIMIT", rendered)

    async def test_summary_query_uses_daily_utc_groups_and_keyset_order(self) -> None:
        session = Mock()
        execution = Mock()
        execution.mappings.return_value = []
        session.execute = AsyncMock(return_value=execution)

        await SqlAttendanceRepository(session).attendance_summary_page(
            limit=10,
            cursor={
                "day": datetime.now(UTC).isoformat(),
                "room_key": "A-101",
                "room_id_key": str(uuid.uuid4()),
            },
            from_time=None,
            to_time=None,
        )

        statement = session.execute.await_args.args[0]
        rendered = str(statement.compile(dialect=postgresql.dialect()))
        self.assertIn("timezone", rendered)
        self.assertIn("date_trunc", rendered)
        self.assertIn("HAVING", rendered)
        self.assertNotIn(" OFFSET ", rendered)

    async def test_record_event_builds_partial_index_upsert(self) -> None:
        event = make_event(
            person_id=uuid.uuid4(),
            room_id=uuid.uuid4(),
            kind=AttendanceKind.CHECK_IN,
            occurred_at=datetime.now(UTC),
            source_event_id="terminal-123",
        )
        session = Mock()
        session.scalar = AsyncMock(return_value=event.id or uuid.uuid4())
        session.get = AsyncMock(return_value=event)

        result = await SqlAttendanceRepository(session).record_event(event)

        self.assertIs(result, event)
        statement = session.scalar.await_args.args[0]
        self.assertIn("ON CONFLICT (source, source_event_id) WHERE source_event_id IS NOT NULL DO NOTHING", str(statement))
        session.get.assert_awaited_once()

    async def test_record_event_returns_existing_row_when_conflict_insert_does_not_insert(self) -> None:
        event = make_event(
            person_id=uuid.uuid4(),
            room_id=uuid.uuid4(),
            kind=AttendanceKind.CHECK_IN,
            occurred_at=datetime.now(UTC),
            source_event_id="terminal-123",
        )
        existing = make_event(
            person_id=event.person_id,
            room_id=event.room_id,
            kind=AttendanceKind.CHECK_IN,
            occurred_at=event.occurred_at,
            source_event_id=event.source_event_id,
        )
        session = Mock()
        session.scalar = AsyncMock(side_effect=[None, existing])

        result = await SqlAttendanceRepository(session).record_event(event)

        self.assertIs(result, existing)
        self.assertEqual(session.scalar.await_count, 2)

    async def test_current_occupancy_query_ranks_latest_event_per_person(self) -> None:
        session = Mock()
        session.scalar = AsyncMock(return_value=3)

        count = await SqlAttendanceRepository(session).current_occupancy(uuid.uuid4())

        self.assertEqual(count, 3)
        statement = session.scalar.await_args.args[0]
        rendered = str(statement.compile(compile_kwargs={"literal_binds": True}))
        self.assertIn("row_number() OVER (PARTITION BY attendance_events.person_id", rendered)
        self.assertIn("attendance_events.occurred_at DESC", rendered)
        self.assertIn("event_rank = 1", rendered)
        self.assertIn("check_in", rendered)


if __name__ == "__main__":
    unittest.main()
