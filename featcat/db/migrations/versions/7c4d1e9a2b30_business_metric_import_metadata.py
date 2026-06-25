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
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("business_metrics"):
        op.create_table(
            "business_metrics",
            sa.Column("id", sa.Text(), primary_key=True),
            sa.Column("name", sa.Text(), nullable=False, unique=True),
            sa.Column("business_metric_name", sa.Text(), nullable=False),
            sa.Column("business_definition", sa.Text(), server_default=""),
            sa.Column("metric_domain", sa.Text(), nullable=False),
            sa.Column("lifecycle_stage", sa.Text(), nullable=False),
            sa.Column("metric_group", sa.Text(), server_default=""),
            sa.Column("metric_level", sa.Text(), nullable=False),
            sa.Column("entity_grain", sa.Text(), nullable=False),
            sa.Column("aggregation_rule", sa.Text(), server_default=""),
            sa.Column("mapped_features", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("owner", sa.Text(), server_default=""),
            sa.Column("lifecycle_status", sa.Text(), nullable=False, server_default="draft"),
            sa.Column("allowed_use_cases", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("external_id", sa.Text(), nullable=False, server_default=""),
            sa.Column("source_systems", sa.Text(), nullable=False, server_default="[]"),
            sa.Column("implementation_status", sa.Text(), nullable=False, server_default="unknown"),
            sa.Column("source_view", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
            sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        )
        op.create_index("idx_business_metrics_domain", "business_metrics", ["metric_domain"])
        op.create_index("idx_business_metrics_stage", "business_metrics", ["lifecycle_stage"])
        op.create_index("idx_business_metrics_level", "business_metrics", ["metric_level"])
        op.create_index("idx_business_metrics_owner", "business_metrics", ["owner"])
        return

    columns = {column["name"] for column in inspector.get_columns("business_metrics")}
    with op.batch_alter_table("business_metrics", schema=None) as batch_op:
        if "external_id" not in columns:
            batch_op.add_column(sa.Column("external_id", sa.Text(), server_default="", nullable=False))
        if "source_systems" not in columns:
            batch_op.add_column(sa.Column("source_systems", sa.Text(), server_default="[]", nullable=False))
        if "implementation_status" not in columns:
            batch_op.add_column(sa.Column("implementation_status", sa.Text(), server_default="unknown", nullable=False))
        if "source_view" not in columns:
            batch_op.add_column(sa.Column("source_view", sa.Text(), server_default="", nullable=False))


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    if not inspector.has_table("business_metrics"):
        return

    columns = {column["name"] for column in inspector.get_columns("business_metrics")}
    with op.batch_alter_table("business_metrics", schema=None) as batch_op:
        if "source_view" in columns:
            batch_op.drop_column("source_view")
        if "implementation_status" in columns:
            batch_op.drop_column("implementation_status")
        if "source_systems" in columns:
            batch_op.drop_column("source_systems")
        if "external_id" in columns:
            batch_op.drop_column("external_id")
