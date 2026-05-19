"""Tests for hybrid lexical+semantic ``search_features`` (Issue 3 fix).

The hybrid path merges FTS5 (or tsvector) hits with embedding-cosine hits via
Reciprocal Rank Fusion. ``sentence-transformers`` is NOT loaded here — its
heavy torch dependency is the [embeddings] extra and isn't in the default CI
profile. Tests either:

* run with the semantic branch disabled (``embeddings_available``→False), or
* stub ``embed_text`` and pre-populate row embeddings so the merge logic can be
  exercised end-to-end without the real model.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest import mock

import pytest
from sqlalchemy import bindparam, text

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.db.embedding_type import Embedding
from featcat.db.models import EMBEDDING_DIM

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def db_with_finance_features(tmp_path: Path) -> LocalBackend:
    """Catalog seeded with features the test queries will recognise.

    Covers EN ('billing'), VI ('doanh thu' — exercises the FTS5
    ``remove_diacritics=2`` tokenizer), and an unrelated feature so the
    'no match' case has a populated catalog to prove the empty result is
    real, not a setup miss.
    """
    db = LocalBackend(str(tmp_path / "hybrid.db"))
    db.init_db()
    billing_src = db.add_source(DataSource(name="billing", path="/b.parquet"))
    revenue_src = db.add_source(DataSource(name="revenue", path="/r.parquet"))
    weather_src = db.add_source(DataSource(name="weather", path="/w.parquet"))

    db.upsert_feature(
        Feature(
            name="billing.invoice_amount",
            data_source_id=billing_src.id,
            column_name="invoice_amount",
            dtype="float64",
            description="invoice total billed to the customer in USD",
            tags=["billing", "money"],
        )
    )
    db.upsert_feature(
        Feature(
            name="revenue.daily_total",
            data_source_id=revenue_src.id,
            column_name="daily_total",
            dtype="float64",
            description="doanh thu hằng ngày của chi nhánh",
            tags=["doanh-thu", "kpi"],
        )
    )
    db.upsert_feature(
        Feature(
            name="weather.temperature",
            data_source_id=weather_src.id,
            column_name="temperature",
            dtype="float64",
            description="ambient temperature in celsius",
            tags=["weather"],
        )
    )
    return db


class TestSearchFeaturesLexicalOnly:
    """Run with ``sentence-transformers`` reported absent so only the
    lexical branch fires. Proves the search_features → hybrid_search path
    keeps lexical-only behaviour intact when embeddings aren't usable."""

    def test_english_query_finds_feature(self, db_with_finance_features: LocalBackend) -> None:
        with mock.patch("featcat.ai.embeddings.embeddings_available", return_value=False):
            results = db_with_finance_features.search_features("billing")
        names = [f.name for f in results]
        assert "billing.invoice_amount" in names
        assert "weather.temperature" not in names

    def test_vietnamese_query_finds_feature(self, db_with_finance_features: LocalBackend) -> None:
        # FTS5 ``remove_diacritics=2`` tokenizer folds 'doanh thu' ↔ 'doanh
        # thu' (the description carries diacritics; the query may not).
        with mock.patch("featcat.ai.embeddings.embeddings_available", return_value=False):
            results = db_with_finance_features.search_features("doanh thu")
        names = [f.name for f in results]
        assert "revenue.daily_total" in names

    def test_no_match_returns_empty_list(self, db_with_finance_features: LocalBackend) -> None:
        with mock.patch("featcat.ai.embeddings.embeddings_available", return_value=False):
            results = db_with_finance_features.search_features("xxxxnomatchxxxx")
        assert results == []

    def test_empty_query_returns_empty(self, db_with_finance_features: LocalBackend) -> None:
        with mock.patch("featcat.ai.embeddings.embeddings_available", return_value=False):
            assert db_with_finance_features.search_features("") == []
            assert db_with_finance_features.search_features("   ") == []


