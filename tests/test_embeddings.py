"""Tests for T1.2 — embedding column + embeddings module.

The actual ``sentence-transformers`` model is NOT loaded in CI (it's a
[embeddings] extra; torch is heavy). Tests mock ``embed_batch`` to return
deterministic 384-d vectors so storage + retrieval logic is verified
without the model dependency.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest import mock

import pytest
from sqlalchemy import text

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.db.models import EMBEDDING_DIM

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def db_with_features(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "embed.db"))
    db.init_db()
    src = db.add_source(DataSource(name="src_a", path="/a.parquet"))
    for i in range(3):
        db.upsert_feature(
            Feature(
                name=f"src_a.col_{i}",
                data_source_id=src.id,
                column_name=f"col_{i}",
                dtype="float64",
                tags=["churn"] if i == 0 else [],
            )
        )
    return db


class TestEmbeddingColumn:
    def test_column_exists_on_features(self, db_with_features: LocalBackend) -> None:
        with db_with_features.session() as s:
            row = s.execute(text("PRAGMA table_info(features)")).all()
            cols = {r[1] for r in row}
        assert "embedding" in cols
        assert "embedding_updated_at" in cols

    def test_round_trip_via_session(self, db_with_features: LocalBackend) -> None:
        """Store a 384-d vector and read it back via the ORM.

        Write uses the bindparam-with-type pattern from production code in
        ``featcat/ai/embeddings.py``. Read uses the ORM model so SA's
        TypeDecorator result processor fires (raw ``text()`` SELECT
        wouldn't decode the JSON-text on sqlite).
        """
        from sqlalchemy import bindparam, select

        from featcat.db.embedding_type import Embedding
        from featcat.db.models import Feature as FeatureORM

        feat = db_with_features.get_feature_by_name("src_a.col_0")
        assert feat is not None
        vec = [0.01 * i for i in range(EMBEDDING_DIM)]
        stmt = text("UPDATE features SET embedding = :vec WHERE id = :id").bindparams(
            bindparam("vec", type_=Embedding(EMBEDDING_DIM))
        )
        with db_with_features.session() as s:
            s.execute(stmt, {"vec": vec, "id": feat.id})
            s.commit()
            retrieved = s.execute(select(FeatureORM.embedding).where(FeatureORM.id == feat.id)).scalar()
        assert isinstance(retrieved, list)
        assert len(retrieved) == EMBEDDING_DIM
        # Allow tiny float-string roundtrip noise (sqlite stores as JSON-text)
        assert all(abs(a - b) < 1e-9 for a, b in zip(retrieved, vec, strict=True))

    def test_null_embedding_is_default(self, db_with_features: LocalBackend) -> None:
        with db_with_features.session() as s:
            row = s.execute(text("SELECT embedding FROM features WHERE name = 'src_a.col_1'")).first()
        assert row is not None
        assert row[0] is None


class TestFeatureEmbedText:
    def test_text_includes_name_and_tags(self, db_with_features: LocalBackend) -> None:
        from featcat.ai.embeddings import feature_embed_text

        feat = db_with_features.get_feature_by_name("src_a.col_0")
        assert feat is not None
        result = feature_embed_text(feat)
        assert "src_a.col_0" in result
        assert "churn" in result

    def test_text_includes_doc_when_supplied(self, db_with_features: LocalBackend) -> None:
        from featcat.ai.embeddings import feature_embed_text

        feat = db_with_features.get_feature_by_name("src_a.col_1")
        assert feat is not None
        doc = {"short_description": "user churn signal", "long_description": "30d session count"}
        result = feature_embed_text(feat, doc=doc)
        assert "user churn signal" in result
        assert "30d session count" in result


class TestUpdateMissingEmbeddings:
    """Mocks embed_batch so the test runs without sentence-transformers."""

    def test_only_processes_missing_rows(self, db_with_features: LocalBackend) -> None:
        # Pre-populate one feature with an embedding so it's skipped.
        from sqlalchemy import bindparam

        from featcat.ai import embeddings as emb_mod
        from featcat.db.embedding_type import Embedding

        feat0 = db_with_features.get_feature_by_name("src_a.col_0")
        assert feat0 is not None
        existing_vec = [0.5] * EMBEDDING_DIM
        stmt = text("UPDATE features SET embedding = :v, embedding_updated_at = updated_at WHERE id = :id").bindparams(
            bindparam("v", type_=Embedding(EMBEDDING_DIM))
        )
        with db_with_features.session() as s:
            s.execute(stmt, {"v": existing_vec, "id": feat0.id})
            s.commit()

        fake_vec = [0.1] * EMBEDDING_DIM
        with mock.patch.object(emb_mod, "embed_batch", return_value=[fake_vec, fake_vec]):
            result = emb_mod.update_missing_embeddings(db_with_features, batch_size=32)

        # 2 features were missing (col_1, col_2); col_0 had an embedding.
        assert result["embedded"] == 2
        assert result["failed"] == 0

        # col_0's embedding wasn't overwritten — read via ORM so the
        # TypeDecorator decodes the JSON-text on sqlite.
        from sqlalchemy import select

        from featcat.db.models import Feature as FeatureORM

        with db_with_features.session() as s:
            retrieved = s.execute(select(FeatureORM.embedding).where(FeatureORM.id == feat0.id)).scalar()
        assert all(abs(a - b) < 1e-9 for a, b in zip(retrieved, existing_vec, strict=True))

    def test_dimension_mismatch_counts_as_failed(self, db_with_features: LocalBackend) -> None:
        from featcat.ai import embeddings as emb_mod

        wrong_vec = [0.1] * 10  # not 384
        with mock.patch.object(emb_mod, "embed_batch", return_value=[wrong_vec, wrong_vec, wrong_vec]):
            result = emb_mod.update_missing_embeddings(db_with_features, batch_size=32)
        assert result["embedded"] == 0
        assert result["failed"] == 3


class TestEmbeddingsAvailability:
    def test_available_returns_bool(self) -> None:
        from featcat.ai.embeddings import embeddings_available

        # Either True or False — we just assert it's a bool and doesn't raise.
        assert isinstance(embeddings_available(), bool)
