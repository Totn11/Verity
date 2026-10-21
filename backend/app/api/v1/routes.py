from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Depends, File, Header, HTTPException, Query, Request, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.exc import IntegrityError

from app.auth.dependencies import require_role
from app.db.models import (
    AttendanceEvent,
    AttendanceKind,
    EventSource,
    Person,
    PersonStatus,
    Room,
    User,
)
from app.repositories import RepositorySet, get_repositories
from app.repositories.cursors import decode_cursor, encode_cursor
from app.services.audit import AuditService
from app.api.v1.schemas import (
    AttendanceRead,
    AttendanceSummaryRead,
    AttendanceWrite,
    Page,
    PersonCreate,
    PersonRead,
    PersonUpdate,
    PeopleImportRead,
    RoomCreate,
    RoomRead,
)

router = APIRouter(prefix="/api/v1")

people_write_guard = require_role("admin")
people_read = APIRouter(
    prefix="/people",
    dependencies=[Depends(require_role("admin", "staff"))],
)
people_write = APIRouter(
    prefix="/people",
    dependencies=[Depends(people_write_guard)],
)
rooms_write = APIRouter(
    prefix="/rooms",
    dependencies=[Depends(require_role("admin"))],
)
rooms_read = APIRouter(
    prefix="/rooms",
    dependencies=[Depends(require_role("admin", "staff"))],
)
attendance_read = APIRouter(
    prefix="/attendance",
    dependencies=[Depends(require_role("admin", "staff"))],
)
attendance_write_guard = require_role("admin", "staff")
attendance_write = APIRouter(
    prefix="/attendance",
    dependencies=[Depends(attendance_write_guard)],
)
reports_read = APIRouter(
    prefix="/reports",
    dependencies=[Depends(require_role("admin", "staff"))],
)

DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 100
MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_ROWS = 1000
PEOPLE_IMPORT_COLUMNS = (
    "external_ref",
    "full_name",
    "email",
    "phone",
    "department",
    "title",
    "status",
)
OPTIONAL_PEOPLE_IMPORT_COLUMNS = {"photo_url"}


def _read_cursor(cursor: str | None) -> dict[str, str] | None:
    try:
        return decode_cursor(cursor)
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


def _page(
    rows: list[Any],
    limit: int,
    cursor_for: Any,
) -> dict[str, Any]:
    has_more = len(rows) > limit
    items = rows[:limit]
    next_cursor = encode_cursor(cursor_for(items[-1])) if has_more and items else None
    return {"items": items, "next_cursor": next_cursor}


