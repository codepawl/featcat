"""merge T2.1 notifications and T2.2a fts heads

Revision ID: 842a42f73f0f
Revises: 489ac96fd407, fc06fb939993
Create Date: 2026-05-06 10:00:39.008840

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '842a42f73f0f'
down_revision: Union[str, Sequence[str], None] = ('489ac96fd407', 'fc06fb939993')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
