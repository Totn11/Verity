from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Enum,
    event,
    ForeignKey,
    Index,
    inspect,
    Integer,
    LargeBinary,
    Numeric,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import CITEXT, JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    STAFF = "staff"
    LECTURER = "lecturer"


class PersonStatus(str, enum.Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    VISITOR = "visitor"


class AttendanceKind(str, enum.Enum):
    CHECK_IN = "check_in"
    CHECK_OUT = "check_out"


class EventSource(str, enum.Enum):
    TERMINAL = "terminal"
    MANUAL = "manual"
    IMPORT = "import"


class RecognitionOutcome(str, enum.Enum):
    MATCH = "match"
    NO_MATCH = "no_match"
    ERROR = "error"


class AttendanceSessionStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    OPEN = "open"
    CLOSED = "closed"


class AttendanceMark(str, enum.Enum):
    PRESENT = "present"
    LATE = "late"
    ABSENT = "absent"
    EXCUSED = "excused"


class AttendanceMethod(str, enum.Enum):
    MANUAL = "manual"
    FACE_RECOGNITION = "face_recognition"
    OFFLINE_SYNC = "offline_sync"


def _enum_values(enum_type: type[enum.Enum]) -> list[str]:
    return [value.value for value in enum_type]


def _enum(enum_type: type[enum.Enum], name: str) -> Enum:
    return Enum(
        enum_type,
        name=name,
        values_callable=_enum_values,
        native_enum=True,
    )


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[UserRole] = mapped_column(_enum(UserRole, "user_role"), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    session_version: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    sessions: Mapped[list[Session]] = relationship(back_populates="user")
    attendance_events: Mapped[list[AttendanceEvent]] = relationship(
        back_populates="actor", foreign_keys="AttendanceEvent.actor_user_id"
    )
    audit_events: Mapped[list[AuditEvent]] = relationship(back_populates="actor")


@event.listens_for(User, "before_update")
def _bump_session_version_for_credential_changes(mapper, connection, user: User) -> None:
    state = inspect(user)
    if state.attrs.role.history.has_changes() or state.attrs.password_hash.history.has_changes():
        user.session_version += 1


class Session(Base):
    __tablename__ = "sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    user_agent: Mapped[str] = mapped_column(Text, nullable=False)
    ip_hash: Mapped[str] = mapped_column(Text, nullable=False)

    user: Mapped[User] = relationship(back_populates="sessions")


class Person(Base):
    __tablename__ = "people"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    external_ref: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str] = mapped_column(CITEXT(), nullable=False)
    phone: Mapped[str] = mapped_column(String(64), nullable=False)
    department: Mapped[str] = mapped_column(String(255), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[PersonStatus] = mapped_column(
        _enum(PersonStatus, "person_status"), nullable=False
    )
    photo_url: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    attendance_events: Mapped[list[AttendanceEvent]] = relationship(back_populates="person")
    recognition_events: Mapped[list[RecognitionEvent]] = relationship(back_populates="person")
    location_events: Mapped[list[LocationEvent]] = relationship(back_populates="person")


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    floor: Mapped[int] = mapped_column(Integer, nullable=False)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False)
    pos_x: Mapped[Decimal] = mapped_column(Numeric, nullable=False)
    pos_y: Mapped[Decimal] = mapped_column(Numeric, nullable=False)

    attendance_events: Mapped[list[AttendanceEvent]] = relationship(back_populates="room")
    recognition_events: Mapped[list[RecognitionEvent]] = relationship(back_populates="room")
    location_events: Mapped[list[LocationEvent]] = relationship(back_populates="room")


class Student(Base):
    __tablename__ = "students"
    __table_args__ = (
        Index("uq_students_email", "email", unique=True, postgresql_where=text("email IS NOT NULL")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_number: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    first_name: Mapped[str] = mapped_column(String(120), nullable=False)
    last_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str | None] = mapped_column(CITEXT())
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    enrollments: Mapped[list[CourseEnrollment]] = relationship(back_populates="student")
    face_template: Mapped[FaceTemplate | None] = relationship(back_populates="student", uselist=False)
    attendance_records: Mapped[list[SessionAttendanceRecord]] = relationship(back_populates="student")


class Semester(Base):
    __tablename__ = "semesters"
    __table_args__ = (
        CheckConstraint("starts_on <= ends_on", name="valid_date_range"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    starts_on: Mapped[date] = mapped_column(Date, nullable=False)
    ends_on: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    class_sections: Mapped[list[ClassSection]] = relationship(back_populates="semester")


class Course(Base):
    __tablename__ = "courses"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    code: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    class_sections: Mapped[list[ClassSection]] = relationship(back_populates="course")


class ClassSection(Base):
    __tablename__ = "class_sections"
    __table_args__ = (
        UniqueConstraint("course_id", "semester_id", "section_code", name="course_term_code"),
        CheckConstraint(
            "schedule_weekday IS NULL OR schedule_weekday BETWEEN 0 AND 6",
            name="schedule_weekday_range",
        ),
        CheckConstraint(
            "(schedule_starts_at IS NULL AND schedule_ends_at IS NULL) OR "
            "(schedule_starts_at IS NOT NULL AND schedule_ends_at IS NOT NULL "
            "AND schedule_starts_at < schedule_ends_at)",
            name="schedule_time_pair",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    course_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("courses.id"), nullable=False
    )
    semester_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("semesters.id"), nullable=False
    )
    lecturer_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    section_code: Mapped[str] = mapped_column(String(64), nullable=False)
    classroom_label: Mapped[str | None] = mapped_column(String(120))
    schedule_weekday: Mapped[int | None] = mapped_column(Integer)
    schedule_starts_at: Mapped[time | None] = mapped_column(Time)
    schedule_ends_at: Mapped[time | None] = mapped_column(Time)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    course: Mapped[Course] = relationship(back_populates="class_sections")
    semester: Mapped[Semester] = relationship(back_populates="class_sections")
    enrollments: Mapped[list[CourseEnrollment]] = relationship(back_populates="class_section")
    attendance_sessions: Mapped[list[AttendanceSession]] = relationship(back_populates="class_section")


class CourseEnrollment(Base):
    __tablename__ = "course_enrollments"
    __table_args__ = (
        Index("uq_course_enrollments_section_student", "class_section_id", "student_id", unique=True),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("class_sections.id"), nullable=False
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id"), nullable=False
    )
    enrolled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    class_section: Mapped[ClassSection] = relationship(back_populates="enrollments")
    student: Mapped[Student] = relationship(back_populates="enrollments")


class AttendanceSession(Base):
    __tablename__ = "attendance_sessions"
    __table_args__ = (
        Index("ix_attendance_sessions_section_started", "class_section_id", "started_at"),
        CheckConstraint(
            "confidence_threshold > 0 AND confidence_threshold < 1",
            name="confidence_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    class_section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("class_sections.id"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    scheduled_for: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    status: Mapped[AttendanceSessionStatus] = mapped_column(
        _enum(AttendanceSessionStatus, "attendance_session_status"),
        nullable=False,
        server_default=text("'open'"),
    )
    confidence_threshold: Mapped[Decimal] = mapped_column(
        Numeric(4, 3), nullable=False, server_default=text("0.800")
    )
    created_by_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    class_section: Mapped[ClassSection] = relationship(back_populates="attendance_sessions")
    records: Mapped[list[SessionAttendanceRecord]] = relationship(back_populates="session")


class SessionAttendanceRecord(Base):
    __tablename__ = "session_attendance_records"
    __table_args__ = (
        Index("uq_session_attendance_session_student", "session_id", "student_id", unique=True),
        Index("uq_session_attendance_source_event", "source_event_id", unique=True,
              postgresql_where=text("source_event_id IS NOT NULL")),
        CheckConstraint(
            "confidence IS NULL OR (confidence >= 0 AND confidence <= 1)",
            name="confidence_range",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("attendance_sessions.id"), nullable=False
    )
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id"), nullable=False
    )
    mark: Mapped[AttendanceMark] = mapped_column(_enum(AttendanceMark, "attendance_mark"), nullable=False)
    method: Mapped[AttendanceMethod] = mapped_column(_enum(AttendanceMethod, "attendance_method"), nullable=False)
    confidence: Mapped[Decimal | None] = mapped_column(Numeric(5, 4))
    source_event_id: Mapped[str | None] = mapped_column(String(255))
    marked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    corrected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    session: Mapped[AttendanceSession] = relationship(back_populates="records")
    student: Mapped[Student] = relationship(back_populates="attendance_records")


class FaceTemplate(Base):
    __tablename__ = "face_templates"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    student_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("students.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    encrypted_template: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    encryption_key_id: Mapped[str] = mapped_column(String(128), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    model_sha256: Mapped[str | None] = mapped_column(String(64))
    consented_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consent_record_id: Mapped[str | None] = mapped_column(String(255))
    consent_actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    student: Mapped[Student] = relationship(back_populates="face_template")


class FaceRecognitionAttempt(Base):
    __tablename__ = "face_recognition_attempts"
    __table_args__ = (
        CheckConstraint(
            "outcome IN ('matched', 'uncertain', 'no_face', 'multiple_faces', "
            "'quality_rejected', 'model_unavailable', 'error')",
            name="outcome_valid",
        ),
        CheckConstraint("inference_ms >= 0", name="inference_duration_nonnegative"),
        Index("ix_face_recognition_attempts_session_created", "session_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("attendance_sessions.id", ondelete="CASCADE"), nullable=False
    )
    actor_user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=False
    )
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    model_version: Mapped[str] = mapped_column(String(128), nullable=False)
    detector_sha256: Mapped[str | None] = mapped_column(String(64))
    embedder_sha256: Mapped[str | None] = mapped_column(String(64))
    inference_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    quality_metrics: Mapped[dict[str, float | bool | list[str]]] = mapped_column(
        JSONB, nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )


class AttendanceSyncOutbox(Base):
    __tablename__ = "attendance_sync_outbox"
    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'synced', 'conflict')", name="status_valid"
        ),
        CheckConstraint("attempt_count >= 0", name="attempt_count_nonnegative"),
        Index("ix_attendance_sync_outbox_status_created", "status", "created_at"),
    )

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16), nullable=False, server_default=text("'pending'")
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AttendanceEvent(Base):
    __tablename__ = "attendance_events"
    __table_args__ = (
        Index(
            "ix_attendance_events_person_occurred_at",
            "person_id",
            text("occurred_at DESC"),
        ),
        Index(
            "uq_attendance_events_source_event_id",
            "source",
            "source_event_id",
            unique=True,
            postgresql_where=text("source_event_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=False
    )
    kind: Mapped[AttendanceKind] = mapped_column(
        _enum(AttendanceKind, "attendance_kind"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source: Mapped[EventSource] = mapped_column(_enum(EventSource, "event_source"), nullable=False)
    source_event_id: Mapped[str | None] = mapped_column(Text)
    room_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.id"))
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    person: Mapped[Person] = relationship(back_populates="attendance_events")
    room: Mapped[Room | None] = relationship(back_populates="attendance_events")
    actor: Mapped[User | None] = relationship(
        back_populates="attendance_events", foreign_keys=[actor_user_id]
    )


class RecognitionEvent(Base):
    __tablename__ = "recognition_events"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id")
    )
    room_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("rooms.id"))
    score: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    threshold: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False)
    outcome: Mapped[RecognitionOutcome] = mapped_column(
        _enum(RecognitionOutcome, "recognition_outcome"), nullable=False
    )
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    person: Mapped[Person | None] = relationship(back_populates="recognition_events")
    room: Mapped[Room | None] = relationship(back_populates="recognition_events")


class LocationEvent(Base):
    __tablename__ = "location_events"
    __table_args__ = (
        Index(
            "ix_location_events_person_occurred_at",
            "person_id",
            text("occurred_at DESC"),
        ),
        Index(
            "uq_location_events_source_event_id",
            "source",
            "source_event_id",
            unique=True,
            postgresql_where=text("source_event_id IS NOT NULL"),
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    person_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("people.id"), nullable=False
    )
    room_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("rooms.id"), nullable=False
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    source: Mapped[EventSource] = mapped_column(_enum(EventSource, "event_source"), nullable=False)
    source_event_id: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    person: Mapped[Person] = relationship(back_populates="location_events")
    room: Mapped[Room] = relationship(back_populates="location_events")


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    actor_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id")
    )
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_type: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[str] = mapped_column(Text, nullable=False)
    before: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    after: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    ip_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    actor: Mapped[User | None] = relationship(back_populates="audit_events")