def _normalize_query_timestamp(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None or value.utcoffset() is None:
        raise HTTPException(
            status_code=422,
            detail="Timestamp must include a timezone.",
        )
    return value.astimezone(UTC)


def _validate_range(
    from_time: datetime | None, to_time: datetime | None
) -> tuple[datetime | None, datetime | None]:
    normalized_from = _normalize_query_timestamp(from_time)
    normalized_to = _normalize_query_timestamp(to_time)
    if normalized_from is not None and normalized_to is not None:
        if normalized_from > normalized_to:
            raise HTTPException(
                status_code=422,
                detail="'from' must be less than or equal to 'to'.",
            )
    return normalized_from, normalized_to


@people_read.get("", response_model=Page[PersonRead])
async def list_people(
    q: str | None = Query(default=None, max_length=255),
    status_filter: PersonStatus | None = Query(default=None, alias="status"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = None,
    repositories: RepositorySet = Depends(get_repositories),
) -> dict[str, Any]:
    rows = await repositories.people.list_page(
        limit=limit,
        cursor=_read_cursor(cursor),
        query=q,
        status=status_filter.value if status_filter is not None else None,
    )
    return _page(
        rows,
        limit,
        lambda person: {"name": person.full_name, "id": str(person.id)},
    )


@people_read.get("/{person_id}", response_model=PersonRead)
async def get_person(
    person_id: uuid.UUID,
    repositories: RepositorySet = Depends(get_repositories),
) -> Person:
    person = await repositories.people.get(person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found.")
    return person


@people_write.post("", response_model=PersonRead, status_code=status.HTTP_201_CREATED)
async def create_person(
    payload: PersonCreate,
    request: Request,
    actor: User = Depends(people_write_guard),
    repositories: RepositorySet = Depends(get_repositories),
) -> Person:
    person = await repositories.people.create(Person(**payload.model_dump()))
    await AuditService(request, repositories.audit).record(
        actor,
        "people.create",
        "person",
        str(person.id),
        {},
        PersonRead.model_validate(person).model_dump(mode="json"),
    )
    return person


@people_write.post("/import", response_model=PeopleImportRead, status_code=status.HTTP_201_CREATED)
async def import_people_csv(
    request: Request,
    file: UploadFile = File(...),
    actor: User = Depends(people_write_guard),
    repositories: RepositorySet = Depends(get_repositories),
) -> PeopleImportRead:
    contents = await file.read(MAX_IMPORT_BYTES + 1)
    if len(contents) > MAX_IMPORT_BYTES:
        raise HTTPException(status_code=413, detail="CSV file must be 5 MiB or smaller.")
    try:
        text_contents = contents.decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text_contents, newline=""), strict=True))
    except (UnicodeDecodeError, csv.Error) as error:
        raise HTTPException(status_code=422, detail="CSV must be valid UTF-8 with valid CSV quoting.") from error
    if not rows:
        raise HTTPException(status_code=422, detail="CSV file is empty.")

    headers = rows[0]
    if (
        len(headers) != len(set(headers))
        or not set(PEOPLE_IMPORT_COLUMNS).issubset(headers)
        or set(headers) - set(PEOPLE_IMPORT_COLUMNS) - OPTIONAL_PEOPLE_IMPORT_COLUMNS
    ):
        required = ", ".join(PEOPLE_IMPORT_COLUMNS)
        raise HTTPException(
            status_code=422,
            detail=f"CSV header must contain exactly these columns, with optional photo_url: {required}.",
        )

    payloads: list[PersonCreate] = []
    seen_refs: set[str] = set()
    seen_emails: set[str] = set()
    for row_number, row in enumerate(rows[1:], start=2):
        if not row or all(not value.strip() for value in row):
            continue
        if len(row) != len(headers):
            raise HTTPException(status_code=422, detail=f"CSV row {row_number} has the wrong number of columns.")
        values = dict(zip(headers, row, strict=True))
        try:
            person_payload = PersonCreate.model_validate(values)
        except ValidationError as error:
            details = "; ".join(
                f"{'.'.join(str(part) for part in issue['loc'])}: {issue['msg']}"
                for issue in error.errors()
            )
            raise HTTPException(status_code=422, detail=f"Invalid CSV row {row_number}: {details}") from error

        external_ref = person_payload.external_ref.casefold()
        email = person_payload.email.casefold()
        if external_ref in seen_refs or email in seen_emails:
            raise HTTPException(status_code=422, detail=f"CSV row {row_number} duplicates an ID or email in the file.")
        seen_refs.add(external_ref)
        seen_emails.add(email)
        payloads.append(person_payload)
        if len(payloads) > MAX_IMPORT_ROWS:
            raise HTTPException(status_code=413, detail=f"CSV may contain at most {MAX_IMPORT_ROWS} people.")

    if not payloads:
        raise HTTPException(status_code=422, detail="CSV contains no people to import.")

    existing_refs: set[str] = set()
    existing_emails: set[str] = set()
    offset = 0
    while True:
        existing_people = await repositories.people.list(limit=100, offset=offset)
        for person in existing_people:
            existing_refs.add(person.external_ref.casefold())
            existing_emails.add(person.email.casefold())
        if len(existing_people) < 100:
            break
        offset += len(existing_people)
    for person_payload in payloads:
        if (
            person_payload.external_ref.casefold() in existing_refs
            or person_payload.email.casefold() in existing_emails
        ):
            raise HTTPException(
                status_code=409,
                detail=f"Person ID or email already exists: {person_payload.external_ref}. No records were imported.",
            )

    created: list[Person] = []
    try:
        for person_payload in payloads:
            person = await repositories.people.create(Person(**person_payload.model_dump()))
            created.append(person)
            await AuditService(request, repositories.audit).record(
                actor,
                "people.import",
                "person",
                str(person.id),
                {},
                PersonRead.model_validate(person).model_dump(mode="json"),
            )
    except IntegrityError as error:
        raise HTTPException(
            status_code=409,
            detail="A person ID or email already exists. No records were imported.",
        ) from error

    return PeopleImportRead(
        created=len(created),
        items=[PersonRead.model_validate(person) for person in created],
    )


