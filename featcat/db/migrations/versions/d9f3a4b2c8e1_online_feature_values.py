"""Online feature values table

Revision ID: d9f3a4b2c8e1
Revises: 9a6bc1e2d4f0
Create Date: 2026-05-25 10:30:00.000000

Stores latest online feature values for PostgreSQL-backed serving. Values and
entity keys are JSON-serialized by the application so SQLite service tests and
PostgreSQL deployments share the same model shape.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d9f3a4b2c8e1"
down_revision: str | Sequence[str] | None = "9a6bc1e2d4f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "online_feature_values",
        sa.Column("project", sa.Text(), server_default="", nullable=False),
        sa.Column("feature_view", sa.Text(), server_default="", nullable=False),
        sa.Column("feature_ref", sa.Text(), nullable=False),
        sa.Column("entity_key_hash", sa.Text(), nullable=False),
        sa.Column("entity_key_json", sa.Text(), nullable=False),
        sa.Column("value_json", sa.Text(), nullable=True),
        sa.Column("value_dtype", sa.Text(), nullable=True),
        sa.Column("event_timestamp", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("created_timestamp", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("source_name", sa.Text(), nullable=True),
        sa.Column("source_path", sa.Text(), nullable=True),
        sa.Column("written_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("write_id", sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint(
            "project",
            "feature_view",
            "feature_ref",
            "entity_key_hash",
            name="pk_online_feature_values",
        ),
    )
    op.create_index(
        "idx_online_feature_values_lookup",
        "online_feature_values",
        ["project", "feature_view", "entity_key_hash"],
        unique=False,
    )
    op.create_index(
        "idx_online_feature_values_feature",
        "online_feature_values",
        ["project", "feature_view", "feature_ref"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_online_feature_values_feature", table_name="online_feature_values")
    op.drop_index("idx_online_feature_values_lookup", table_name="online_feature_values")
    op.drop_table("online_feature_values")
