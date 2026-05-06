"""T1.2 features embedding column

Revision ID: d6e943d39311
Revises: 25c2acba0f39
Create Date: 2026-05-06 08:34:48.903576

Adds the ``embedding`` + ``embedding_updated_at`` columns to ``features``.

PostgreSQL: emits ``vector(384)`` via the pgvector extension and creates a
HNSW index over cosine distance for sub-100ms top-K queries even at 10k+
features. The migration ensures ``CREATE EXTENSION vector`` runs first.

SQLite: emits ``TEXT`` (JSON-encoded list of floats). Similarity *queries*
still go through the existing TF-IDF fallback path; the column merely
stores the embedding so it survives a sqlite→postgres migration without
regeneration.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

import featcat.db.embedding_type

# revision identifiers, used by Alembic.
revision: str = "d6e943d39311"
down_revision: str | Sequence[str] | None = "25c2acba0f39"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        # pgvector extension must exist before the column type resolves to
        # ``vector(384)``. Idempotent: noop if extension is already there.
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    with op.batch_alter_table("features", schema=None) as batch_op:
        batch_op.add_column(sa.Column("embedding", featcat.db.embedding_type.Embedding(), nullable=True))
        batch_op.add_column(sa.Column("embedding_updated_at", sa.TIMESTAMP(timezone=True), nullable=True))

    if is_postgres:
        # HNSW index on cosine distance — chosen over IVFFlat because it
        # doesn't need a build-time ``lists`` parameter and degrades
        # gracefully at small catalog sizes. ``embedding IS NULL`` rows are
        # skipped automatically by pgvector index scans.
        op.execute(
            "CREATE INDEX IF NOT EXISTS idx_features_embedding "
            "ON features USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    is_postgres = bind.dialect.name == "postgresql"

    if is_postgres:
        op.execute("DROP INDEX IF EXISTS idx_features_embedding")

    with op.batch_alter_table("features", schema=None) as batch_op:
        batch_op.drop_column("embedding_updated_at")
        batch_op.drop_column("embedding")

    # Intentionally do NOT ``DROP EXTENSION vector`` — other tables/indexes
    # could depend on it and the operator opted in via T1.2 explicitly.
