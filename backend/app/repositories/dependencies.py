from __future__ import annotations

import os
from collections.abc import AsyncIterator
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.repositories.memory import (
    InMemoryAttendanceRepository,
    InMemoryAuditRepository,
    InMemoryPeopleRepository,
    InMemoryRoomsRepository,
)
from app.repositories.protocols import (
    AttendanceRepository,
    AuditRepository,
    PeopleRepository,
    RoomsRepository,
)
from app.repositories.sql import (
    SqlAttendanceRepository,
    SqlAuditRepository,
    SqlPeopleRepository,
    SqlRoomsRepository,
)


@dataclass(frozen=True)
class RepositorySet:
    people: PeopleRepository
    rooms: RoomsRepository
    attendance: AttendanceRepository
    audit: AuditRepository


def _sql_repositories(session: AsyncSession) -> RepositorySet:
    return RepositorySet(
        people=SqlPeopleRepository(session),
        rooms=SqlRoomsRepository(session),
        attendance=SqlAttendanceRepository(session),
        audit=SqlAuditRepository(session),
    )


_memory_rooms = InMemoryRoomsRepository()
_memory_repositories = RepositorySet(
    people=InMemoryPeopleRepository(),
    rooms=_memory_rooms,
    attendance=InMemoryAttendanceRepository(rooms=_memory_rooms),
    audit=InMemoryAuditRepository(),
)


async def get_repositories() -> AsyncIterator[RepositorySet]:
    """Provide persistent repositories when configured, otherwise shared in-memory repositories."""
    if not os.getenv("DATABASE_URL"):
        yield _memory_repositories
        return

    async with get_sessionmaker()() as session:
        try:
            yield _sql_repositories(session)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
