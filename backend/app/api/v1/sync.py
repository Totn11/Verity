from __future__ import annotations

import hmac
import os
import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    AttendanceMark,
    AttendanceMethod,
    AttendanceSession,
    AttendanceSessionStatus,
    CourseEnrollment,
    SessionAttendanceRecord,
    Student,
    User,
)
from app.db.session import get_session
from app.repositories.sql import SqlAuditRepository
from app.services.audit import AuditService

router = APIRouter(prefix="/api/v1/sync")
SessionDep = Annotated[AsyncSession, Depends(get_session)]


class AttendanceSyncInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    event_id: uuid.UUID
    source_event_id: str = Field(min_length=1, max_length=255)
    session_id: uuid.UUID
    student_id: uuid.UUID
    mark: AttendanceMark
    marked_at: datetime
    actor_user_id: uuid.UUID | None = None
    correction: bool = False
    correction_of: str | None = None
    correction_reason: str | None = Field(default=None, min_length=3, max_length=500)

    @model_validator(mode="after")
    def validate_event(self) -> AttendanceSyncInput:
        expected_id = uuid.uuid5(uuid.NAMESPACE_URL, f"verity-attendance:{self.source_event_id}")
        if self.event_id != expected_id:
            raise ValueError("Event ID does not match its idempotency key.")
        if self.marked_at.tzinfo is None or self.marked_at.utcoffset() is None:
            raise ValueError("Attendance timestamp must include a timezone.")
        if self.correction != (self.correction_reason is not None):
            raise ValueError("A correction must include a reason and non-corrections must not.")
        return self


class AttendanceSyncReceipt(BaseModel):
    event_id: uuid.UUID
    status: str


def _authorized_sync_request(authorization: str | None) -> None:
    expected = os.getenv("VERITY_SYNC_TOKEN", "")
    if not expected:
        raise HTTPException(status_code=503, detail="Central synchronization is not configured.")
    supplied = authorization.removeprefix("Bearer ").strip() if authorization else ""
    if not hmac.compare_digest(supplied, expected):
        raise HTTPException(status_code=401, detail="Synchronization credentials are invalid.")


async def _apply_synced_correction(
    db: AsyncSession,
    request: Request,
    actor: User | None,
    record: SessionAttendanceRecord,
    payload: AttendanceSyncInput,
) -> AttendanceSyncReceipt:
    if payload.correction_of is not None and payload.correction_of != record.source_event_id:
        raise HTTPException(status_code=409, detail="Correction refers to an outdated attendance event.")
    if payload.correction_of is None and record.source_event_id is not None:
        raise HTTPException(status_code=409, detail="Correction omitted the current attendance event version.")
    before = {
        "session_id": str(record.session_id),
        "student_id": str(record.student_id),
        "mark": record.mark.value,
        "source_event_id": record.source_event_id,
        "marked_at": record.marked_at.isoformat(),
    }
    record.mark = payload.mark
    record.method = AttendanceMethod.OFFLINE_SYNC
    record.source_event_id = payload.source_event_id
    record.marked_at = payload.marked_at.astimezone(UTC)
    record.actor_user_id = actor.id if actor is not None else None
    record.corrected_at = datetime.now(UTC)
    after = {
        "session_id": str(record.session_id),
        "student_id": str(record.student_id),
        "mark": record.mark.value,
        "source_event_id": record.source_event_id,
        "marked_at": record.marked_at.isoformat(),
        "correction_reason": payload.correction_reason,
    }
    await AuditService(request, SqlAuditRepository(db)).record(
        actor,
        "attendance_records.sync_correction",
        "attendance_record",
        str(record.id),
        before,
        after,
    )
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="Attendance correction conflicts with a newer event.") from error
    return AttendanceSyncReceipt(event_id=payload.event_id, status="corrected")


@router.post("/attendance", response_model=AttendanceSyncReceipt)
async def receive_attendance_event(
    payload: AttendanceSyncInput,
    request: Request,
    db: SessionDep,
    authorization: Annotated[str | None, Header()] = None,
) -> AttendanceSyncReceipt:
    _authorized_sync_request(authorization)
    prior = await db.scalar(
        select(SessionAttendanceRecord).where(
            SessionAttendanceRecord.source_event_id == payload.source_event_id
        )
    )
    if prior is not None:
        same_record = prior.session_id == payload.session_id and prior.student_id == payload.student_id
        if same_record and prior.mark == payload.mark:
            return AttendanceSyncReceipt(event_id=payload.event_id, status="already_synced")
        if payload.correction and same_record and payload.correction_of == prior.source_event_id:
            actor = await db.get(User, payload.actor_user_id) if payload.actor_user_id else None
            return await _apply_synced_correction(db, request, actor, prior, payload)
        raise HTTPException(status_code=409, detail="Event ID conflicts with an existing attendance mark.")

    session = await db.get(AttendanceSession, payload.session_id)
    student = await db.get(Student, payload.student_id)
    if session is None or student is None or not student.is_active:
        raise HTTPException(status_code=409, detail="Class session or active student is missing on the server.")
    if not payload.correction:
        if payload.marked_at.astimezone(UTC) < session.started_at.astimezone(UTC):
            raise HTTPException(status_code=409, detail="Attendance event predates its class session.")
        if (
            session.status == AttendanceSessionStatus.SCHEDULED
            or (
                session.status == AttendanceSessionStatus.CLOSED
                and session.ended_at is not None
                and payload.marked_at.astimezone(UTC) > session.ended_at.astimezone(UTC)
            )
        ):
            raise HTTPException(status_code=409, detail="Attendance event is outside the class session.")
    enrolled = await db.scalar(
        select(CourseEnrollment.id).where(
            CourseEnrollment.class_section_id == session.class_section_id,
            CourseEnrollment.student_id == student.id,
        )
    )
    if enrolled is None:
        raise HTTPException(status_code=409, detail="Student is not enrolled in the class session.")
    actor = await db.get(User, payload.actor_user_id) if payload.actor_user_id else None
    if payload.actor_user_id is not None and actor is None:
        raise HTTPException(status_code=409, detail="The attendance actor is not provisioned on the server.")
    if payload.correction:
        existing_record = await db.scalar(
            select(SessionAttendanceRecord).where(
                SessionAttendanceRecord.session_id == payload.session_id,
                SessionAttendanceRecord.student_id == payload.student_id,
            )
        )
        if existing_record is not None:
            return await _apply_synced_correction(
                db, request, actor, existing_record, payload
            )
    record = SessionAttendanceRecord(
        session_id=session.id,
        student_id=student.id,
        mark=payload.mark,
        method=AttendanceMethod.OFFLINE_SYNC,
        source_event_id=payload.source_event_id,
        marked_at=payload.marked_at.astimezone(UTC),
        actor_user_id=actor.id if actor is not None else None,
    )
    db.add(record)
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A different attendance event already exists for this student and session.",
        ) from error
    after = {
        "session_id": str(session.id),
        "student_id": str(student.id),
        "mark": payload.mark.value,
        "source_event_id": payload.source_event_id,
        "marked_at": record.marked_at.isoformat(),
    }
    if payload.correction:
        after["correction_reason"] = payload.correction_reason
    await AuditService(request, SqlAuditRepository(db)).record(
        actor,
        "attendance_records.sync_correction" if payload.correction else "attendance_records.sync",
        "attendance_record",
        str(record.id),
        {},
        after,
    )
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            status_code=409,
            detail="A different attendance event already exists for this student and session.",
        ) from error
    return AttendanceSyncReceipt(event_id=payload.event_id, status="synced")
