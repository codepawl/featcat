"""Materialization audit table

Revision ID: e7a1c3d9b5a2
Revises: d9f3a4b2c8e1
Create Date: 2026-05-26 00:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "e7a1c3d9b5a2"
down_revision: str | Sequence[str] | None = "d9f3a4b2c8e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "materialization_audits",
        sa.Column("id", sa.Text(), primary_key=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source_name", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("project", sa.Text(), server_default="", nullable=False),
        sa.Column("feature_view", sa.Text(), server_default="", nullable=False),
        sa.Column("entity_key", sa.Text(), nullable=True),
        sa.Column("event_timestamp_column", sa.Text(), nullable=True),
        sa.Column("created_timestamp_column", sa.Text(), nullable=True),
        sa.Column("feature_columns", sa.Text(), server_default="[]", nullable=False),
        sa.Column("entity_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("feature_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("requested", sa.Integer(), server_default="0", nullable=False),
        sa.Column("written", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_older", sa.Integer(), server_default="0", nullable=False),
        sa.Column("skipped_same_timestamp", sa.Integer(), server_default="0", nullable=False),
        sa.Column("errors", sa.Text(), server_default="[]", nullable=False),
        sa.Column("warnings", sa.Text(), server_default="[]", nullable=False),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index(
        "idx_materialization_audits_created_at",
        "materialization_audits",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_materialization_audits_created_at", table_name="materialization_audits")
    op.drop_table("materialization_audits")
