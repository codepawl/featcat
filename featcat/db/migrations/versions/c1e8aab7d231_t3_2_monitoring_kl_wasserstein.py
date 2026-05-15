"""T3.2 monitoring_checks: KL divergence and Wasserstein distance columns

Revision ID: c1e8aab7d231
Revises: 48172b100cdf
Create Date: 2026-05-15 17:00:00.000000

Adds two supplementary distribution-shift metrics computed alongside PSI
on every drift check. Both are nullable so legacy rows survive untouched
and the chart can render gaps where the metric wasn't recorded.

- kl_divergence (REAL): KL(current || baseline) on a 20-bin histogram of
  the deterministic Gaussian proxy. Sensitive to low-density region
  shifts that PSI flattens out.
- wasserstein (REAL): 1-Wasserstein (earth-mover's) distance between
  baseline and current sample sets. Reports the shift in the feature's
  original units (unlike PSI's unitless score).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c1e8aab7d231"
down_revision: str | Sequence[str] | None = "48172b100cdf"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("monitoring_checks", schema=None) as batch_op:
        batch_op.add_column(sa.Column("kl_divergence", sa.REAL(), nullable=True))
        batch_op.add_column(sa.Column("wasserstein", sa.REAL(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("monitoring_checks", schema=None) as batch_op:
        batch_op.drop_column("wasserstein")
        batch_op.drop_column("kl_divergence")
