from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.models import AttendanceKind, EventSource, PersonStatus

T = TypeVar("T")


class Page(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: str | None


class PersonCreate(BaseModel):
    external_ref: str = Field(min_length=1)
    full_name: str = Field(min_length=1, max_length=255)
    email: str = Field(min_length=1, max_length=320)
    phone: str = Field(min_length=1, max_length=64)
    department: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1, max_length=255)
    status: PersonStatus
    photo_url: str | None = None


class PersonUpdate(BaseModel):
    external_ref: str | None = Field(default=None, min_length=1)
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    email: str | None = Field(default=None, min_length=1, max_length=320)
    phone: str | None = Field(default=None, min_length=1, max_length=64)
    department: str | None = Field(default=None, min_length=1, max_length=255)
    title: str | None = Field(default=None, min_length=1, max_length=255)
    status: PersonStatus | None = None
    photo_url: str | None = None


class PersonRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    external_ref: str
    full_name: str
    email: str
    phone: str
    department: str
    title: str
    status: PersonStatus
    photo_url: str | None
    created_at: datetime
    updated_at: datetime


class PeopleImportRead(BaseModel):
    created: int
    items: list[PersonRead]


class RoomCreate(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    floor: int
    capacity: int = Field(ge=0)
    pos_x: Decimal
    pos_y: Decimal


class RoomRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    code: str
    name: str
    floor: int
    capacity: int
    pos_x: Decimal
    pos_y: Decimal


class AttendanceWrite(BaseModel):
    person_id: uuid.UUID
    room_id: uuid.UUID | None = None
    occurred_at: datetime | None = None

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            raise ValueError("Timestamp must include a timezone.")
        return value.astimezone(UTC)


class AttendanceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    person_id: uuid.UUID
    kind: AttendanceKind
    occurred_at: datetime
    source: EventSource
    source_event_id: str | None
    room_id: uuid.UUID | None
    actor_user_id: uuid.UUID | None
    created_at: datetime


class AttendanceSummaryRead(BaseModel):
    day: datetime
    room_id: uuid.UUID | None
    room_code: str | None
    room_name: str | None
    check_ins: int
    check_outs: int
