"""Add the lecturer role for class ownership and attendance.

Revision ID: 20261026_0007
Revises: 20261026_0006
Create Date: 2026-10-26 18:30:00
"""

from typing import Sequence, Union

from alembic import op

revision: str = "20261026_0007"
down_revision: Union[str, None] = "20261026_0006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE user_role ADD VALUE IF NOT EXISTS 'lecturer'")


def downgrade() -> None:
    # PostgreSQL cannot drop an enum value safely; retaining it is backward-compatible.
    pass
