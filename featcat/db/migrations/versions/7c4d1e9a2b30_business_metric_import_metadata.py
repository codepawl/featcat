"""Business metric import metadata

Revision ID: 7c4d1e9a2b30
Revises: a4c6d8e2f1b3, 3a1f0b6c9d2e
Create Date: 2026-06-22 10:00:00.000000

Adds optional metadata needed to preserve imported CX/Cus360 metric catalog
fields without forcing a technical feature mapping at import time.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7c4d1e9a2b30"
down_revision: str | Sequence[str] | None = ("a4c6d8e2f1b3", "3a1f0b6c9d2e")
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("business_metrics", schema=None) as batch_op:
        batch_op.add_column(sa.Column("external_id", sa.Text(), server_default="", nullable=False))
        batch_op.add_column(sa.Column("source_systems", sa.Text(), server_default="[]", nullable=False))
        batch_op.add_column(sa.Column("implementation_status", sa.Text(), server_default="unknown", nullable=False))
        batch_op.add_column(sa.Column("source_view", sa.Text(), server_default="", nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("business_metrics", schema=None) as batch_op:
        batch_op.drop_column("source_view")
        batch_op.drop_column("implementation_status")
        batch_op.drop_column("source_systems")
        batch_op.drop_column("external_id")
