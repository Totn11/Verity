"""Add recognition audit metadata and durable attendance sync outbox.

Revision ID: 20261026_0008
Revises: 20261026_0007
Create Date: 2026-10-26 18:45:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "20261026_0008"
down_revision: Union[str, None] = "20261026_0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("face_templates", sa.Column("model_sha256", sa.String(64), nullable=True))
    op.add_column("face_templates", sa.Column("consent_record_id", sa.String(255), nullable=True))
    op.add_column(
        "face_templates",
        sa.Column(
            "consent_actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", name="fk_face_templates_consent_actor"),
            nullable=True,
        ),
    )
    op.create_index(
        "ix_face_templates_expires_at",
        "face_templates",
        ["expires_at"],
        postgresql_where=sa.text("revoked_at IS NULL"),
    )

    op.create_table(
        "face_recognition_attempts",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column(
            "session_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("attendance_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "actor_user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id"),
            nullable=False,
        ),
        sa.Column("outcome", sa.String(32), nullable=False),
        sa.Column("model_version", sa.String(128), nullable=False),
        sa.Column("detector_sha256", sa.String(64), nullable=True),
        sa.Column("embedder_sha256", sa.String(64), nullable=True),
        sa.Column("inference_ms", sa.Integer(), nullable=False),
        sa.Column("quality_metrics", postgresql.JSONB(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "outcome IN ('matched', 'uncertain', 'no_face', 'multiple_faces', "
            "'quality_rejected', 'model_unavailable', 'error')",
            name="outcome_valid",
        ),
        sa.CheckConstraint(
            "inference_ms >= 0",
            name="inference_duration_nonnegative",
        ),
        sa.PrimaryKeyConstraint("id", name="pk_face_recognition_attempts"),
    )
    op.create_index(
        "ix_face_recognition_attempts_session_created",
        "face_recognition_attempts",
        ["session_id", "created_at"],
    )

    op.create_table(
        "attendance_sync_outbox",
        sa.Column("event_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(), nullable=False),
        sa.Column(
            "status",
            sa.String(16),
            server_default=sa.text("'pending'"),
            nullable=False,
        ),
        sa.Column(
            "attempt_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('pending', 'synced', 'conflict')",
            name="status_valid",
        ),
        sa.CheckConstraint(
            "attempt_count >= 0",
            name="attempt_count_nonnegative",
        ),
        sa.PrimaryKeyConstraint("event_id", name="pk_attendance_sync_outbox"),
    )
    op.create_index(
        "ix_attendance_sync_outbox_status_created",
        "attendance_sync_outbox",
        ["status", "created_at"],
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.exec_driver_sql("SELECT EXISTS (SELECT 1 FROM attendance_sync_outbox)").scalar():
        raise RuntimeError("Export or reconcile attendance sync events before downgrading 20261026_0008.")
    if bind.exec_driver_sql("SELECT EXISTS (SELECT 1 FROM face_recognition_attempts)").scalar():
        raise RuntimeError("Export recognition audit events before downgrading 20261026_0008.")
    if bind.exec_driver_sql(
        "SELECT EXISTS (SELECT 1 FROM face_templates "
        "WHERE model_sha256 IS NOT NULL OR consent_record_id IS NOT NULL "
        "OR consent_actor_user_id IS NOT NULL)"
    ).scalar():
        raise RuntimeError("Preserve enrolled-template consent metadata before downgrading 20261026_0008.")

    op.drop_index("ix_attendance_sync_outbox_status_created", table_name="attendance_sync_outbox")
    op.drop_table("attendance_sync_outbox")
    op.drop_index(
        "ix_face_recognition_attempts_session_created",
        table_name="face_recognition_attempts",
    )
    op.drop_table("face_recognition_attempts")
    op.drop_index("ix_face_templates_expires_at", table_name="face_templates")
    op.drop_column("face_templates", "consent_actor_user_id")
    op.drop_column("face_templates", "consent_record_id")
    op.drop_column("face_templates", "model_sha256")