@people_write.patch("/{person_id}", response_model=PersonRead)
async def update_person(
    person_id: uuid.UUID,
    payload: PersonUpdate,
    request: Request,
    actor: User = Depends(people_write_guard),
    repositories: RepositorySet = Depends(get_repositories),
) -> Person:
    changes = payload.model_dump(exclude_unset=True)
    non_nullable = set(changes) - {"photo_url"}
    if any(changes[name] is None for name in non_nullable):
        raise HTTPException(status_code=422, detail="Only photo_url may be set to null.")
    before_person = await repositories.people.get(person_id)
    if before_person is None:
        raise HTTPException(status_code=404, detail="Person not found.")
    before = PersonRead.model_validate(before_person).model_dump(mode="json")
    person = await repositories.people.update(person_id, changes)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found.")
    await AuditService(request, repositories.audit).record(
        actor,
        "people.update",
        "person",
        str(person.id),
        before,
        PersonRead.model_validate(person).model_dump(mode="json"),
    )
    return person


@people_write.put("/{person_id}", response_model=PersonRead)
async def replace_person(
    person_id: uuid.UUID,
    payload: PersonCreate,
    request: Request,
    actor: User = Depends(people_write_guard),
    repositories: RepositorySet = Depends(get_repositories),
) -> Person:
    before_person = await repositories.people.get(person_id)
    if before_person is None:
        raise HTTPException(status_code=404, detail="Person not found.")
    before = PersonRead.model_validate(before_person).model_dump(mode="json")
    person = await repositories.people.update(
        person_id, payload.model_dump()
    )
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found.")
    await AuditService(request, repositories.audit).record(
        actor,
        "people.replace",
        "person",
        str(person.id),
        before,
        PersonRead.model_validate(person).model_dump(mode="json"),
    )
    return person


@rooms_read.get("", response_model=Page[RoomRead])
async def list_rooms(
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = None,
    repositories: RepositorySet = Depends(get_repositories),
) -> dict[str, Any]:
    rows = await repositories.rooms.list_page(
        limit=limit,
        cursor=_read_cursor(cursor),
    )
    return _page(
        rows,
        limit,
        lambda room: {"code": room.code, "id": str(room.id)},
    )


@rooms_read.get("/{room_id}", response_model=RoomRead)
async def get_room(
    room_id: uuid.UUID,
    repositories: RepositorySet = Depends(get_repositories),
) -> Room:
    room = await repositories.rooms.get(room_id)
    if room is None:
        raise HTTPException(status_code=404, detail="Room not found.")
    return room


@rooms_write.post("", response_model=RoomRead, status_code=status.HTTP_201_CREATED)
async def create_room(
    payload: RoomCreate,
    request: Request,
    actor: User = Depends(require_role("admin")),
    repositories: RepositorySet = Depends(get_repositories),
) -> Room:
    room = await repositories.rooms.create(Room(**payload.model_dump()))
    await AuditService(request, repositories.audit).record(
        actor,
        "rooms.create",
        "room",
        str(room.id),
        {},
        RoomRead.model_validate(room).model_dump(mode="json"),
    )
    return room


