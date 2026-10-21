"""Create the initial Verity facility schema.

Revision ID: 20261021_0001
Revises:
Create Date: 2026-10-21 15:44:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20261021_0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

user_role = postgresql.ENUM("admin", "staff", name="user_role", create_type=False)
person_status = postgresql.ENUM(
    "active", "inactive", "visitor", name="person_status", create_type=False
)
attendance_kind = postgresql.ENUM(
    "check_in", "check_out", name="attendance_kind", create_type=False
)
event_source = postgresql.ENUM(
    "terminal", "manual", "import", name="event_source", create_type=False
)
recognition_outcome = postgresql.ENUM(
    "match", "no_match", "error", name="recognition_outcome", create_type=False
)


def upgrade() -> None:
    bind = op.get_bind()
    op.execute("CREATE EXTENSION IF NOT EXISTS citext")
    user_role.create(bind, checkfirst=True)
    person_status.create(bind, checkfirst=True)
    attendance_kind.create(bind, checkfirst=True)
    event_source.create(bind, checkfirst=True)
    recognition_outcome.create(bind, checkfirst=True)

    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("role", user_role, nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_users"),
        sa.UniqueConstraint("email", name="uq_users_email"),
    )
    op.create_table(
        "people",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("external_ref", sa.Text(), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("email", postgresql.CITEXT(), nullable=False),
        sa.Column("phone", sa.String(length=64), nullable=False),
        sa.Column("department", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("status", person_status, nullable=False),
        sa.Column("photo_url", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.PrimaryKeyConstraint("id", name="pk_people"),
        sa.UniqueConstraint("external_ref", name="uq_people_external_ref"),
    )
    op.create_table(
        "rooms",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("floor", sa.Integer(), nullable=False),
        sa.Column("capacity", sa.Integer(), nullable=False),
        sa.Column("pos_x", sa.Numeric(), nullable=False),
        sa.Column("pos_y", sa.Numeric(), nullable=False),
        sa.PrimaryKeyConstraint("id", name="pk_rooms"),
        sa.UniqueConstraint("code", name="uq_rooms_code"),
    )
    op.create_table(
        "sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.Text(), nullable=False),
        sa.Column(
            "issued_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "expires_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=False),
        sa.Column("ip_hash", sa.Text(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_sessions_user_id_users"),
        sa.PrimaryKeyConstraint("id", name="pk_sessions"),
        sa.UniqueConstraint("token_hash", name="uq_sessions_token_hash"),
    )
    op.create_table(
        "attendance_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", attendance_kind, nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("source", event_source, nullable=False),
        sa.Column("source_event_id", sa.Text(), nullable=True),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name="fk_attendance_events_actor_user_id_users"
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["people.id"], name="fk_attendance_events_person_id_people"
        ),
        sa.ForeignKeyConstraint(
            ["room_id"], ["rooms.id"], name="fk_attendance_events_room_id_rooms"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_attendance_events"),
    )
    op.create_index(
        "ix_attendance_events_person_occurred_at",
        "attendance_events",
        ["person_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "uq_attendance_events_source_event_id",
        "attendance_events",
        ["source", "source_event_id"],
        unique=True,
        postgresql_where=sa.text("source_event_id IS NOT NULL"),
    )
    op.create_table(
        "recognition_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("score", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("threshold", sa.Numeric(precision=5, scale=4), nullable=False),
        sa.Column("outcome", recognition_outcome, nullable=False),
        sa.Column("model_version", sa.Text(), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["people.id"], name="fk_recognition_events_person_id_people"
        ),
        sa.ForeignKeyConstraint(
            ["room_id"], ["rooms.id"], name="fk_recognition_events_room_id_rooms"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_recognition_events"),
    )
    op.create_table(
        "location_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("person_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("room_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.Column("source", event_source, nullable=False),
        sa.Column("source_event_id", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["person_id"], ["people.id"], name="fk_location_events_person_id_people"
        ),
        sa.ForeignKeyConstraint(["room_id"], ["rooms.id"], name="fk_location_events_room_id_rooms"),
        sa.PrimaryKeyConstraint("id", name="pk_location_events"),
    )
    op.create_index(
        "ix_location_events_person_occurred_at",
        "location_events",
        ["person_id", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "uq_location_events_source_event_id",
        "location_events",
        ["source", "source_event_id"],
        unique=True,
        postgresql_where=sa.text("source_event_id IS NOT NULL"),
    )
    op.create_table(
        "audit_events",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.Text(), nullable=False),
        sa.Column("entity_type", sa.Text(), nullable=False),
        sa.Column("entity_id", sa.Text(), nullable=False),
        sa.Column("before", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("after", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("request_id", sa.Text(), nullable=False),
        sa.Column("ip_hash", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False
        ),
        sa.ForeignKeyConstraint(
            ["actor_user_id"], ["users.id"], name="fk_audit_events_actor_user_id_users"
        ),
        sa.PrimaryKeyConstraint("id", name="pk_audit_events"),
    )


def downgrade() -> None:
    op.drop_table("audit_events")
    op.drop_index(
        "uq_location_events_source_event_id", table_name="location_events"
    )
    op.drop_index(
        "ix_location_events_person_occurred_at", table_name="location_events"
    )
    op.drop_table("location_events")
    op.drop_table("recognition_events")
    op.drop_index(
        "uq_attendance_events_source_event_id", table_name="attendance_events"
    )
    op.drop_index(
        "ix_attendance_events_person_occurred_at", table_name="attendance_events"
    )
    op.drop_table("attendance_events")
    op.drop_table("sessions")
    op.drop_table("rooms")
    op.drop_table("people")
    op.drop_table("users")

    bind = op.get_bind()
    recognition_outcome.drop(bind, checkfirst=True)
    event_source.drop(bind, checkfirst=True)
    attendance_kind.drop(bind, checkfirst=True)
    person_status.drop(bind, checkfirst=True)
    user_role.drop(bind, checkfirst=True)
    op.execute("DROP EXTENSION IF EXISTS citext")
