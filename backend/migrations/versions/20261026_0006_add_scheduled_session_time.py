"""Keep planned session start separately from actual start.

Revision ID: 20261026_0006
Revises: 20261026_0005
Create Date: 2026-10-26 18:20:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261026_0006"
down_revision: Union[str, None] = "20261026_0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("attendance_sessions", sa.Column("scheduled_for", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("attendance_sessions", "scheduled_for")
