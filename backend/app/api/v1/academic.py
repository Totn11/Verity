from __future__ import annotations

import csv
import io
import uuid
from datetime import UTC, date, datetime, time
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import require_role
from app.db.models import (
    AttendanceMark,
    AttendanceMethod,
    AttendanceSession,
    AttendanceSessionStatus,
    AttendanceSyncOutbox,
    ClassSection,
    Course,
    CourseEnrollment,
    Semester,
    SessionAttendanceRecord,
    Student,
    User,
    UserRole,
)
from app.db.session import get_session
from app.repositories.sql import SqlAuditRepository
from app.services.audit import AuditService
from app.services.attendance_outbox import enqueue_attendance_event

router = APIRouter(prefix="/api/v1")
read_access = require_role("admin", "staff", "lecturer")
write_access = require_role("admin")
attendance_access = require_role("admin", "staff", "lecturer")
SessionDep = Annotated[AsyncSession, Depends(get_session)]
UserDep = Annotated[User, Depends(read_access)]


class StudentInput(BaseModel):
    student_number: str = Field(min_length=1, max_length=64)
    first_name: str = Field(min_length=1, max_length=120)
    last_name: str = Field(min_length=1, max_length=120)
    email: str | None = Field(default=None, max_length=320)


class StudentRead(StudentInput):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    is_active: bool


class CourseInput(BaseModel):
    code: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None


