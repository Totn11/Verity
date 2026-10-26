"""Add classroom attendance domain tables.

Revision ID: 20261026_0004
Revises: 20261021_0003
Create Date: 2026-10-26 18:00:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20261026_0004"
down_revision: Union[str, None] = "20261021_0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

session_status = postgresql.ENUM(
    "scheduled", "open", "closed", name="attendance_session_status", create_type=False
)
attendance_mark = postgresql.ENUM(
    "present", "late", "absent", "excused", name="attendance_mark", create_type=False
)
attendance_method = postgresql.ENUM(
    "manual", "face_recognition", "offline_sync", name="attendance_method", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    session_status.create(bind, checkfirst=True)
    attendance_mark.create(bind, checkfirst=True)
    attendance_method.create(bind, checkfirst=True)

    op.create_table(
        "students",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_number", sa.String(64), nullable=False),
        sa.Column("first_name", sa.String(120), nullable=False),
        sa.Column("last_name", sa.String(120), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=True),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_students"),
        sa.UniqueConstraint("student_number", name="uq_students_student_number"),
    )
    op.create_index(
        "uq_students_email",
        "students",
        ["email"],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )

    op.create_table(
        "semesters",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("starts_on <= ends_on", name="valid_date_range"),
        sa.PrimaryKeyConstraint("id", name="pk_semesters"),
        sa.UniqueConstraint("name", name="uq_semesters_name"),
    )
    op.create_table(
        "courses",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.String(64), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_courses"),
        sa.UniqueConstraint("code", name="uq_courses_code"),
    )
    op.create_table(
        "class_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("course_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("semester_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lecturer_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("section_code", sa.String(64), nullable=False),
        sa.Column("classroom_label", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["course_id"], ["courses.id"], name="fk_class_sections_course_id_courses"),
        sa.ForeignKeyConstraint(["semester_id"], ["semesters.id"], name="fk_class_sections_semester_id_semesters"),
        sa.ForeignKeyConstraint(["lecturer_user_id"], ["users.id"], name="fk_class_sections_lecturer_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_class_sections"),
        sa.UniqueConstraint("course_id", "semester_id", "section_code", name="uq_class_sections_course_term_code"),
    )
    op.create_table(
        "course_enrollments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("class_section_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("enrolled_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["class_section_id"], ["class_sections.id"], name="fk_course_enrollments_section"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], name="fk_course_enrollments_student"),
        sa.PrimaryKeyConstraint("id", name="pk_course_enrollments"),
        sa.UniqueConstraint("class_section_id", "student_id", name="uq_course_enrollments_section_student"),
    )
    op.create_table(
        "attendance_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("class_section_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", session_status, server_default=sa.text("'open'"), nullable=False),
        sa.Column("confidence_threshold", sa.Numeric(4, 3), server_default=sa.text("0.800"), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("confidence_threshold > 0 AND confidence_threshold < 1", name="confidence_range"),
        sa.ForeignKeyConstraint(["class_section_id"], ["class_sections.id"], name="fk_attendance_sessions_section"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], name="fk_attendance_sessions_creator"),
        sa.PrimaryKeyConstraint("id", name="pk_attendance_sessions"),
    )
    op.create_index(
        "ix_attendance_sessions_section_started",
        "attendance_sessions",
        ["class_section_id", "started_at"],
    )
    op.create_table(
        "session_attendance_records",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mark", attendance_mark, nullable=False),
        sa.Column("method", attendance_method, nullable=False),
        sa.Column("confidence", sa.Numeric(5, 4), nullable=True),
        sa.Column("source_event_id", sa.String(255), nullable=True),
        sa.Column("marked_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("confidence IS NULL OR (confidence >= 0 AND confidence <= 1)", name="confidence_range"),
        sa.ForeignKeyConstraint(["session_id"], ["attendance_sessions.id"], name="fk_session_attendance_session"),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], name="fk_session_attendance_student"),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"], name="fk_session_attendance_actor"),
        sa.PrimaryKeyConstraint("id", name="pk_session_attendance_records"),
        sa.UniqueConstraint("session_id", "student_id", name="uq_session_attendance_session_student"),
    )
    op.create_index(
        "uq_session_attendance_source_event",
        "session_attendance_records",
        ["source_event_id"],
        unique=True,
        postgresql_where=sa.text("source_event_id IS NOT NULL"),
    )
    op.create_table(
        "face_templates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("student_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("encrypted_template", sa.LargeBinary(), nullable=False),
        sa.Column("encryption_key_id", sa.String(128), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("consented_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["student_id"], ["students.id"], ondelete="CASCADE", name="fk_face_templates_student"),
        sa.PrimaryKeyConstraint("id", name="pk_face_templates"),
        sa.UniqueConstraint("student_id", name="uq_face_templates_student_id"),
    )


def downgrade() -> None:
    op.drop_table("face_templates")
    op.drop_index("uq_session_attendance_source_event", table_name="session_attendance_records")
    op.drop_table("session_attendance_records")
    op.drop_index("ix_attendance_sessions_section_started", table_name="attendance_sessions")
    op.drop_table("attendance_sessions")
    op.drop_table("course_enrollments")
    op.drop_table("class_sections")
    op.drop_table("courses")
    op.drop_table("semesters")
    op.drop_index("uq_students_email", table_name="students")
    op.drop_table("students")
    attendance_method.drop(op.get_bind(), checkfirst=True)
    attendance_mark.drop(op.get_bind(), checkfirst=True)
    session_status.drop(op.get_bind(), checkfirst=True)
