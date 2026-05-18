"""Tests for the three new monitoring chart endpoints.

Covers:
- ``MonitoringCheck`` schema migration (new columns + indexes are idempotent)
- ``save_monitoring_result`` persists the auxiliary metrics
- ``get_feature_metric_history`` (route ``GET /api/monitor/metrics/{spec}``)
- ``get_group_drift_matrix`` (route ``GET /api/groups/{name}/drift-matrix``)
- ``get_catalog_drift_trend`` (route ``GET /api/monitor/drift-rate``)
- Cache invalidation on /monitor/check writes
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature, FeatureGroup

if TYPE_CHECKING:
    from pathlib import Path


def _utc(year: int, month: int, day: int, hour: int = 12) -> datetime:
    return datetime(year, month, day, hour, tzinfo=timezone.utc)


@pytest.fixture
def db(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "monitoring.db"))
    db.init_db()
    return db


@pytest.fixture
def db_with_features(db: LocalBackend) -> LocalBackend:
    src = db.add_source(DataSource(name="src", path="/data/src.parquet"))
    db.upsert_feature(Feature(name="src.alpha", data_source_id=src.id, column_name="alpha", dtype="float64"))
    db.upsert_feature(Feature(name="src.beta", data_source_id=src.id, column_name="beta", dtype="float64"))
    db.upsert_feature(Feature(name="src.gamma", data_source_id=src.id, column_name="gamma", dtype="int64"))
    return db


def _client(db: LocalBackend) -> TestClient:
    from featcat.server import create_app
    from featcat.server.cache import invalidate
    from featcat.server.deps import get_db, get_llm

    invalidate("")  # don't let prior tests leak cached responses
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm] = lambda: None
    return TestClient(app)


# ---------------------------------------------------------------------------
# Schema migration
# ---------------------------------------------------------------------------


class TestSchemaMigration:
    def test_new_columns_present_on_fresh_db(self, db: LocalBackend) -> None:
        with db.session() as s:
            cols = {row[1] for row in s.execute(text("PRAGMA table_info(monitoring_checks)")).all()}
        assert {"null_ratio", "mean_z_score", "sample_size"}.issubset(cols)

    def test_init_db_idempotent(self, db: LocalBackend) -> None:
        # Running init_db twice on an already-initialized DB must not raise.
        db.init_db()
        db.init_db()
        with db.session() as s:
            cols = {row[1] for row in s.execute(text("PRAGMA table_info(monitoring_checks)")).all()}
        assert {"null_ratio", "mean_z_score", "sample_size"}.issubset(cols)

    def test_legacy_db_gets_columns_added(self, tmp_path: Path) -> None:
        """Simulate a pre-migration DB and verify the ALTER TABLEs land cleanly."""
        path = str(tmp_path / "legacy.db")
        # Create a sqlite file with a stripped-down monitoring_checks table.
        conn = sqlite3.connect(path)
        conn.execute(
            "CREATE TABLE monitoring_checks (id TEXT PRIMARY KEY, feature_id TEXT, "
            "feature_name TEXT, psi REAL, severity TEXT, checked_at TIMESTAMP)"
        )
        conn.execute("CREATE TABLE features (id TEXT PRIMARY KEY)")  # FK target
        conn.commit()
        conn.close()

        # Now open via LocalBackend — init_db should add the new columns + indexes.
        legacy = LocalBackend(path)
        legacy.init_db()
        with legacy.session() as s:
            cols = {row[1] for row in s.execute(text("PRAGMA table_info(monitoring_checks)")).all()}
            indexes = {row[1] for row in s.execute(text("PRAGMA index_list(monitoring_checks)")).all()}
        assert {"null_ratio", "mean_z_score", "sample_size"}.issubset(cols)
        assert "idx_monitoring_checks_feature_date" in indexes
        assert "idx_monitoring_checks_date_severity" in indexes


# ---------------------------------------------------------------------------
# save_monitoring_result + get_feature_metric_history
# ---------------------------------------------------------------------------


class TestMetricHistory:
    def test_save_persists_new_metrics(self, db_with_features: LocalBackend) -> None:
        feat = db_with_features.get_feature_by_name("src.alpha")
        assert feat is not None
        db_with_features.save_monitoring_result(
            feat.id,
            feat.name,
            psi=0.05,
            severity="healthy",
            null_ratio=0.02,
            mean_z_score=0.5,
            sample_size=10000,
        )
        rows = db_with_features.get_feature_metric_history("src.alpha", days=7)
        assert len(rows) == 1
        assert rows[0]["psi"] == 0.05
        assert rows[0]["null_ratio"] == 0.02
        assert rows[0]["mean_z_score"] == 0.5
        assert rows[0]["sample_size"] == 10000

    def test_legacy_row_returns_null_for_new_metrics(self, db_with_features: LocalBackend) -> None:
        feat = db_with_features.get_feature_by_name("src.alpha")
        assert feat is not None
        db_with_features.save_monitoring_result(feat.id, feat.name, psi=0.08, severity="healthy")
        rows = db_with_features.get_feature_metric_history("src.alpha", days=7)
        assert rows[0]["null_ratio"] is None
        assert rows[0]["mean_z_score"] is None
        assert rows[0]["sample_size"] is None

    def test_route_returns_metric_series(self, db_with_features: LocalBackend) -> None:
        feat = db_with_features.get_feature_by_name("src.alpha")
        assert feat is not None
        db_with_features.save_monitoring_result(
            feat.id, feat.name, 0.12, "warning", null_ratio=0.04, mean_z_score=1.5, sample_size=5000
        )
        resp = _client(db_with_features).get("/api/monitor/metrics/src.alpha?days=30")
        assert resp.status_code == 200
        body = resp.json()
        assert isinstance(body, list)
        assert body[0]["severity"] == "warning"
        assert body[0]["psi"] == 0.12
        assert body[0]["null_ratio"] == 0.04
        assert body[0]["sample_size"] == 5000


# ---------------------------------------------------------------------------
# get_group_drift_matrix
# ---------------------------------------------------------------------------


def _seed_check(db: LocalBackend, feature_name: str, when: datetime, severity: str, psi: float | None = None) -> None:
    """Insert a monitoring_check at an arbitrary timestamp (bypasses _utcnow)."""
    feat = db.get_feature_by_name(feature_name)
    assert feat is not None
    with db.session() as s:
        s.execute(
            text(
                "INSERT INTO monitoring_checks (id, feature_id, feature_name, psi, severity, checked_at) "
                "VALUES (:id, :fid, :name, :psi, :sev, :ts)"
            ),
            {
                "id": f"chk-{feature_name}-{when.isoformat()}",
                "fid": feat.id,
                "name": feat.name,
                "psi": psi,
                "sev": severity,
                "ts": when,
            },
        )
        s.commit()


class TestGroupDriftMatrix:
    def test_empty_group_returns_empty_features(self, db_with_features: LocalBackend) -> None:
        group = db_with_features.create_group(FeatureGroup(name="empty"))
        matrix = db_with_features.get_group_drift_matrix(group.id, days=30)
        assert matrix["features"] == []
        assert matrix["truncated"] is False
        assert matrix["total_count"] == 0
        assert len(matrix["date_range"]) == 30

    def test_worst_severity_per_day_wins(self, db_with_features: LocalBackend) -> None:
        group = db_with_features.create_group(FeatureGroup(name="g"))
        feats = [db_with_features.get_feature_by_name(n) for n in ("src.alpha",)]
        db_with_features.add_group_members(group.id, [f.id for f in feats if f])

        today = datetime.now(timezone.utc).date()
        midday = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc) + timedelta(hours=10)
        evening = midday + timedelta(hours=6)
        # Two checks today: warning, then critical → critical must win.
        _seed_check(db_with_features, "src.alpha", midday, "warning", psi=0.15)
        _seed_check(db_with_features, "src.alpha", evening, "critical", psi=0.30)

        matrix = db_with_features.get_group_drift_matrix(group.id, days=7)
        alpha = matrix["features"][0]
        today_iso = today.isoformat()
        cell = next(c for c in alpha["daily"] if c["date"] == today_iso)
        assert cell["severity"] == "critical"
        assert cell["psi"] == 0.30

    def test_features_sorted_by_severity_then_name(self, db_with_features: LocalBackend) -> None:
        group = db_with_features.create_group(FeatureGroup(name="g"))
        all_feats = [db_with_features.get_feature_by_name(n) for n in ("src.alpha", "src.beta", "src.gamma")]
        db_with_features.add_group_members(group.id, [f.id for f in all_feats if f])

        now = datetime.now(timezone.utc) - timedelta(hours=1)
        _seed_check(db_with_features, "src.alpha", now, "healthy", psi=0.02)
        _seed_check(db_with_features, "src.beta", now, "critical", psi=0.40)
        _seed_check(db_with_features, "src.gamma", now, "warning", psi=0.15)

        matrix = db_with_features.get_group_drift_matrix(group.id, days=7)
        names = [f["name"] for f in matrix["features"]]
        # critical < warning < healthy by priority; ties broken alphabetically.
        assert names == ["src.beta", "src.gamma", "src.alpha"]

    @pytest.mark.timeout(30)
    def test_truncates_at_200_features(self, db: LocalBackend) -> None:
        src = db.add_source(DataSource(name="big", path="/big.parquet"))
        for i in range(220):
            db.upsert_feature(
                Feature(name=f"big.f{i:04d}", data_source_id=src.id, column_name=f"f{i:04d}", dtype="float64")
            )
        group = db.create_group(FeatureGroup(name="big"))
        feats = [db.get_feature_by_name(f"big.f{i:04d}") for i in range(220)]
        db.add_group_members(group.id, [f.id for f in feats if f])

        matrix = db.get_group_drift_matrix(group.id, days=30)
        assert matrix["truncated"] is True
        assert matrix["total_count"] == 220
        assert len(matrix["features"]) == 200

    def test_route_404_for_unknown_group(self, db_with_features: LocalBackend) -> None:
        resp = _client(db_with_features).get("/api/groups/does-not-exist/drift-matrix")
        assert resp.status_code == 404

    def test_route_returns_matrix(self, db_with_features: LocalBackend) -> None:
        group = db_with_features.create_group(FeatureGroup(name="g"))
        feats = [db_with_features.get_feature_by_name(n) for n in ("src.alpha", "src.beta")]
        db_with_features.add_group_members(group.id, [f.id for f in feats if f])
        _seed_check(db_with_features, "src.alpha", datetime.now(timezone.utc) - timedelta(hours=1), "healthy", 0.01)

        resp = _client(db_with_features).get("/api/groups/g/drift-matrix?days=14")
        assert resp.status_code == 200
        body = resp.json()
        assert len(body["date_range"]) == 14
        assert len(body["features"]) == 2
        assert body["truncated"] is False
        assert body["total_count"] == 2


# ---------------------------------------------------------------------------
# get_catalog_drift_trend
# ---------------------------------------------------------------------------


class TestCatalogDriftTrend:
    def test_no_checks_yields_zero_percentages(self, db_with_features: LocalBackend) -> None:
        series = db_with_features.get_catalog_drift_trend(days=7)
        assert len(series) == 7
        assert all(p["critical_pct"] == 0.0 for p in series)
        assert all(p["warning_pct"] == 0.0 for p in series)
        assert all(p["total_features"] == 0 for p in series)

    def test_per_day_percentages(self, db_with_features: LocalBackend) -> None:
        # Yesterday: alpha critical, beta warning, gamma healthy → 33% critical, 33% warning, total=3.
        yesterday = datetime.now(timezone.utc) - timedelta(days=1)
        _seed_check(db_with_features, "src.alpha", yesterday, "critical", 0.40)
        _seed_check(db_with_features, "src.beta", yesterday, "warning", 0.15)
        _seed_check(db_with_features, "src.gamma", yesterday, "healthy", 0.02)

        series = db_with_features.get_catalog_drift_trend(days=3)
        # The 'yesterday' day in the window — find by date.
        target_date = yesterday.date().isoformat()
        point = next(p for p in series if p["date"] == target_date)
        assert point["total_features"] == 3
        assert point["critical_pct"] == round(100 / 3, 2)
        assert point["warning_pct"] == round(100 / 3, 2)

    def test_latest_check_on_or_before_day_wins(self, db_with_features: LocalBackend) -> None:
        # Day -3: alpha goes critical. Day -2: alpha recovers to healthy.
        # On day -3, alpha is critical (1/1). On day -1, alpha is healthy (0/1).
        now = datetime.now(timezone.utc)
        _seed_check(db_with_features, "src.alpha", now - timedelta(days=3), "critical", 0.40)
        _seed_check(db_with_features, "src.alpha", now - timedelta(days=2), "healthy", 0.02)

        series = db_with_features.get_catalog_drift_trend(days=5)
        date_to_point = {p["date"]: p for p in series}
        d_minus_3 = (now.date() - timedelta(days=3)).isoformat()
        d_minus_1 = (now.date() - timedelta(days=1)).isoformat()
        # Day -3: only the critical check is on-or-before, so 100% critical of 1 feature.
        assert date_to_point[d_minus_3]["critical_pct"] == 100.0
        assert date_to_point[d_minus_3]["total_features"] == 1
        # Day -1: the healthy check supersedes the critical one, so 0% critical.
        assert date_to_point[d_minus_1]["critical_pct"] == 0.0
        assert date_to_point[d_minus_1]["total_features"] == 1

    def test_route_returns_envelope(self, db_with_features: LocalBackend) -> None:
        _seed_check(
            db_with_features,
            "src.alpha",
            datetime.now(timezone.utc) - timedelta(hours=1),
            "critical",
            0.40,
        )
        resp = _client(db_with_features).get("/api/monitor/drift-rate?days=30")
        assert resp.status_code == 200
        body = resp.json()
        assert "date_range" in body
        assert "series" in body
        assert len(body["series"]) == 30


# ---------------------------------------------------------------------------
# Cache integration
# ---------------------------------------------------------------------------


class TestCaching:
    def test_drift_rate_caches(self, db_with_features: LocalBackend) -> None:
        from featcat.server.cache import cache_get

        client = _client(db_with_features)
        _seed_check(
            db_with_features,
            "src.alpha",
            datetime.now(timezone.utc) - timedelta(hours=1),
            "critical",
            0.40,
        )

        # First call populates cache.
        first = client.get("/api/monitor/drift-rate?days=30")
        assert first.status_code == 200
        assert cache_get("monitor:drift_rate:30") is not None

        # Second call returns the cached value (same JSON shape).
        second = client.get("/api/monitor/drift-rate?days=30")
        assert second.json() == first.json()

    def test_check_endpoint_invalidates_chart_caches(self, db_with_features: LocalBackend) -> None:
        from featcat.server.cache import cache_get

        client = _client(db_with_features)
        _seed_check(
            db_with_features,
            "src.alpha",
            datetime.now(timezone.utc) - timedelta(hours=1),
            "critical",
            0.40,
        )
        client.get("/api/monitor/drift-rate?days=30")
        assert cache_get("monitor:drift_rate:30") is not None

        # /monitor/check writes new monitoring_checks rows; cache must drop.
        client.get("/api/monitor/check")
        assert cache_get("monitor:drift_rate:30") is None


def _make_baselined_feature(db: LocalBackend, name: str, mean: float, std: float) -> Any:
    src = db.add_source(DataSource(name=name + "-src", path=f"/{name}.parquet"))
    feat = db.upsert_feature(
        Feature(
            name=f"{name}-src.{name}",
            data_source_id=src.id,
            column_name=name,
            dtype="float64",
            stats={"mean": mean, "std": std, "null_ratio": 0.01, "total_count": 1000, "min": 0, "max": 100},
        )
    )
    db.save_baseline(feat.id, {"mean": mean, "std": std, "null_ratio": 0.01, "min": 0, "max": 100})
    return feat


# ---------------------------------------------------------------------------
# Plugin integration — confirm new metrics get persisted by the real plugin path
# ---------------------------------------------------------------------------


class TestPluginPersistsMetrics:
    def test_check_persists_auxiliary_metrics(self, db: LocalBackend) -> None:
        from featcat.plugins.monitoring import MonitoringPlugin

        # Baseline mean=10, std=2. Drift the current to mean=14 → Z-score = (14-10)/2 = 2.0.
        feat = _make_baselined_feature(db, "drift", mean=10.0, std=2.0)
        # Re-upsert with drifted current stats.
        db.upsert_feature(
            Feature(
                id=feat.id,
                name=feat.name,
                data_source_id=feat.data_source_id,
                column_name=feat.column_name,
                dtype="float64",
                stats={"mean": 14.0, "std": 2.0, "null_ratio": 0.05, "total_count": 1000, "min": 0, "max": 100},
            )
        )

        plugin = MonitoringPlugin()
        plugin.execute(db, None, action="check")

        rows = db.get_feature_metric_history(feat.name, days=1)
        assert len(rows) == 1
        assert rows[0]["mean_z_score"] == 2.0
        assert rows[0]["null_ratio"] == 0.05
        assert rows[0]["sample_size"] == 1000
