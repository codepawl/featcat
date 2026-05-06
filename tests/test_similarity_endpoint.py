"""Tests for T1.2b — find_similar_features + /api/features/by-name/similar.

Pgvector path needs a live postgres + populated embeddings — exercised in the
integration-test runs the operator triggers (out of scope for unit tests).
The TF-IDF fallback runs against a fresh sqlite catalog and is what these
tests cover.
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
def db_with_similar(tmp_path: Path) -> LocalBackend:
    """Catalog with three thematically-related features and one outlier."""
    db = LocalBackend(str(tmp_path / "sim.db"))
    db.init_db()
    src = db.add_source(DataSource(name="src", path="/x.parquet"))
    db.upsert_feature(
        Feature(
            name="src.user_session_count",
            data_source_id=src.id,
            column_name="user_session_count",
            dtype="int64",
            tags=["user", "session", "engagement"],
            description="count of user sessions in the last 30 days",
        )
    )
    db.upsert_feature(
        Feature(
            name="src.user_session_duration",
            data_source_id=src.id,
            column_name="user_session_duration",
            dtype="float64",
            tags=["user", "session", "engagement"],
            description="average duration of user sessions in seconds",
        )
    )
    db.upsert_feature(
        Feature(
            name="src.user_event_count",
            data_source_id=src.id,
            column_name="user_event_count",
            dtype="int64",
            tags=["user", "engagement"],
            description="count of user events in the last 30 days",
        )
    )
    db.upsert_feature(
        Feature(
            name="src.weather_temperature",
            data_source_id=src.id,
            column_name="weather_temperature",
            dtype="float64",
            tags=["weather", "external"],
            description="ambient temperature in celsius",
        )
    )
    return db


class TestFindSimilarTFIDFFallback:
    def test_returns_thematic_neighbors_first(self, db_with_similar: LocalBackend) -> None:
        """user_session_count should rank user_session_duration / user_event_count
        above weather_temperature."""
        ref = db_with_similar.get_feature_by_name("src.user_session_count")
        assert ref is not None
        results = db_with_similar.find_similar_features(ref.id, top_k=3)
        names = [r["name"] for r in results]
        assert names[0] in {"src.user_session_duration", "src.user_event_count"}
        assert "src.weather_temperature" not in names[:2]  # outlier not in top-2

    def test_excludes_self(self, db_with_similar: LocalBackend) -> None:
        ref = db_with_similar.get_feature_by_name("src.user_session_count")
        assert ref is not None
        results = db_with_similar.find_similar_features(ref.id, top_k=10)
        assert all(r["id"] != ref.id for r in results)

    def test_top_k_caps_results(self, db_with_similar: LocalBackend) -> None:
        ref = db_with_similar.get_feature_by_name("src.user_session_count")
        assert ref is not None
        assert len(db_with_similar.find_similar_features(ref.id, top_k=2)) <= 2

    def test_similarity_is_in_range(self, db_with_similar: LocalBackend) -> None:
        ref = db_with_similar.get_feature_by_name("src.user_session_count")
        assert ref is not None
        results = db_with_similar.find_similar_features(ref.id, top_k=10)
        for r in results:
            assert 0.0 < r["similarity"] <= 1.0

    def test_unknown_feature_returns_empty(self, db_with_similar: LocalBackend) -> None:
        assert db_with_similar.find_similar_features("does-not-exist") == []

    def test_empty_catalog_returns_empty(self, tmp_path: Path) -> None:
        db = LocalBackend(str(tmp_path / "empty.db"))
        db.init_db()
        # Even when ref doesn't exist, the early-return short-circuits cleanly.
        assert db.find_similar_features("anything") == []


class TestSimilarEndpoint:
    def _client(self, db: LocalBackend) -> TestClient:
        from featcat.server import create_app
        from featcat.server.deps import get_db

        app = create_app()
        app.dependency_overrides[get_db] = lambda: db
        return TestClient(app)

    def test_endpoint_returns_ranked_neighbors(self, db_with_similar: LocalBackend) -> None:
        resp = self._client(db_with_similar).get(
            "/api/features/by-name/similar",
            params={"name": "src.user_session_count", "top_k": 3},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert all(set(r.keys()) >= {"id", "name", "dtype", "similarity"} for r in body)
        assert len(body) <= 3

    def test_endpoint_404_for_unknown(self, db_with_similar: LocalBackend) -> None:
        resp = self._client(db_with_similar).get(
            "/api/features/by-name/similar",
            params={"name": "src.nope"},
        )
        assert resp.status_code == 404

    def test_endpoint_top_k_clamped(self, db_with_similar: LocalBackend) -> None:
        # top_k=51 exceeds the upper bound of Query(le=50)
        resp = self._client(db_with_similar).get(
            "/api/features/by-name/similar",
            params={"name": "src.user_session_count", "top_k": 51},
        )
        assert resp.status_code == 422  # validation error
