"""Tests for ``compute_similarity_matrix`` / ``compute_pair_reasons`` and the
``GET /api/features/similarity-matrix`` + ``GET /api/features/similarity-pair``
endpoints.

Covers the matrix view added on top of the duplicates+recommend refactor:
caller-ordered upper-triangle scoring, threshold filter, 100-feature cap,
unknown-id handling, and a regression check that the reason-code breakdown
matches what ``find_duplicate_pairs`` produces for the same pair.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature

if TYPE_CHECKING:
    from pathlib import Path


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def db_with_features(tmp_path: Path) -> LocalBackend:
    """Three-feature catalog: two near-duplicates plus an unrelated outlier."""
    db = LocalBackend(str(tmp_path / "matrix.db"))
    db.init_db()
    src = db.add_source(DataSource(name="billing", path="/billing.parquet"))
    db.upsert_feature(
        Feature(
            name="billing.user_total_amount",
            data_source_id=src.id,
            column_name="user_total_amount",
            dtype="float64",
            tags=["billing", "amount"],
            description="total billed amount per user in the last 30 days",
            stats={"mean": 105.0, "std": 20.0, "min": 0.0, "max": 500.0},
        )
    )
    db.upsert_feature(
        Feature(
            name="billing.user_amount_total",
            data_source_id=src.id,
            column_name="user_amount_total",
            dtype="float64",
            tags=["billing", "amount"],
            description="total billed amount per user over the last month",
            stats={"mean": 108.0, "std": 21.0, "min": 0.0, "max": 510.0},
        )
    )
    db.upsert_feature(
        Feature(
            name="billing.weather_temp",
            data_source_id=src.id,
            column_name="weather_temp",
            dtype="float64",
            tags=["weather"],
            description="ambient temperature in celsius",
            stats={"mean": 22.0, "std": 5.0, "min": -5.0, "max": 40.0},
        )
    )
    return db


def _ids(db: LocalBackend) -> list[str]:
    """Stable id ordering by name for deterministic tests."""
    return [f.id for f in sorted(db.list_features(), key=lambda f: f.name)]


def _client(db: LocalBackend) -> TestClient:
    from featcat.server import create_app
    from featcat.server.deps import get_db

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


# ---------------------------------------------------------------------------
# Backend method tests — compute_similarity_matrix
# ---------------------------------------------------------------------------


class TestComputeSimilarityMatrix:
    def test_returns_upper_triangle_only(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features)
        features, cells = db_with_features.compute_similarity_matrix(ids, threshold=0.0)
        assert len(features) == 3
        # 3 features → upper triangle has 3 cells: (0,1), (0,2), (1,2)
        assert len(cells) == 3
        for c in cells:
            assert c["a"] < c["b"]
        assert {(c["a"], c["b"]) for c in cells} == {(0, 1), (0, 2), (1, 2)}

    def test_preserves_caller_order(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features)
        # Reverse the order; features in the response must mirror the request.
        reversed_ids = list(reversed(ids))
        features, _ = db_with_features.compute_similarity_matrix(reversed_ids, threshold=0.0)
        assert [f["id"] for f in features] == reversed_ids

    def test_threshold_filters_low_scores(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features)
        _, all_cells = db_with_features.compute_similarity_matrix(ids, threshold=0.0)
        _, strict_cells = db_with_features.compute_similarity_matrix(ids, threshold=0.99)
        assert len(strict_cells) <= len(all_cells)
        # 0.99 is high enough that no real-world pair survives — the two
        # near-duplicates score < 1.0 because their text differs.
        assert len(strict_cells) == 0

    def test_features_returned_are_brief_shaped(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features)
        features, _ = db_with_features.compute_similarity_matrix(ids, threshold=0.0)
        for f in features:
            assert set(f.keys()) >= {"id", "name", "dtype", "source", "has_doc"}
            assert f["source"] == "billing"

    def test_two_features_returns_one_cell(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features)[:2]
        features, cells = db_with_features.compute_similarity_matrix(ids, threshold=0.0)
        assert len(features) == 2
        assert len(cells) == 1
        assert cells[0]["a"] == 0 and cells[0]["b"] == 1

    def test_single_feature_returns_no_cells(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features)[:1]
        features, cells = db_with_features.compute_similarity_matrix(ids, threshold=0.0)
        assert len(features) == 1
        assert cells == []

    def test_empty_ids_raises(self, db_with_features: LocalBackend) -> None:
        with pytest.raises(ValueError, match="must not be empty"):
            db_with_features.compute_similarity_matrix([], threshold=0.0)

    def test_duplicate_ids_raises(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features)
        with pytest.raises(ValueError, match="unique"):
            db_with_features.compute_similarity_matrix([ids[0], ids[0]], threshold=0.0)

    def test_unknown_id_raises_keyerror(self, db_with_features: LocalBackend) -> None:
        with pytest.raises(KeyError):
            db_with_features.compute_similarity_matrix(["nonexistent-id"], threshold=0.0)

    def test_cap_raises_with_clear_message(self, db_with_features: LocalBackend) -> None:
        original = LocalBackend.SIMILARITY_MATRIX_MAX_FEATURES
        try:
            LocalBackend.SIMILARITY_MATRIX_MAX_FEATURES = 2  # type: ignore[misc]
            ids = _ids(db_with_features)
            with pytest.raises(ValueError, match="exceeds cap"):
                db_with_features.compute_similarity_matrix(ids, threshold=0.0)
        finally:
            LocalBackend.SIMILARITY_MATRIX_MAX_FEATURES = original  # type: ignore[misc]


# ---------------------------------------------------------------------------
# Backend method tests — compute_pair_reasons
# ---------------------------------------------------------------------------


class TestComputePairReasons:
    def test_returns_brief_shapes_score_and_reasons(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features)
        a, b, score, reasons = db_with_features.compute_pair_reasons(ids[0], ids[1])
        assert set(a.keys()) >= {"id", "name", "dtype", "source", "has_doc"}
        assert set(b.keys()) >= {"id", "name", "dtype", "source", "has_doc"}
        assert 0.0 <= score <= 1.0
        assert any(r["code"] == "semantic_match" for r in reasons)

    def test_matches_duplicates_breakdown_for_same_pair(self, db_with_features: LocalBackend) -> None:
        """Regression: the per-pair endpoint must surface the *same* reason
        codes that ``find_duplicate_pairs`` would produce for that pair."""
        ids = _ids(db_with_features)
        # The two near-duplicates: user_amount_total and user_total_amount.
        # _ids sorts by name, so 0=user_amount_total, 1=user_total_amount.
        a_id, b_id = ids[0], ids[1]
        _, _, _, pair_reasons = db_with_features.compute_pair_reasons(a_id, b_id)
        pair_codes = {r["code"] for r in pair_reasons}

        all_pairs, _, _ = db_with_features.find_duplicate_pairs(threshold=0.0, limit=100)
        target_pair = next(p for p in all_pairs if frozenset({p["a"]["id"], p["b"]["id"]}) == frozenset({a_id, b_id}))
        target_codes = {r["code"] for r in target_pair["reasons"]}
        assert pair_codes == target_codes

    def test_self_pair_raises(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features)
        with pytest.raises(ValueError, match="must differ"):
            db_with_features.compute_pair_reasons(ids[0], ids[0])

    def test_unknown_id_raises_keyerror(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features)
        with pytest.raises(KeyError):
            db_with_features.compute_pair_reasons(ids[0], "nonexistent-id")


# ---------------------------------------------------------------------------
# Route-level tests — /similarity-matrix
# ---------------------------------------------------------------------------


class TestSimilarityMatrixEndpoint:
    def test_returns_response_shape(self, db_with_features: LocalBackend) -> None:
        from featcat.server.cache import invalidate

        invalidate("matrix:")
        ids = _ids(db_with_features)
        resp = _client(db_with_features).get(
            "/api/features/similarity-matrix",
            params={"ids": ",".join(ids), "threshold": 0.0},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) >= {"features", "cells", "threshold", "cached_at"}
        assert len(body["features"]) == 3
        assert len(body["cells"]) == 3
        for c in body["cells"]:
            assert set(c.keys()) >= {"a", "b", "score"}
            assert c["a"] < c["b"]

    def test_404_on_unknown_id(self, db_with_features: LocalBackend) -> None:
        from featcat.server.cache import invalidate

        invalidate("matrix:")
        resp = _client(db_with_features).get(
            "/api/features/similarity-matrix",
            params={"ids": "nonexistent", "threshold": 0.0},
        )
        assert resp.status_code == 404
        assert "nonexistent" in resp.json()["detail"]

    def test_400_above_feature_cap(self, db_with_features: LocalBackend) -> None:
        from featcat.server.cache import invalidate

        invalidate("matrix:")
        original = LocalBackend.SIMILARITY_MATRIX_MAX_FEATURES
        try:
            LocalBackend.SIMILARITY_MATRIX_MAX_FEATURES = 2  # type: ignore[misc]
            ids = _ids(db_with_features)
            resp = _client(db_with_features).get(
                "/api/features/similarity-matrix",
                params={"ids": ",".join(ids), "threshold": 0.0},
            )
            assert resp.status_code == 400
            assert "exceeds cap" in resp.json()["detail"]
        finally:
            LocalBackend.SIMILARITY_MATRIX_MAX_FEATURES = original  # type: ignore[misc]

    def test_400_on_empty_ids(self, db_with_features: LocalBackend) -> None:
        from featcat.server.cache import invalidate

        invalidate("matrix:")
        resp = _client(db_with_features).get(
            "/api/features/similarity-matrix",
            params={"ids": "", "threshold": 0.0},
        )
        assert resp.status_code == 400

    def test_400_on_duplicate_ids(self, db_with_features: LocalBackend) -> None:
        from featcat.server.cache import invalidate

        invalidate("matrix:")
        ids = _ids(db_with_features)
        resp = _client(db_with_features).get(
            "/api/features/similarity-matrix",
            params={"ids": f"{ids[0]},{ids[0]}", "threshold": 0.0},
        )
        assert resp.status_code == 400
        assert "unique" in resp.json()["detail"]

    def test_threshold_validation_above_max_returns_422(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features)
        resp = _client(db_with_features).get(
            "/api/features/similarity-matrix",
            params={"ids": ",".join(ids), "threshold": 1.5},
        )
        assert resp.status_code == 422

    def test_empty_cells_when_threshold_above_all_scores(self, db_with_features: LocalBackend) -> None:
        from featcat.server.cache import invalidate

        invalidate("matrix:")
        ids = _ids(db_with_features)
        resp = _client(db_with_features).get(
            "/api/features/similarity-matrix",
            params={"ids": ",".join(ids), "threshold": 0.99},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["features"]) == 3
        assert body["cells"] == []

    def test_cache_hit_populates_cached_at(self, db_with_features: LocalBackend) -> None:
        from featcat.server.cache import invalidate

        invalidate("matrix:")
        client = _client(db_with_features)
        ids = _ids(db_with_features)
        params = {"ids": ",".join(ids), "threshold": 0.0}
        first = client.get("/api/features/similarity-matrix", params=params).json()
        second = client.get("/api/features/similarity-matrix", params=params).json()
        assert first["cells"] == second["cells"]
        assert first["cached_at"] is None
        assert second["cached_at"] is not None


# ---------------------------------------------------------------------------
# Route-level tests — /similarity-pair
# ---------------------------------------------------------------------------


class TestSimilarityPairEndpoint:
    def test_returns_response_shape(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features)
        resp = _client(db_with_features).get(
            "/api/features/similarity-pair",
            params={"a": ids[0], "b": ids[1]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) >= {"a", "b", "score", "reasons"}
        assert set(body["a"].keys()) >= {"id", "name", "dtype", "source", "has_doc"}
        assert any(r["code"] == "semantic_match" for r in body["reasons"])

    def test_404_on_unknown_id(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features)
        resp = _client(db_with_features).get(
            "/api/features/similarity-pair",
            params={"a": ids[0], "b": "nonexistent"},
        )
        assert resp.status_code == 404
        assert "nonexistent" in resp.json()["detail"]

    def test_400_on_self_pair(self, db_with_features: LocalBackend) -> None:
        ids = _ids(db_with_features)
        resp = _client(db_with_features).get(
            "/api/features/similarity-pair",
            params={"a": ids[0], "b": ids[0]},
        )
        assert resp.status_code == 400
        assert "differ" in resp.json()["detail"]