class TestSearchFeaturesHybridMerge:
    """Stub ``embed_text`` + pre-populate row embeddings so the RRF merge of
    lexical and semantic candidates can be exercised end-to-end."""

    def _seed_embeddings(self, db: LocalBackend, vectors: dict[str, list[float]]) -> None:
        """Persist deterministic embeddings for the given feature names."""
        stmt = text("UPDATE features SET embedding = :vec WHERE name = :name").bindparams(
            bindparam("vec", type_=Embedding(EMBEDDING_DIM))
        )
        with db.session() as s:
            for name, vec in vectors.items():
                s.execute(stmt, {"vec": vec, "name": name})
            s.commit()

    def test_semantic_lifts_match_when_lexical_misses(self, db_with_finance_features: LocalBackend) -> None:
        """Lexical can't match 'payment' against any feature here (no token
        overlap), but the semantic branch points at billing.invoice_amount.
        The hybrid result must surface it via the embedding-only signal."""
        # Embed 'billing.invoice_amount' identically to the query vector;
        # the other two features get orthogonal vectors. all-MiniLM is
        # 384-dim, so the test vectors are too.
        money_vec = [1.0] + [0.0] * (EMBEDDING_DIM - 1)
        weather_vec = [0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 2)
        revenue_vec = [0.0, 0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 3)
        self._seed_embeddings(
            db_with_finance_features,
            {
                "billing.invoice_amount": money_vec,
                "weather.temperature": weather_vec,
                "revenue.daily_total": revenue_vec,
            },
        )
        with (
            mock.patch("featcat.ai.embeddings.embeddings_available", return_value=True),
            mock.patch("featcat.ai.embeddings.embed_text", return_value=money_vec),
        ):
            results = db_with_finance_features.search_features("payment")
        names = [f.name for f in results]
        # No lexical hit on 'payment', but the semantic branch finds the
        # nearest embedding (billing.invoice_amount).
        assert "billing.invoice_amount" in names
        assert names[0] == "billing.invoice_amount"

    def test_embedding_load_failure_falls_back_to_lexical(self, db_with_finance_features: LocalBackend) -> None:
        """``embed_text`` raising RuntimeError (model download failed, etc.)
        must not crash the search — it logs and keeps the lexical half."""
        with (
            mock.patch("featcat.ai.embeddings.embeddings_available", return_value=True),
            mock.patch(
                "featcat.ai.embeddings.embed_text",
                side_effect=RuntimeError("model unavailable"),
            ),
        ):
            results = db_with_finance_features.search_features("billing")
        names = [f.name for f in results]
        assert "billing.invoice_amount" in names


class TestSearchByEmbeddingSqlite:
    """Sanity-check the new SQLite cosine override directly so a regression
    on the matrix multiply is caught independently of the hybrid wrapper."""

    def test_returns_empty_when_no_row_has_embedding(self, db_with_finance_features: LocalBackend) -> None:
        vec = [0.0] * EMBEDDING_DIM
        assert db_with_finance_features.search_by_embedding(vec, top_k=5) == []

    def test_ranks_nearest_embedding_first(self, db_with_finance_features: LocalBackend) -> None:
        stmt = text("UPDATE features SET embedding = :vec WHERE name = :name").bindparams(
            bindparam("vec", type_=Embedding(EMBEDDING_DIM))
        )
        v_a = [1.0] + [0.0] * (EMBEDDING_DIM - 1)
        v_b = [0.5, 0.5] + [0.0] * (EMBEDDING_DIM - 2)
        v_c = [0.0, 1.0] + [0.0] * (EMBEDDING_DIM - 2)
        with db_with_finance_features.session() as s:
            s.execute(stmt, {"vec": v_a, "name": "billing.invoice_amount"})
            s.execute(stmt, {"vec": v_b, "name": "revenue.daily_total"})
            s.execute(stmt, {"vec": v_c, "name": "weather.temperature"})
            s.commit()
        # Query along the 'a' axis: a > b > c in cosine.
        results = db_with_finance_features.search_by_embedding(v_a, top_k=3)
        names = [r["name"] for r in results]
        assert names == ["billing.invoice_amount", "revenue.daily_total", "weather.temperature"]
        assert results[0]["similarity"] > results[1]["similarity"] > results[2]["similarity"]
