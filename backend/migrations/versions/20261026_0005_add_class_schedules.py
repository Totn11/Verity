"""Add explicit weekly class schedule fields.

Revision ID: 20261026_0005
Revises: 20261026_0004
Create Date: 2026-10-26 18:10:00
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "20261026_0005"
down_revision: Union[str, None] = "20261026_0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("class_sections", sa.Column("schedule_weekday", sa.Integer(), nullable=True))
    op.add_column("class_sections", sa.Column("schedule_starts_at", sa.Time(), nullable=True))
    op.add_column("class_sections", sa.Column("schedule_ends_at", sa.Time(), nullable=True))
    op.create_check_constraint(
        "schedule_weekday_range",
        "class_sections",
        "schedule_weekday IS NULL OR schedule_weekday BETWEEN 0 AND 6",
    )
    op.create_check_constraint(
        "schedule_time_pair",
        "class_sections",
        "(schedule_starts_at IS NULL AND schedule_ends_at IS NULL) OR "
        "(schedule_starts_at IS NOT NULL AND schedule_ends_at IS NOT NULL "
        "AND schedule_starts_at < schedule_ends_at)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_class_sections_schedule_time_pair", "class_sections", type_="check")
    op.drop_constraint("ck_class_sections_schedule_weekday_range", "class_sections", type_="check")
    op.drop_column("class_sections", "schedule_ends_at")
    op.drop_column("class_sections", "schedule_starts_at")
    op.drop_column("class_sections", "schedule_weekday")
