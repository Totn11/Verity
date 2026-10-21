"""Prevent changes to persisted audit events.

Revision ID: 20261021_0002
Revises: 20261021_0001
Create Date: 2026-10-21 16:30:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261021_0002"
down_revision: Union[str, None] = "20261021_0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE FUNCTION reject_audit_event_mutation()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            RAISE EXCEPTION 'audit_events is append-only'
                USING ERRCODE = '55000';
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_events_append_only
        BEFORE UPDATE OR DELETE ON audit_events
        FOR EACH ROW
        EXECUTE FUNCTION reject_audit_event_mutation()
        """
    )


def downgrade() -> None:
    op.execute(
        "DROP TRIGGER trg_audit_events_append_only ON audit_events"
    )
    op.execute("DROP FUNCTION reject_audit_event_mutation()")