@attendance_read.get("", response_model=Page[AttendanceRead])
async def list_attendance(
    person_id: uuid.UUID | None = None,
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = None,
    repositories: RepositorySet = Depends(get_repositories),
) -> dict[str, Any]:
    normalized_from, normalized_to = _validate_range(from_time, to_time)
    rows = await repositories.attendance.list_page(
        limit=limit,
        cursor=_read_cursor(cursor),
        person_id=person_id,
        from_time=normalized_from,
        to_time=normalized_to,
    )
    return _page(
        rows,
        limit,
        lambda event: {
            "occurred_at": event.occurred_at.isoformat(),
            "id": str(event.id),
        },
    )


async def _record_attendance(
    kind: AttendanceKind,
    payload: AttendanceWrite,
    idempotency_key: str | None,
    user: User,
    repositories: RepositorySet,
    request: Request,
) -> AttendanceEvent:
    person = await repositories.people.get(payload.person_id)
    if person is None:
        raise HTTPException(status_code=404, detail="Person not found.")
    room = None
    if payload.room_id is not None:
        room = await repositories.rooms.get(payload.room_id)
        if room is None:
            raise HTTPException(status_code=404, detail="Room not found.")
    event = AttendanceEvent(
        person_id=payload.person_id,
        kind=kind,
        occurred_at=payload.occurred_at or datetime.now(UTC),
        source=EventSource.MANUAL,
        source_event_id=idempotency_key,
        room_id=payload.room_id,
        actor_user_id=user.id,
    )
    if room is not None:
        event.room = room
    recorded = await repositories.attendance.record_event(event)
    await AuditService(request, repositories.audit).record(
        user,
        f"attendance.{kind.value}",
        "attendance_event",
        str(recorded.id),
        {},
        AttendanceRead.model_validate(recorded).model_dump(mode="json"),
    )
    return recorded


@attendance_write.post(
    "/check-in",
    response_model=AttendanceRead,
    status_code=status.HTTP_201_CREATED,
)
async def check_in(
    payload: AttendanceWrite,
    request: Request,
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=1, max_length=255
    ),
    user: User = Depends(attendance_write_guard),
    repositories: RepositorySet = Depends(get_repositories),
) -> AttendanceEvent:
    return await _record_attendance(
        AttendanceKind.CHECK_IN, payload, idempotency_key, user, repositories, request
    )


@attendance_write.post(
    "/check-out",
    response_model=AttendanceRead,
    status_code=status.HTTP_201_CREATED,
)
async def check_out(
    payload: AttendanceWrite,
    request: Request,
    idempotency_key: str | None = Header(
        default=None, alias="Idempotency-Key", min_length=1, max_length=255
    ),
    user: User = Depends(attendance_write_guard),
    repositories: RepositorySet = Depends(get_repositories),
) -> AttendanceEvent:
    return await _record_attendance(
        AttendanceKind.CHECK_OUT, payload, idempotency_key, user, repositories, request
    )


@reports_read.get(
    "/attendance-summary",
    response_model=Page[AttendanceSummaryRead],
)
async def attendance_summary(
    from_time: datetime | None = Query(default=None, alias="from"),
    to_time: datetime | None = Query(default=None, alias="to"),
    limit: int = Query(default=DEFAULT_PAGE_SIZE, ge=1, le=MAX_PAGE_SIZE),
    cursor: str | None = None,
    repositories: RepositorySet = Depends(get_repositories),
) -> dict[str, Any]:
    normalized_from, normalized_to = _validate_range(from_time, to_time)
    rows = await repositories.attendance.attendance_summary_page(
        limit=limit,
        cursor=_read_cursor(cursor),
        from_time=normalized_from,
        to_time=normalized_to,
    )
    return _page(
        rows,
        limit,
        lambda item: {
            "day": item["day"].isoformat(),
            "room_key": item["room_code"] or "",
            "room_id_key": str(item["room_id"]) if item["room_id"] is not None else "",
        },
    )


for protected_router in (
    people_read,
    people_write,
    rooms_write,
    rooms_read,
    attendance_read,
    attendance_write,
    reports_read,
):
    router.include_router(protected_router)
