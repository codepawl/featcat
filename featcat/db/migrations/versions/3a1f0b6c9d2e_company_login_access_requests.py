"""Company login access requests

Revision ID: 3a1f0b6c9d2e
Revises: c1e8aab7d231
Create Date: 2026-06-09 16:20:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "3a1f0b6c9d2e"
down_revision: Union[str, Sequence[str], None] = "c1e8aab7d231"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "access_requests",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=True),
        sa.Column("message", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("reviewed_by", sa.Text(), nullable=True),
        sa.Column("reviewed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="uq_access_requests_email"),
    )
    with op.batch_alter_table("access_requests", schema=None) as batch_op:
        batch_op.create_index("idx_access_requests_created_at", ["created_at"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("access_requests", schema=None) as batch_op:
        batch_op.drop_index("idx_access_requests_created_at")
    op.drop_table("access_requests")
