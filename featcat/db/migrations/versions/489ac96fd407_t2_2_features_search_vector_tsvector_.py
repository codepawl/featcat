"""T2.2 features search_vector tsvector (postgres-only)

Revision ID: 489ac96fd407
Revises: d6e943d39311
Create Date: 2026-05-06 09:39:49.214653

PostgreSQL: adds a stored generated ``tsvector`` column over
``name`` (weight A) + ``tags`` (B) + ``description`` (C), plus a GIN index
for fast ``@@`` queries. Uses the ``simple`` config (no stemming) since
catalogs mix English + Vietnamese.

SQLite: no-op. The runtime fall-back path in ``LocalBackend.full_text_search``
tokenizes + scans on sqlite.

Out of scope here: pulling ``feature_docs.short_description`` /
``long_description`` into the vector. That requires either a trigger or
a materialized view since the docs live on a separate table; deferred.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "489ac96fd407"
down_revision: str | Sequence[str] | None = "d6e943d39311"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute(
        """
        ALTER TABLE features ADD COLUMN search_vector tsvector
        GENERATED ALWAYS AS (
            setweight(to_tsvector('simple', coalesce(name, '')), 'A') ||
            setweight(to_tsvector('simple', coalesce(tags, '')), 'B') ||
            setweight(to_tsvector('simple', coalesce(description, '')), 'C')
        ) STORED
        """
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_features_search_vector "
        "ON features USING GIN (search_vector)"
    )


def downgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    op.execute("DROP INDEX IF EXISTS idx_features_search_vector")
    op.execute("ALTER TABLE features DROP COLUMN IF EXISTS search_vector")
