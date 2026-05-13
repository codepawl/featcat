"""Tests for T2.2a — full-text search backend + endpoint.

The postgres tsvector path is exercised in operator-side integration runs
(needs a live postgres + the migration applied). These unit tests run
against the sqlite fallback path which uses in-process token scanning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def db_with_features(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "fts.db"))
    db.init_db()
    user_src = db.add_source(DataSource(name="user_behavior", path="/u.parquet"))
    weather_src = db.add_source(DataSource(name="weather", path="/w.parquet"))
    db.upsert_feature(
        Feature(
            name="user_behavior.session_count_30d",
            data_source_id=user_src.id,
            column_name="session_count_30d",
            dtype="int64",
            description="count of user sessions in the last 30 days",
            tags=["churn", "engagement"],
        )
    )
    db.upsert_feature(
        Feature(
            name="user_behavior.event_count_30d",
            data_source_id=user_src.id,
            column_name="event_count_30d",
            dtype="int64",
            description="count of user events in the last 30 days",
            tags=["engagement"],
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
    db.save_feature_doc(
        db.get_feature_by_name("user_behavior.session_count_30d").id,
        {"short_description": "30d sessions"},
    )
    return db


def _client(db: LocalBackend) -> TestClient:
    from featcat.server import create_app
    from featcat.server.deps import get_db

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


# --------------------------------------------------------------------------- #
# Backend                                                                     #
# --------------------------------------------------------------------------- #


class TestFullTextSearchSqlite:
    def test_token_match_ranks_by_hits(self, db_with_features: LocalBackend) -> None:
        results = db_with_features.full_text_search("user sessions")
        names = [r["name"] for r in results]
        # Both user_behavior.* features hit; session-named feature should rank
        # higher because the literal substring 'session' appears in name.
        assert "user_behavior.session_count_30d" in names
        assert results[0]["name"] == "user_behavior.session_count_30d"
        # Weather feature shouldn't appear — neither token matches.
        assert "weather.temperature" not in names

    def test_source_filter_pushdown(self, db_with_features: LocalBackend) -> None:
        results = db_with_features.full_text_search("count", source="user_behavior")
        assert all(r["name"].startswith("user_behavior.") for r in results)

    def test_dtype_filter(self, db_with_features: LocalBackend) -> None:
        results = db_with_features.full_text_search("count", dtype="float64")
        assert results == []  # both count features are int64

    def test_has_doc_true_filters(self, db_with_features: LocalBackend) -> None:
        results = db_with_features.full_text_search("count", has_doc=True)
        names = {r["name"] for r in results}
        assert names == {"user_behavior.session_count_30d"}

    def test_has_doc_false_filters(self, db_with_features: LocalBackend) -> None:
        results = db_with_features.full_text_search("count", has_doc=False)
        names = {r["name"] for r in results}
        assert "user_behavior.session_count_30d" not in names

    def test_no_match_returns_empty(self, db_with_features: LocalBackend) -> None:
        assert db_with_features.full_text_search("xyzqqq") == []

    def test_empty_query_returns_empty(self, db_with_features: LocalBackend) -> None:
        assert db_with_features.full_text_search("   ") == []

    def test_limit_caps_results(self, db_with_features: LocalBackend) -> None:
        assert len(db_with_features.full_text_search("count", limit=1)) == 1


# --------------------------------------------------------------------------- #
# FTS5-specific behaviour (Fix 3 / P2.1)                                       #
# --------------------------------------------------------------------------- #


class TestFts5Behaviour:
    def test_underscore_tokenizes(self, db_with_features: LocalBackend) -> None:
        """`cpu_usage` → tokens [cpu, usage]: matches features with either."""
        results = db_with_features.full_text_search("session_count")
        names = [r["name"] for r in results]
        assert "user_behavior.session_count_30d" in names

    def test_diacritic_insensitive(self, tmp_path: Path) -> None:
        """unicode61 with remove_diacritics=2: 'luot' matches 'lượt'."""
        db = LocalBackend(str(tmp_path / "dia.db"))
        db.init_db()
        src = db.add_source(DataSource(name="vn", path="/v.parquet"))
        db.upsert_feature(
            Feature(
                name="vn.luot_truy_cap",
                data_source_id=src.id,
                column_name="luot_truy_cap",
                dtype="int64",
                description="lượt truy cập của user trong tháng",
                tags=["vietnamese"],
            )
        )
        # Search without diacritics still matches the description with them.
        hits = db.full_text_search("luot truy cap")
        assert any(h["name"] == "vn.luot_truy_cap" for h in hits)

    def test_malformed_query_falls_back_cleanly(self, db_with_features: LocalBackend) -> None:
        """Crafted FTS5 syntax errors must not raise — fall back to keyword path."""
        # Unbalanced quote is invalid FTS5 syntax; expect graceful fallback.
        results = db_with_features.full_text_search('session"unclosed')
        # No raise. Either FTS5 tokenized the parts, or the legacy path did.
        # Either way we should still find session-related features.
        assert any("session" in r["name"] for r in results)

    def test_trigger_picks_up_new_features(self, db_with_features: LocalBackend) -> None:
        """Insert post-init must be picked up by the FTS5 trigger."""
        new_src = db_with_features.add_source(DataSource(name="late", path="/l.parquet"))
        db_with_features.upsert_feature(
            Feature(
                name="late.new_arrival",
                data_source_id=new_src.id,
                column_name="new_arrival",
                dtype="int64",
                description="recently inserted to verify FTS trigger",
                tags=["fresh"],
            )
        )
        hits = db_with_features.full_text_search("arrival")
        assert any(h["name"] == "late.new_arrival" for h in hits)

    def test_trigger_drops_deleted_features(self, db_with_features: LocalBackend) -> None:
        """Delete must remove rows from features_fts via AFTER DELETE trigger."""
        feature = db_with_features.get_feature_by_name("weather.temperature")
        assert feature is not None
        with db_with_features.session() as s:
            s.execute(text("DELETE FROM features WHERE id = :id"), {"id": feature.id})
            s.commit()
        hits = db_with_features.full_text_search("temperature")
        assert all(h["name"] != "weather.temperature" for h in hits)


class TestSearchFeaturesDelegation:
    """search_features now delegates to full_text_search — verify it returns
    Feature objects in rank order (Fix 3)."""

    def test_returns_feature_objects_in_rank_order(self, db_with_features: LocalBackend) -> None:
        results = db_with_features.search_features("session")
        assert results, "expected at least one hit"
        assert results[0].name == "user_behavior.session_count_30d"
        # All hits are Feature instances with hydrated tags list.
        assert all(isinstance(f.tags, list) for f in results)

    def test_search_by_tag(self, db_with_features: LocalBackend) -> None:
        """Tags are tokenized as part of the FTS5 index — tag search still works."""
        results = db_with_features.search_features("churn")
        names = [f.name for f in results]
        assert "user_behavior.session_count_30d" in names

    def test_empty_query_returns_empty(self, db_with_features: LocalBackend) -> None:
        assert db_with_features.search_features("") == []
        assert db_with_features.search_features("   ") == []


class TestSearchFacets:
    def test_no_query_returns_full_facets(self, db_with_features: LocalBackend) -> None:
        facets = db_with_features.search_facets()
        src_names = {s["name"] for s in facets["sources"]}
        assert src_names == {"user_behavior", "weather"}
        dtype_names = {d["name"] for d in facets["dtypes"]}
        assert dtype_names == {"int64", "float64"}
        # All-features view: 1 has doc, 2 don't.
        assert facets["has_doc"]["true"] == 1
        assert facets["has_doc"]["false"] == 2

    def test_query_narrows_facets(self, db_with_features: LocalBackend) -> None:
        facets = db_with_features.search_facets("session")
        # Only session feature matches → only its source / dtype / tag count.
        assert {s["name"] for s in facets["sources"]} == {"user_behavior"}
        assert {d["name"] for d in facets["dtypes"]} == {"int64"}
        tag_names = {t["name"] for t in facets["tags"]}
        assert "churn" in tag_names

    def test_filter_combines_with_facet_count(self, db_with_features: LocalBackend) -> None:
        # filter source=user_behavior → sources facet still shows only user_behavior
        # but with the count for that filtered set.
        facets = db_with_features.search_facets(source="user_behavior")
        assert {s["name"] for s in facets["sources"]} == {"user_behavior"}
        sb = facets["sources"][0]
        assert sb["count"] == 2  # 2 user_behavior features


# --------------------------------------------------------------------------- #
# API                                                                         #
# --------------------------------------------------------------------------- #


class TestSearchEndpoint:
    def test_search_endpoint_shape(self, db_with_features: LocalBackend) -> None:
        resp = _client(db_with_features).get("/api/search", params={"q": "session"})
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert all(set(r.keys()) >= {"id", "name", "dtype", "source", "rank"} for r in body)

    def test_search_requires_q(self, db_with_features: LocalBackend) -> None:
        resp = _client(db_with_features).get("/api/search")
        assert resp.status_code == 422  # missing required q

    def test_search_q_min_length(self, db_with_features: LocalBackend) -> None:
        resp = _client(db_with_features).get("/api/search", params={"q": ""})
        assert resp.status_code == 422

    def test_facets_endpoint_shape(self, db_with_features: LocalBackend) -> None:
        resp = _client(db_with_features).get("/api/search/facets")
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) == {"sources", "tags", "dtypes", "has_doc"}
