"""Tests for T2.2a — full-text search backend + endpoint.

The postgres tsvector path is exercised in operator-side integration runs
(needs a live postgres + the migration applied). These unit tests run
against the sqlite fallback path which uses in-process token scanning.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

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
