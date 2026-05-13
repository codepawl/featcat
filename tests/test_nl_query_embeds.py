"""Tests for T1.2c — NL query embeds-first path.

The pgvector branch needs a live postgres + populated embeddings. These
tests stub the backend's ``backend`` attribute and ``search_by_embedding``
to verify routing without requiring postgres at unit-test time.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest import mock

import pytest

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.plugins.nl_query import NLQueryPlugin

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def db_with_three(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "nlq.db"))
    db.init_db()
    src = db.add_source(DataSource(name="src", path="/x.parquet"))
    for i in range(3):
        db.upsert_feature(
            Feature(
                name=f"src.col_{i}",
                data_source_id=src.id,
                column_name=f"col_{i}",
                dtype="float64",
            )
        )
    return db


class TestEmbedsFirstRouting:
    def test_sqlite_falls_through_to_fuzzy(self, db_with_three: LocalBackend) -> None:
        """SQLite has no pgvector; embedding path returns None and we
        fall through to the existing fuzzy/LLM-less code path."""
        plugin = NLQueryPlugin()
        result = plugin.execute(db_with_three, llm=None, query="col 1", fallback_only=True)
        assert result.status == "success"
        assert result.data["method"] == "fuzzy_search"

    def test_postgres_with_embeddings_uses_vector_path(self, db_with_three: LocalBackend) -> None:
        """Stub backend='postgres' and search_by_embedding to confirm the
        plugin returns the vector-similarity results directly when both
        the backend and the embedding service are available."""
        from featcat.ai import embeddings as emb_mod
        from featcat.plugins import nl_query as nl_mod

        canned_hits = [
            {"id": "f1", "name": "src.col_0", "dtype": "float64", "similarity": 0.91},
            {"id": "f2", "name": "src.col_1", "dtype": "float64", "similarity": 0.42},
        ]
        with (
            mock.patch.object(db_with_three, "backend", "postgres"),
            mock.patch.object(db_with_three, "search_by_embedding", return_value=canned_hits),
            mock.patch.object(emb_mod, "embeddings_available", return_value=True),
            mock.patch.object(emb_mod, "embed_text", return_value=[0.1] * 384),
        ):
            # Reach into the plugin module's import namespace too —
            # ``_embedding_search`` resolves embeddings_available/embed_text via
            # ``from ..ai.embeddings import ...`` lazily at call time.
            assert nl_mod._embedding_search(db_with_three, "anything") is not None
            plugin = NLQueryPlugin()
            result = plugin.execute(db_with_three, llm=None, query="user activity")
        assert result.status == "success"
        assert result.data["method"] == "embedding"
        assert [r["feature"] for r in result.data["results"]] == ["src.col_0", "src.col_1"]
        assert result.data["results"][0]["score"] == 0.91

    def test_embed_failure_falls_back(self, db_with_three: LocalBackend) -> None:
        """If embed_text raises (model load failure / bad input), the plugin
        must NOT crash — it should return None from _embedding_search and
        let the fuzzy/LLM path run."""
        from featcat.ai import embeddings as emb_mod

        with (
            mock.patch.object(db_with_three, "backend", "postgres"),
            mock.patch.object(emb_mod, "embeddings_available", return_value=True),
            mock.patch.object(emb_mod, "embed_text", side_effect=RuntimeError("boom")),
        ):
            plugin = NLQueryPlugin()
            result = plugin.execute(db_with_three, llm=None, query="anything", fallback_only=True)
        # fallback_only=True forces fuzzy when embed_first returns None.
        assert result.status == "success"
        assert result.data["method"] == "fuzzy_search"

    def test_fallback_only_skips_embeddings(self, db_with_three: LocalBackend) -> None:
        """``fallback_only=True`` should bypass the embed-first path even
        on postgres — useful for users who explicitly want fuzzy."""
        from featcat.ai import embeddings as emb_mod

        with (
            mock.patch.object(db_with_three, "backend", "postgres"),
            mock.patch.object(
                db_with_three,
                "search_by_embedding",
                return_value=[{"id": "f1", "name": "src.col_0", "dtype": "float64", "similarity": 0.91}],
            ),
            mock.patch.object(emb_mod, "embeddings_available", return_value=True),
            mock.patch.object(emb_mod, "embed_text", return_value=[0.1] * 384),
        ):
            plugin = NLQueryPlugin()
            result = plugin.execute(db_with_three, llm=None, query="anything", fallback_only=True)
        assert result.data["method"] == "fuzzy_search"
