"""Data source join metadata for offline dataset building

Revision ID: 3b9d6e2c4a7f
Revises: c1e8aab7d231
Create Date: 2026-05-25 06:10:00.000000

Adds optional source-level join metadata used by future offline training
dataset builders and point-in-time joins. All columns are nullable so existing
catalogs remain valid without a backfill.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "3b9d6e2c4a7f"
down_revision: str | Sequence[str] | None = "c1e8aab7d231"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("data_sources", schema=None) as batch_op:
        batch_op.add_column(sa.Column("entity_key", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("event_timestamp_column", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("created_timestamp_column", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("data_sources", schema=None) as batch_op:
        batch_op.drop_column("created_timestamp_column")
        batch_op.drop_column("event_timestamp_column")
        batch_op.drop_column("entity_key")
