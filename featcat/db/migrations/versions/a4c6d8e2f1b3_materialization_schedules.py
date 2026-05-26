"""Materialization schedules

Revision ID: a4c6d8e2f1b3
Revises: e7a1c3d9b5a2
Create Date: 2026-05-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a4c6d8e2f1b3"
down_revision: str | Sequence[str] | None = "e7a1c3d9b5a2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "materialization_schedules",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("name", sa.Text(), nullable=False, unique=True),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("feature_columns", sa.Text(), server_default="[]", nullable=False),
        sa.Column("project", sa.Text(), server_default="", nullable=False),
        sa.Column("feature_view", sa.Text(), server_default="", nullable=False),
        sa.Column("schedule_type", sa.Text(), server_default="interval", nullable=False),
        sa.Column("interval_seconds", sa.Integer(), nullable=False),
        sa.Column("cron_expression", sa.Text(), nullable=True),
        sa.Column("enabled", sa.Integer(), server_default="1", nullable=False),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("last_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("lease_owner", sa.Text(), nullable=True),
        sa.Column("lease_until", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_materialization_schedules_due",
        "materialization_schedules",
        ["enabled", "next_run_at"],
        unique=False,
    )
    op.create_index(
        "idx_materialization_schedules_lease",
        "materialization_schedules",
        ["lease_until"],
        unique=False,
    )
    op.create_index(
        "idx_materialization_schedules_source",
        "materialization_schedules",
        ["source_name"],
        unique=False,
    )
    op.add_column("materialization_audits", sa.Column("schedule_id", sa.Text(), nullable=True))
    op.create_index(
        "idx_materialization_audits_schedule_created",
        "materialization_audits",
        ["schedule_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_materialization_audits_schedule_created", table_name="materialization_audits")
    op.drop_column("materialization_audits", "schedule_id")
    op.drop_index("idx_materialization_schedules_source", table_name="materialization_schedules")
    op.drop_index("idx_materialization_schedules_lease", table_name="materialization_schedules")
    op.drop_index("idx_materialization_schedules_due", table_name="materialization_schedules")
    op.drop_table("materialization_schedules")
