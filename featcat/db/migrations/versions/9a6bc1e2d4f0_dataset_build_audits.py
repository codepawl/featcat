"""Dataset build audit table

Revision ID: 9a6bc1e2d4f0
Revises: 3b9d6e2c4a7f
Create Date: 2026-05-25 09:10:00.000000

Stores lightweight API/CLI training dataset build request records for
reproducibility and artifact traceability.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "9a6bc1e2d4f0"
down_revision: str | Sequence[str] | None = "3b9d6e2c4a7f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "dataset_build_audits",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("entity_df_path", sa.Text(), nullable=False),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("source_name", sa.Text(), nullable=True),
        sa.Column("output_path", sa.Text(), nullable=True),
        sa.Column("entity_key", sa.Text(), nullable=True),
        sa.Column("entity_timestamp_column", sa.Text(), nullable=True),
        sa.Column("source_event_timestamp_column", sa.Text(), nullable=True),
        sa.Column("feature_columns", sa.Text(), server_default="[]", nullable=False),
        sa.Column("row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("feature_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unresolved_row_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("missing_feature_value_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("errors", sa.Text(), server_default="[]", nullable=False),
        sa.Column("warnings", sa.Text(), server_default="[]", nullable=False),
        sa.Column("actor", sa.Text(), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_dataset_build_audits_created_at", "dataset_build_audits", ["created_at"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_dataset_build_audits_created_at", table_name="dataset_build_audits")
    op.drop_table("dataset_build_audits")
