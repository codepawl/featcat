"""Tests for ``find_duplicate_pairs`` + ``GET /api/features/duplicates``.

Covers the new duplicate-detection endpoint introduced in the Similarity
refactor: TF-IDF-based pair detection, reason codes, multi-source filtering,
scale cap, threshold validation, and cache behavior.
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
def empty_db(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "empty.db"))
    db.init_db()
    return db


@pytest.fixture
def db_with_duplicates(tmp_path: Path) -> LocalBackend:
    """Catalog with a near-duplicate pair within one source plus an outlier."""
    db = LocalBackend(str(tmp_path / "dups.db"))
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


@pytest.fixture
def db_cross_source(tmp_path: Path) -> LocalBackend:
    """Two near-identical features in different sources, plus a third source."""
    db = LocalBackend(str(tmp_path / "cross.db"))
    db.init_db()
    billing = db.add_source(DataSource(name="billing", path="/b.parquet"))
    network = db.add_source(DataSource(name="network", path="/n.parquet"))
    device = db.add_source(DataSource(name="device", path="/d.parquet"))
    db.upsert_feature(
        Feature(
            name="billing.user_session_count",
            data_source_id=billing.id,
            column_name="user_session_count",
            dtype="int64",
            tags=["user", "session"],
            description="count of user sessions",
        )
    )
    db.upsert_feature(
        Feature(
            name="network.user_session_count",
            data_source_id=network.id,
            column_name="user_session_count",
            dtype="int64",
            tags=["user", "session"],
            description="count of user sessions per device",
        )
    )
    db.upsert_feature(
        Feature(
            name="device.cpu_usage",
            data_source_id=device.id,
            column_name="cpu_usage",
            dtype="float64",
            tags=["device"],
            description="cpu utilization percent",
        )
    )
    return db


def _client(db: LocalBackend) -> TestClient:
    from featcat.server import create_app
    from featcat.server.deps import get_db

    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


# ---------------------------------------------------------------------------
# Backend method tests
# ---------------------------------------------------------------------------


class TestFindDuplicatePairs:
    def test_returns_empty_on_empty_catalog(self, empty_db: LocalBackend) -> None:
        pairs, total, summary = empty_db.find_duplicate_pairs(threshold=0.5, limit=100)
        assert pairs == []
        assert total == 0
        assert summary is None

    def test_returns_empty_on_single_feature(self, tmp_path: Path) -> None:
        db = LocalBackend(str(tmp_path / "one.db"))
        db.init_db()
        src = db.add_source(DataSource(name="src", path="/x.parquet"))
        db.upsert_feature(Feature(name="src.x", data_source_id=src.id, column_name="x", dtype="int64"))
        pairs, total, _ = db.find_duplicate_pairs(threshold=0.5, limit=100)
        assert pairs == []
        assert total == 0

    def test_finds_obvious_pair_above_threshold(self, db_with_duplicates: LocalBackend) -> None:
        pairs, total, _ = db_with_duplicates.find_duplicate_pairs(threshold=0.3, limit=100)
        assert total >= 1
        names = {(p["a"]["name"], p["b"]["name"]) for p in pairs}
        # Whichever order they land in, the user_total_amount / user_amount_total
        # pair must surface.
        target = frozenset({"billing.user_total_amount", "billing.user_amount_total"})
        assert any(frozenset(pair) == target for pair in names)

    def test_threshold_filters_low_scores(self, db_with_duplicates: LocalBackend) -> None:
        high, _, _ = db_with_duplicates.find_duplicate_pairs(threshold=0.95, limit=100)
        low, _, _ = db_with_duplicates.find_duplicate_pairs(threshold=0.3, limit=100)
        assert len(high) <= len(low)

    def test_pair_deduplicated_a_b_b_a(self, db_with_duplicates: LocalBackend) -> None:
        pairs, _, _ = db_with_duplicates.find_duplicate_pairs(threshold=0.3, limit=100)
        seen = set()
        for p in pairs:
            key = frozenset({p["a"]["name"], p["b"]["name"]})
            assert key not in seen, f"pair {key} appears twice"
            seen.add(key)

    def test_no_filter_returns_cross_source_pairs(self, db_cross_source: LocalBackend) -> None:
        pairs, _, _ = db_cross_source.find_duplicate_pairs(threshold=0.3, limit=100)
        cross = [p for p in pairs if p["a"]["source"] != p["b"]["source"]]
        assert cross, "expected at least one cross-source pair without a source filter"
        names = {(p["a"]["name"], p["b"]["name"]) for p in cross}
        target = frozenset({"billing.user_session_count", "network.user_session_count"})
        assert any(frozenset(pair) == target for pair in names)

    def test_multi_source_filter_scopes_to_set(self, db_cross_source: LocalBackend) -> None:
        pairs, _, _ = db_cross_source.find_duplicate_pairs(threshold=0.1, limit=100, sources=["billing", "network"])
        for p in pairs:
            assert p["a"]["source"] in {"billing", "network"}
            assert p["b"]["source"] in {"billing", "network"}

    def test_single_source_filter_excludes_cross_source(self, db_cross_source: LocalBackend) -> None:
        pairs, _, _ = db_cross_source.find_duplicate_pairs(threshold=0.1, limit=100, sources=["billing"])
        for p in pairs:
            assert p["a"]["source"] == "billing"
            assert p["b"]["source"] == "billing"

    def test_reason_codes_attached_for_schema_match(self, db_with_duplicates: LocalBackend) -> None:
        pairs, _, _ = db_with_duplicates.find_duplicate_pairs(threshold=0.3, limit=100)
        # The user_total_amount / user_amount_total pair are both float64
        target = next(
            (
                p
                for p in pairs
                if frozenset({p["a"]["name"], p["b"]["name"]})
                == frozenset({"billing.user_total_amount", "billing.user_amount_total"})
            ),
            None,
        )
        assert target is not None
        codes = {r["code"] for r in target["reasons"]}
        assert "schema_match" in codes
        assert "semantic_match" in codes

    def test_reason_codes_attached_for_distribution_match(self, db_with_duplicates: LocalBackend) -> None:
        pairs, _, _ = db_with_duplicates.find_duplicate_pairs(threshold=0.3, limit=100)
        target = next(
            (
                p
                for p in pairs
                if frozenset({p["a"]["name"], p["b"]["name"]})
                == frozenset({"billing.user_total_amount", "billing.user_amount_total"})
            ),
            None,
        )
        assert target is not None
        codes = {r["code"] for r in target["reasons"]}
        # mean/std are within 5% / 5% → well under the 10% tolerance.
        assert "distribution_match" in codes

    def test_distribution_match_skipped_for_categorical(self, tmp_path: Path) -> None:
        db = LocalBackend(str(tmp_path / "cat.db"))
        db.init_db()
        src = db.add_source(DataSource(name="src", path="/x.parquet"))
        db.upsert_feature(
            Feature(
                name="src.user_city",
                data_source_id=src.id,
                column_name="user_city",
                dtype="string",
                tags=["user", "geo"],
                description="user city of residence",
                stats={"null_ratio": 0.01, "unique_count": 42},
            )
        )
        db.upsert_feature(
            Feature(
                name="src.user_city_name",
                data_source_id=src.id,
                column_name="user_city_name",
                dtype="string",
                tags=["user", "geo"],
                description="user city of residence (full name)",
                stats={"null_ratio": 0.01, "unique_count": 42},
            )
        )
        pairs, _, _ = db.find_duplicate_pairs(threshold=0.1, limit=10)
        if pairs:
            codes = {r["code"] for r in pairs[0]["reasons"]}
            assert "distribution_match" not in codes  # no mean/std → never emitted

    def test_sort_is_stable_score_desc_then_reason_count_desc(self, db_with_duplicates: LocalBackend) -> None:
        pairs, _, _ = db_with_duplicates.find_duplicate_pairs(threshold=0.0, limit=100)
        for prev, nxt in zip(pairs, pairs[1:], strict=False):
            if prev["score"] == nxt["score"]:
                assert len(prev["reasons"]) >= len(nxt["reasons"])
            else:
                assert prev["score"] > nxt["score"]


# ---------------------------------------------------------------------------
# Route-level tests
# ---------------------------------------------------------------------------


class TestDuplicatesEndpoint:
    def test_returns_response_shape(self, db_with_duplicates: LocalBackend) -> None:
        resp = _client(db_with_duplicates).get("/api/features/duplicates", params={"threshold": 0.4})
        assert resp.status_code == 200
        body = resp.json()
        assert set(body.keys()) >= {"threshold", "pairs", "total", "cached_at", "summary"}
        for p in body["pairs"]:
            assert set(p.keys()) >= {"a", "b", "score", "reasons"}
            assert set(p["a"].keys()) >= {"id", "name", "dtype", "source", "has_doc"}

    def test_threshold_validation_below_min_returns_422(self, db_with_duplicates: LocalBackend) -> None:
        resp = _client(db_with_duplicates).get("/api/features/duplicates", params={"threshold": 0.39})
        assert resp.status_code == 422

    def test_threshold_validation_above_max_returns_422(self, db_with_duplicates: LocalBackend) -> None:
        resp = _client(db_with_duplicates).get("/api/features/duplicates", params={"threshold": 0.96})
        assert resp.status_code == 422

    def test_cache_hit_returns_same_payload_with_cached_at_set(self, db_with_duplicates: LocalBackend) -> None:
        from featcat.server.cache import invalidate

        invalidate("duplicates:")
        client = _client(db_with_duplicates)
        first = client.get("/api/features/duplicates", params={"threshold": 0.5}).json()
        second = client.get("/api/features/duplicates", params={"threshold": 0.5}).json()
        assert first["pairs"] == second["pairs"]
        # First call computes fresh → cached_at None; second call is the cache
        # hit → cached_at populated with an ISO timestamp.
        assert first["cached_at"] is None
        assert second["cached_at"] is not None

    def test_returns_empty_with_summary_when_catalog_exceeds_cap(self, tmp_path: Path) -> None:
        """Stub-style: directly verify the cap path returns the expected
        ``summary`` without needing 2001 features.

        We monkey-patch the class constant down to 2 so a 3-feature catalog
        trips the cap.
        """
        db = LocalBackend(str(tmp_path / "cap.db"))
        db.init_db()
        src = db.add_source(DataSource(name="src", path="/x.parquet"))
        for i in range(3):
            db.upsert_feature(
                Feature(
                    name=f"src.f{i}",
                    data_source_id=src.id,
                    column_name=f"f{i}",
                    dtype="int64",
                    description=f"feature number {i}",
                )
            )
        original = LocalBackend.DUPLICATES_MAX_FEATURES
        try:
            LocalBackend.DUPLICATES_MAX_FEATURES = 2  # type: ignore[misc]
            pairs, total, summary = db.find_duplicate_pairs(threshold=0.0, limit=10)
        finally:
            LocalBackend.DUPLICATES_MAX_FEATURES = original  # type: ignore[misc]
        assert pairs == []
        assert total == 0
        assert summary is not None
        assert "too large" in summary.lower()