class CourseRead(CourseInput):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class SemesterInput(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    starts_on: date
    ends_on: date

    @model_validator(mode="after")
    def validate_dates(self) -> SemesterInput:
        if self.starts_on > self.ends_on:
            raise ValueError("Semester start date must be on or before the end date.")
        return self


class SemesterRead(SemesterInput):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class SectionInput(BaseModel):
    course_id: uuid.UUID
    semester_id: uuid.UUID
    lecturer_user_id: uuid.UUID | None = None
    section_code: str = Field(min_length=1, max_length=64)
    classroom_label: str | None = Field(default=None, max_length=120)
    schedule_weekday: int | None = Field(default=None, ge=0, le=6)
    schedule_starts_at: time | None = None
    schedule_ends_at: time | None = None

    @model_validator(mode="after")
    def validate_schedule(self) -> SectionInput:
        schedule_values = (
            self.schedule_weekday,
            self.schedule_starts_at,
            self.schedule_ends_at,
        )
        if any(value is not None for value in schedule_values) and any(
            value is None for value in schedule_values
        ):
            raise ValueError("Schedule day, start time, and end time must be provided together.")
        if (
            self.schedule_starts_at is not None
            and self.schedule_ends_at is not None
            and self.schedule_starts_at >= self.schedule_ends_at
        ):
            raise ValueError("Class schedule end time must be after its start time.")
        return self


class SectionRead(SectionInput):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID


class EnrollmentInput(BaseModel):
    student_id: uuid.UUID


class AttendanceSessionInput(BaseModel):
    scheduled_for: datetime | None = None
    status: AttendanceSessionStatus = AttendanceSessionStatus.OPEN
    confidence_threshold: Decimal = Field(default=Decimal("0.800"), gt=0, lt=1)

    @model_validator(mode="after")
    def validate_timezone(self) -> AttendanceSessionInput:
        if self.scheduled_for is not None and (
            self.scheduled_for.tzinfo is None or self.scheduled_for.utcoffset() is None
        ):
            raise ValueError("Session timestamp must include a timezone.")
        if self.status == AttendanceSessionStatus.SCHEDULED and (
            self.scheduled_for is None or self.scheduled_for.astimezone(UTC) <= datetime.now(UTC)
        ):
            raise ValueError("A scheduled session must have a future start time.")
        if self.status == AttendanceSessionStatus.OPEN and self.scheduled_for is not None:
            raise ValueError("An open session cannot have a scheduled start time.")
        if self.status == AttendanceSessionStatus.CLOSED:
            raise ValueError("A new attendance session cannot start closed.")
        return self


class AttendanceSessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    class_section_id: uuid.UUID
    started_at: datetime
    scheduled_for: datetime | None
    ended_at: datetime | None
    status: AttendanceSessionStatus
    confidence_threshold: Decimal


class AttendanceRecordInput(BaseModel):
    student_id: uuid.UUID
    mark: AttendanceMark = AttendanceMark.PRESENT
    method: AttendanceMethod = AttendanceMethod.MANUAL
    marked_at: datetime | None = None
    source_event_id: str | None = Field(default=None, min_length=1, max_length=255)

    @model_validator(mode="after")
    def validate_manual_or_offline_only(self) -> AttendanceRecordInput:
        if self.method != AttendanceMethod.MANUAL:
            raise ValueError("Only manual attendance recording is available.")
        if self.marked_at is not None and (
            self.marked_at.tzinfo is None or self.marked_at.utcoffset() is None
        ):
            raise ValueError("Attendance timestamp must include a timezone.")
        return self


class AttendanceCorrectionInput(BaseModel):
    mark: AttendanceMark
    reason: str = Field(min_length=3, max_length=500)


class AttendanceRecordRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    session_id: uuid.UUID
    student_id: uuid.UUID
    mark: AttendanceMark
    method: AttendanceMethod
    confidence: Decimal | None
    source_event_id: str | None
    marked_at: datetime
    corrected_at: datetime | None


class AttendanceActivityRead(BaseModel):
    student_id: uuid.UUID
    student_name: str
    student_number: str
    mark: AttendanceMark
    method: AttendanceMethod
    marked_at: datetime


class UpcomingClassRead(BaseModel):
    section_id: uuid.UUID
    course_name: str
    course_code: str
    section_code: str
    starts_at: time | None
    classroom_label: str | None


class UpcomingSessionRead(BaseModel):
    session_id: uuid.UUID
    class_section_id: uuid.UUID
    course_name: str
    course_code: str
    section_code: str
    starts_at: datetime


class LecturerRead(BaseModel):
    id: uuid.UUID
    display_name: str
    email: str


class DashboardSummaryRead(BaseModel):
    total_registered_students: int
    classes_scheduled_today: int
    active_sessions: int
    students_present: int | None
    students_absent: int | None
    students_unverified: int | None
    attendance_activity: list[AttendanceActivityRead]
    upcoming_classes: list[UpcomingClassRead]
    upcoming_sessions: list[UpcomingSessionRead]
    recognition_review_available: bool
    recognition_failures_pending_review: int | None


@router.get(
    "/dashboard/summary",
    response_model=DashboardSummaryRead,
    dependencies=[Depends(read_access)],
)
async def dashboard_summary(
    db: SessionDep,
    actor: UserDep,
    local_date: date = Query(),
    local_time: time = Query(),
) -> DashboardSummaryRead:
    student_count = select(func.count()).select_from(Student).where(Student.is_active.is_(True))
    if actor.role == UserRole.LECTURER:
        student_count = (
            select(func.count(func.distinct(Student.id)))
            .select_from(Student)
            .join(CourseEnrollment)
            .join(ClassSection)
            .where(Student.is_active.is_(True), ClassSection.lecturer_user_id == actor.id)
        )
    total_students = await db.scalar(student_count) or 0
    schedule_query = (
        select(ClassSection)
        .join(Semester)
        .where(
            ClassSection.schedule_weekday == local_date.weekday(),
            Semester.starts_on <= local_date,
            Semester.ends_on >= local_date,
        )
    )
    if actor.role == UserRole.LECTURER:
        schedule_query = schedule_query.where(ClassSection.lecturer_user_id == actor.id)
    scheduled_sections = list(
        (
            await db.scalars(
                schedule_query.order_by(ClassSection.schedule_starts_at)
            )
        ).all()
    )
    section_ids = [section.id for section in scheduled_sections]
    course_rows = {}
    if section_ids:
        course_rows = {
            section.id: (course.code, course.name)
            for section, course in (
                await db.execute(
                    select(ClassSection, Course)
                    .join(Course, Course.id == ClassSection.course_id)
                    .where(ClassSection.id.in_(section_ids))
                )
            ).all()
        }

    open_session_query = select(AttendanceSession).where(
        AttendanceSession.status == AttendanceSessionStatus.OPEN
    )
    if actor.role == UserRole.LECTURER:
        open_session_query = open_session_query.join(ClassSection).where(
            ClassSection.lecturer_user_id == actor.id
        )
    open_sessions = list((await db.scalars(open_session_query)).all())
    active_session_count = len(open_sessions)
    present_count: int | None = None
    absent_count: int | None = None
    unverified_count: int | None = None
    if open_sessions:
        active_session_ids = [session.id for session in open_sessions]
        enrolled_pairs = list(
            (
                await db.execute(
                    select(CourseEnrollment.class_section_id, CourseEnrollment.student_id)
                    .join(
                        AttendanceSession,
                        AttendanceSession.class_section_id == CourseEnrollment.class_section_id,
                    )
                    .where(AttendanceSession.id.in_(active_session_ids))
                )
            ).all()
        )
        sessions_by_section: dict[uuid.UUID, list[uuid.UUID]] = {}
        for session in open_sessions:
            sessions_by_section.setdefault(session.class_section_id, []).append(session.id)
        roster_pairs = {
            (session_id, student_id)
            for section_id, student_id in enrolled_pairs
            for session_id in sessions_by_section.get(section_id, [])
        }
        active_records = list(
            (
                await db.scalars(
                    select(SessionAttendanceRecord).where(
                        SessionAttendanceRecord.session_id.in_(active_session_ids)
                    )
                )
            ).all()
        )
        recorded_pairs = {(record.session_id, record.student_id) for record in active_records}
        present_count = sum(
            record.mark in (AttendanceMark.PRESENT, AttendanceMark.LATE)
            for record in active_records
        )
        absent_count = sum(record.mark == AttendanceMark.ABSENT for record in active_records)
        unverified_count = len(roster_pairs - recorded_pairs)

    activity_query = (
        select(
                SessionAttendanceRecord.student_id,
                Student.first_name,
                Student.last_name,
                Student.student_number,
                SessionAttendanceRecord.mark,
                SessionAttendanceRecord.method,
                SessionAttendanceRecord.marked_at,
            )
            .join(Student, Student.id == SessionAttendanceRecord.student_id)
            .order_by(SessionAttendanceRecord.marked_at.desc())
            .limit(8)
    )
    if actor.role == UserRole.LECTURER:
        activity_query = activity_query.join(
            AttendanceSession, AttendanceSession.id == SessionAttendanceRecord.session_id
        ).join(ClassSection).where(ClassSection.lecturer_user_id == actor.id)
    activity_rows = (await db.execute(activity_query)).all()
    activity = [
        AttendanceActivityRead(
            student_id=row.student_id,
            student_name=f"{row.first_name} {row.last_name}",
            student_number=row.student_number,
            mark=row.mark,
            method=row.method,
            marked_at=row.marked_at,
        )
        for row in activity_rows
    ]
    upcoming = [
        UpcomingClassRead(
            section_id=section.id,
            course_name=course_rows[section.id][1],
            course_code=course_rows[section.id][0],
            section_code=section.section_code,
            starts_at=section.schedule_starts_at,
            classroom_label=section.classroom_label,
        )
        for section in scheduled_sections
        if section.id in course_rows
        and section.schedule_starts_at is not None
        and section.schedule_starts_at > local_time
    ]
    scheduled_session_query = (
        select(AttendanceSession)
                .where(
                    AttendanceSession.status == AttendanceSessionStatus.SCHEDULED,
                    AttendanceSession.scheduled_for > datetime.now(UTC),
                )
                .order_by(AttendanceSession.scheduled_for)
                .limit(5)
    )
    if actor.role == UserRole.LECTURER:
        scheduled_session_query = scheduled_session_query.join(ClassSection).where(
            ClassSection.lecturer_user_id == actor.id
        )
    scheduled_sessions = list((await db.scalars(scheduled_session_query)).all())
    upcoming_session_rows = []
    if scheduled_sessions:
        scheduled_section_ids = {session.class_section_id for session in scheduled_sessions}
        scheduled_courses = {
            section.id: (course.code, course.name, section.section_code)
            for section, course in (
                await db.execute(
                    select(ClassSection, Course)
                    .join(Course, Course.id == ClassSection.course_id)
                    .where(ClassSection.id.in_(scheduled_section_ids))
                )
            ).all()
        }
        upcoming_session_rows = [
            UpcomingSessionRead(
                session_id=session.id,
                class_section_id=session.class_section_id,
                course_name=scheduled_courses[session.class_section_id][1],
                course_code=scheduled_courses[session.class_section_id][0],
                section_code=scheduled_courses[session.class_section_id][2],
                starts_at=session.scheduled_for,
            )
            for session in scheduled_sessions
            if session.class_section_id in scheduled_courses
        ]
    return DashboardSummaryRead(
        total_registered_students=total_students,
        classes_scheduled_today=len(scheduled_sections),
        active_sessions=active_session_count,
        students_present=present_count,
        students_absent=absent_count,
        students_unverified=unverified_count,
        attendance_activity=activity,
        upcoming_classes=upcoming,
        upcoming_sessions=upcoming_session_rows,
        recognition_review_available=False,
        recognition_failures_pending_review=None,
    )


async def _audit(
    request: Request,
    db: AsyncSession,
    actor: User,
    action: str,
    entity_type: str,
    entity_id: uuid.UUID,
    after: BaseModel,
) -> None:
    await AuditService(request, SqlAuditRepository(db)).record(
        actor, action, entity_type, str(entity_id), {}, after.model_dump(mode="json")
    )


async def _require_section_access(
    db: AsyncSession, section_id: uuid.UUID, actor: User
) -> ClassSection:
    section = await db.get(ClassSection, section_id)
    if section is None:
        raise HTTPException(status_code=404, detail="Class section not found.")
    if actor.role == UserRole.LECTURER and section.lecturer_user_id != actor.id:
        raise HTTPException(status_code=403, detail="This class section is not assigned to the lecturer.")
    return section


async def _commit_or_conflict(db: AsyncSession) -> None:
    try:
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A record with the same unique identifier already exists.") from error


async def _flush_or_conflict(db: AsyncSession) -> None:
    try:
        await db.flush()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(status_code=409, detail="A record with the same unique identifier already exists.") from error


@router.get("/students", response_model=list[StudentRead], dependencies=[Depends(read_access)])
async def list_students(
    db: SessionDep,
    actor: UserDep,
    q: str | None = Query(default=None, max_length=255),
    limit: int = Query(default=100, ge=1, le=500),
) -> list[Student]:
    statement = select(Student).order_by(Student.last_name, Student.first_name).limit(limit)
    if q:
        statement = statement.where(
            Student.student_number.ilike(f"%{q}%")
            | Student.first_name.ilike(f"%{q}%")
            | Student.last_name.ilike(f"%{q}%")
        )
    if actor.role == UserRole.LECTURER:
        statement = (
            statement.join(CourseEnrollment)
            .join(ClassSection)
            .where(ClassSection.lecturer_user_id == actor.id)
            .distinct()
        )
    return list((await db.scalars(statement)).all())


@router.post("/students", response_model=StudentRead, status_code=status.HTTP_201_CREATED)
async def create_student(
    payload: StudentInput,
    request: Request,
    db: SessionDep,
    actor: Annotated[User, Depends(write_access)],
) -> Student:
    student = Student(**payload.model_dump())
    db.add(student)
    await _flush_or_conflict(db)
    await _audit(request, db, actor, "students.create", "student", student.id, StudentRead.model_validate(student))
    await _commit_or_conflict(db)
    return student


@router.get("/courses", response_model=list[CourseRead], dependencies=[Depends(read_access)])
async def list_courses(db: SessionDep, actor: UserDep) -> list[Course]:
    statement = select(Course).order_by(Course.code)
    if actor.role == UserRole.LECTURER:
        statement = (
            statement.join(ClassSection)
            .where(ClassSection.lecturer_user_id == actor.id)
            .distinct()
        )
    return list((await db.scalars(statement)).all())


@router.post("/courses", response_model=CourseRead, status_code=status.HTTP_201_CREATED)
async def create_course(
    payload: CourseInput,
    request: Request,
    db: SessionDep,
    actor: Annotated[User, Depends(write_access)],
) -> Course:
    course = Course(**payload.model_dump())
    db.add(course)
    await _flush_or_conflict(db)
    await _audit(request, db, actor, "courses.create", "course", course.id, CourseRead.model_validate(course))
    await _commit_or_conflict(db)
    return course


@router.get("/semesters", response_model=list[SemesterRead], dependencies=[Depends(read_access)])
async def list_semesters(db: SessionDep, actor: UserDep) -> list[Semester]:
    statement = select(Semester).order_by(Semester.starts_on.desc())
    if actor.role == UserRole.LECTURER:
        statement = (
            statement.join(ClassSection)
            .where(ClassSection.lecturer_user_id == actor.id)
            .distinct()
        )
    return list((await db.scalars(statement)).all())


@router.post("/semesters", response_model=SemesterRead, status_code=status.HTTP_201_CREATED)
async def create_semester(
    payload: SemesterInput,
    request: Request,
    db: SessionDep,
    actor: Annotated[User, Depends(write_access)],
) -> Semester:
    semester = Semester(**payload.model_dump())
    db.add(semester)
    await _flush_or_conflict(db)
    await _audit(request, db, actor, "semesters.create", "semester", semester.id, SemesterRead.model_validate(semester))
    await _commit_or_conflict(db)
    return semester


@router.get("/class-sections", response_model=list[SectionRead], dependencies=[Depends(read_access)])
async def list_sections(db: SessionDep, actor: UserDep) -> list[ClassSection]:
    statement = select(ClassSection).order_by(ClassSection.section_code)
    if actor.role == UserRole.LECTURER:
        statement = statement.where(ClassSection.lecturer_user_id == actor.id)
    return list((await db.scalars(statement)).all())


@router.get("/lecturers", response_model=list[LecturerRead], dependencies=[Depends(write_access)])
async def list_lecturers(db: SessionDep) -> list[LecturerRead]:
    users = await db.scalars(
        select(User)
        .where(User.role == UserRole.LECTURER, User.is_active.is_(True))
        .order_by(User.display_name)
    )
    return [
        LecturerRead(id=user.id, display_name=user.display_name, email=user.email)
        for user in users
    ]


@router.post("/class-sections", response_model=SectionRead, status_code=status.HTTP_201_CREATED)
async def create_section(
    payload: SectionInput,
    request: Request,
    db: SessionDep,
    actor: Annotated[User, Depends(write_access)],
) -> ClassSection:
    if payload.lecturer_user_id is not None:
        lecturer = await db.scalar(
            select(User).where(
                User.id == payload.lecturer_user_id,
                User.role == UserRole.LECTURER,
                User.is_active.is_(True),
            )
        )
        if lecturer is None:
            raise HTTPException(status_code=422, detail="Assigned user must be an active lecturer.")
    section = ClassSection(**payload.model_dump())
    db.add(section)
    await _flush_or_conflict(db)
    await _audit(request, db, actor, "class_sections.create", "class_section", section.id, SectionRead.model_validate(section))
    await _commit_or_conflict(db)
    return section


@router.post("/class-sections/{section_id}/enrollments", status_code=status.HTTP_201_CREATED)
async def enroll_student(
    section_id: uuid.UUID,
    payload: EnrollmentInput,
    request: Request,
    db: SessionDep,
    actor: Annotated[User, Depends(write_access)],
) -> dict[str, str]:
    section = await db.get(ClassSection, section_id)
    student = await db.get(Student, payload.student_id)
    if section is None or student is None:
        raise HTTPException(status_code=404, detail="Class section or student not found.")
    enrollment = CourseEnrollment(class_section_id=section_id, student_id=student.id)
    db.add(enrollment)
    await _flush_or_conflict(db)
    await _audit(
        request, db, actor, "students.enroll", "course_enrollment", enrollment.id,
        EnrollmentInput(student_id=student.id),
    )
    await _commit_or_conflict(db)
    return {"id": str(enrollment.id), "student_id": str(student.id), "class_section_id": str(section_id)}


@router.get("/attendance-sessions", response_model=list[AttendanceSessionRead], dependencies=[Depends(read_access)])
async def list_attendance_sessions(
    db: SessionDep,
    actor: UserDep,
    class_section_id: uuid.UUID | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[AttendanceSession]:
    statement = select(AttendanceSession).order_by(AttendanceSession.started_at.desc()).limit(limit)
    if class_section_id is not None:
        statement = statement.where(AttendanceSession.class_section_id == class_section_id)
    if actor.role == UserRole.LECTURER:
        statement = statement.join(ClassSection).where(ClassSection.lecturer_user_id == actor.id)
    return list((await db.scalars(statement)).all())


@router.post(
    "/class-sections/{section_id}/attendance-sessions",
    response_model=AttendanceSessionRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_attendance_session(
    section_id: uuid.UUID,
    payload: AttendanceSessionInput,
    request: Request,
    db: SessionDep,
    actor: Annotated[User, Depends(attendance_access)],
) -> AttendanceSession:
    await _require_section_access(db, section_id, actor)
    session = AttendanceSession(
        class_section_id=section_id,
        started_at=datetime.now(UTC),
        scheduled_for=payload.scheduled_for.astimezone(UTC) if payload.scheduled_for else None,
        status=payload.status,
        confidence_threshold=payload.confidence_threshold,
        created_by_user_id=actor.id,
    )
    db.add(session)
    await _flush_or_conflict(db)
    await _audit(request, db, actor, "attendance_sessions.create", "attendance_session", session.id, AttendanceSessionRead.model_validate(session))
    await db.commit()
    return session


@router.post("/attendance-sessions/{session_id}/start", response_model=AttendanceSessionRead)
async def start_attendance_session(
    session_id: uuid.UUID,
    request: Request,
    db: SessionDep,
    actor: Annotated[User, Depends(attendance_access)],
) -> AttendanceSession:
    session = await db.get(AttendanceSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Attendance session not found.")
    await _require_section_access(db, session.class_section_id, actor)
    if session.status == AttendanceSessionStatus.CLOSED:
        raise HTTPException(status_code=409, detail="A closed attendance session cannot be reopened.")
    if session.status == AttendanceSessionStatus.OPEN:
        return session
    before = AttendanceSessionRead.model_validate(session).model_dump(mode="json")
    session.status = AttendanceSessionStatus.OPEN
    session.started_at = datetime.now(UTC)
    await _flush_or_conflict(db)
    await AuditService(request, SqlAuditRepository(db)).record(
        actor, "attendance_sessions.start", "attendance_session", str(session.id),
        before, AttendanceSessionRead.model_validate(session).model_dump(mode="json")
    )
    await db.commit()
    return session


@router.post(
    "/attendance-sessions/{session_id}/records",
    response_model=AttendanceRecordRead,
    status_code=status.HTTP_201_CREATED,
)
async def record_attendance(
    session_id: uuid.UUID,
    payload: AttendanceRecordInput,
    request: Request,
    db: SessionDep,
    actor: Annotated[User, Depends(attendance_access)],
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key", min_length=1, max_length=255)] = None,
) -> AttendanceRecordRead:
    session = await db.get(AttendanceSession, session_id)
    student = await db.get(Student, payload.student_id)
    if session is None or student is None:
        raise HTTPException(status_code=404, detail="Attendance session or student not found.")
    await _require_section_access(db, session.class_section_id, actor)
    if session.status != AttendanceSessionStatus.OPEN:
        raise HTTPException(status_code=409, detail="Attendance session is not open.")
    enrolled = await db.scalar(
        select(CourseEnrollment.id).where(
            CourseEnrollment.class_section_id == session.class_section_id,
            CourseEnrollment.student_id == student.id,
        )
    )
    if enrolled is None:
        raise HTTPException(status_code=422, detail="Student is not enrolled in this class section.")
    if payload.source_event_id and idempotency_key and payload.source_event_id != idempotency_key:
        raise HTTPException(
            status_code=422,
            detail="source_event_id and Idempotency-Key must match when both are provided.",
        )
    event_id = payload.source_event_id or idempotency_key or str(uuid.uuid4())
    if event_id:
        prior = await db.scalar(
            select(SessionAttendanceRecord).where(SessionAttendanceRecord.source_event_id == event_id)
        )
        if prior is not None:
            if (
                prior.session_id != session.id
                or prior.student_id != student.id
                or prior.mark != payload.mark
                or prior.method != AttendanceMethod.MANUAL
            ):
                raise HTTPException(status_code=409, detail="This idempotency key is already associated with a different attendance record.")
            return AttendanceRecordRead.model_validate(prior)
    record = SessionAttendanceRecord(
        session_id=session.id,
        student_id=student.id,
        mark=payload.mark,
        method=AttendanceMethod.MANUAL,
        source_event_id=event_id,
        marked_at=payload.marked_at.astimezone(UTC) if payload.marked_at else datetime.now(UTC),
        actor_user_id=actor.id,
    )
    db.add(record)
    await _flush_or_conflict(db)
    enqueue_attendance_event(
        db,
        source_event_id=event_id,
        session_id=session.id,
        student_id=student.id,
        mark=record.mark.value,
        marked_at=record.marked_at,
        actor_user_id=actor.id,
    )
    await _audit(request, db, actor, "attendance_records.create", "attendance_record", record.id, AttendanceRecordRead.model_validate(record))
    await _commit_or_conflict(db)
    return record


@router.get(
    "/attendance-sessions/{session_id}/records",
    response_model=list[AttendanceRecordRead],
    dependencies=[Depends(read_access)],
)
async def list_session_records(
    session_id: uuid.UUID, db: SessionDep, actor: UserDep
) -> list[SessionAttendanceRecord]:
    session = await db.get(AttendanceSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Attendance session not found.")
    await _require_section_access(db, session.class_section_id, actor)
    statement = select(SessionAttendanceRecord).where(
        SessionAttendanceRecord.session_id == session_id
    ).order_by(SessionAttendanceRecord.marked_at)
    return list((await db.scalars(statement)).all())


@router.patch(
    "/attendance-sessions/{session_id}/records/{record_id}",
    response_model=AttendanceRecordRead,
)
async def correct_attendance_record(
    session_id: uuid.UUID,
    record_id: uuid.UUID,
    payload: AttendanceCorrectionInput,
    request: Request,
    db: SessionDep,
    actor: Annotated[User, Depends(attendance_access)],
) -> SessionAttendanceRecord:
    record = await db.get(SessionAttendanceRecord, record_id)
    if record is None or record.session_id != session_id:
        raise HTTPException(status_code=404, detail="Attendance record not found in this session.")
    session = await db.get(AttendanceSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Attendance session not found.")
    await _require_section_access(db, session.class_section_id, actor)
    before = AttendanceRecordRead.model_validate(record).model_dump(mode="json")
    previous_source_event_id = record.source_event_id
    record.mark = payload.mark
    record.method = AttendanceMethod.MANUAL
    record.actor_user_id = actor.id
    record.corrected_at = datetime.now(UTC)
    source_event_id = f"correction:{uuid.uuid4()}"
    record.marked_at = record.corrected_at
    if previous_source_event_id:
        pending_event_id = uuid.uuid5(
            uuid.NAMESPACE_URL, f"verity-attendance:{previous_source_event_id}"
        )
        pending_event = await db.get(AttendanceSyncOutbox, pending_event_id)
    else:
        pending_event = None
    if pending_event is not None and pending_event.status == "pending":
        pending_event.payload = {
            **pending_event.payload,
            "mark": payload.mark.value,
            "marked_at": record.marked_at.isoformat(),
            "actor_user_id": str(actor.id),
            "correction": True,
            "correction_of": previous_source_event_id,
            "correction_reason": payload.reason,
        }
    else:
        record.source_event_id = source_event_id
        enqueue_attendance_event(
            db,
            source_event_id=source_event_id,
            session_id=record.session_id,
            student_id=record.student_id,
            mark=record.mark.value,
            marked_at=record.marked_at,
            actor_user_id=actor.id,
            correction_of=previous_source_event_id,
            correction_reason=payload.reason,
        )
    await _flush_or_conflict(db)
    after = AttendanceRecordRead.model_validate(record).model_dump(mode="json")
    after["correction_reason"] = payload.reason
    await AuditService(request, SqlAuditRepository(db)).record(
        actor, "attendance_records.correct", "attendance_record", str(record.id), before, after
    )
    await db.commit()
    return record


@router.get("/attendance-sessions/{session_id}/records.csv")
async def export_session_records(
    session_id: uuid.UUID,
    db: SessionDep,
    actor: UserDep,
) -> StreamingResponse:
    session = await db.get(AttendanceSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Attendance session not found.")
    await _require_section_access(db, session.class_section_id, actor)
    rows = await db.execute(
        select(
            Student.student_number,
            Student.first_name,
            Student.last_name,
            SessionAttendanceRecord.mark,
            SessionAttendanceRecord.method,
            SessionAttendanceRecord.marked_at,
        )
        .join(SessionAttendanceRecord, SessionAttendanceRecord.student_id == Student.id)
        .where(SessionAttendanceRecord.session_id == session_id)
        .order_by(Student.last_name, Student.first_name)
    )
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["student_number", "first_name", "last_name", "mark", "method", "marked_at"])
    writer.writerows(rows.all())
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="verity-attendance-{session_id}.csv"'},
    )


@router.post("/attendance-sessions/{session_id}/close", response_model=AttendanceSessionRead)
async def close_attendance_session(
    session_id: uuid.UUID,
    request: Request,
    db: SessionDep,
    actor: Annotated[User, Depends(attendance_access)],
) -> AttendanceSession:
    session = await db.get(AttendanceSession, session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="Attendance session not found.")
    await _require_section_access(db, session.class_section_id, actor)
    if session.status == AttendanceSessionStatus.CLOSED:
        return session
    before = AttendanceSessionRead.model_validate(session).model_dump(mode="json")
    session.status = AttendanceSessionStatus.CLOSED
    session.ended_at = datetime.now(UTC)
    await _flush_or_conflict(db)
    await AuditService(request, SqlAuditRepository(db)).record(
        actor, "attendance_sessions.close", "attendance_session", str(session.id),
        before, AttendanceSessionRead.model_validate(session).model_dump(mode="json")
    )
    await db.commit()
    return session
