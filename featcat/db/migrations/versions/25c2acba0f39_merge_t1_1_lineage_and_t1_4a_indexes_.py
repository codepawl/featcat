"""merge T1.1 lineage and T1.4a indexes branches

Revision ID: 25c2acba0f39
Revises: b4de1aac246b, f871e02d23fb
Create Date: 2026-05-06 08:34:19.565474

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '25c2acba0f39'
down_revision: Union[str, Sequence[str], None] = ('b4de1aac246b', 'f871e02d23fb')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    pass


def downgrade() -> None:
    """Downgrade schema."""
    pass
