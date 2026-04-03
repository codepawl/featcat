"""Tests for the Quality Monitoring plugin and statistics utilities."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature
from featcat.plugins.monitoring import MonitoringPlugin, export_monitoring_report
from featcat.utils.statistics import (
    check_null_spike,
    check_range_violation,
    check_zero_variance,
    classify_severity,
    compute_psi,
)

if TYPE_CHECKING:
    from pathlib import Path

# --- Statistics utility tests ---


class TestPSI:
    def test_identical_distributions(self):
        stats = {"mean": 10.0, "std": 2.0}
        psi = compute_psi(stats, stats)
        assert psi is not None
        assert psi < 0.01

    def test_shifted_mean(self):
        baseline = {"mean": 10.0, "std": 2.0}
        current = {"mean": 15.0, "std": 2.0}
        psi = compute_psi(baseline, current)
        assert psi is not None
        assert psi > 0.1

    def test_large_drift(self):
        baseline = {"mean": 10.0, "std": 2.0}
        current = {"mean": 30.0, "std": 5.0}
        psi = compute_psi(baseline, current)
        assert psi is not None
        assert psi > 0.25

    def test_missing_stats(self):
        psi = compute_psi({"mean": 10}, {"mean": 10, "std": 2})
        assert psi is None

    def test_zero_std(self):
        baseline = {"mean": 5.0, "std": 0.0}
        current = {"mean": 5.0, "std": 0.0}
        psi = compute_psi(baseline, current)
        assert psi == 0.0


class TestNullSpike:
    def test_spike_detected(self):
        result = check_null_spike(
            {"null_ratio": 0.01},
            {"null_ratio": 0.10},
            threshold=0.05,
        )
        assert result is not None
        assert result["issue"] == "null_spike"

    def test_no_spike(self):
        result = check_null_spike(
            {"null_ratio": 0.01},
            {"null_ratio": 0.03},
            threshold=0.05,
        )
        assert result is None


class TestRangeViolation:
    def test_violation_detected(self):
        baseline = {"min": 0, "max": 100, "std": 10}
        current = {"min": -50, "max": 100}
        result = check_range_violation(baseline, current)
        assert result is not None
        assert result["issue"] == "range_violation"

    def test_within_range(self):
        baseline = {"min": 0, "max": 100, "std": 10}
        current = {"min": 5, "max": 95}
        result = check_range_violation(baseline, current)
        assert result is None


class TestZeroVariance:
    def test_zero_variance(self):
        result = check_zero_variance({"std": 0, "mean": 5})
        assert result is not None
        assert result["issue"] == "zero_variance"

    def test_nonzero_variance(self):
        result = check_zero_variance({"std": 1.5})
        assert result is None


class TestClassifySeverity:
    def test_healthy(self):
        assert classify_severity(0.05, []) == "healthy"

    def test_warning_psi(self):
        assert classify_severity(0.15, []) == "warning"

    def test_critical_psi(self):
        assert classify_severity(0.30, []) == "critical"

    def test_warning_with_issues(self):
        assert classify_severity(0.05, [{"issue": "null_spike"}]) == "warning"

    def test_critical_range(self):
        assert classify_severity(0.05, [{"issue": "range_violation"}]) == "critical"


# --- Monitoring plugin tests ---


@pytest.fixture()
def db_with_baselines(tmp_path: Path) -> CatalogDB:
    db = CatalogDB(str(tmp_path / "test.db"))
    db.init_db()
    source = DataSource(name="src", path="/data/test.parquet")
    db.add_source(source)

    # Feature with stable stats
    f1 = Feature(
        name="src.stable",
        data_source_id=source.id,
        column_name="stable",
        dtype="double",
        stats={"mean": 50.0, "std": 10.0, "min": 20, "max": 80, "null_ratio": 0.01},
    )
    db.upsert_feature(f1)

    # Feature with drifted stats
    f2 = Feature(
        name="src.drifted",
        data_source_id=source.id,
        column_name="drifted",
        dtype="double",
        stats={"mean": 80.0, "std": 15.0, "min": 10, "max": 200, "null_ratio": 0.15},
    )
    db.upsert_feature(f2)

    # Compute baselines with original stats
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc)

    baseline_stable = {"mean": 50.0, "std": 10.0, "min": 20, "max": 80, "null_ratio": 0.01}
    baseline_drifted = {"mean": 50.0, "std": 10.0, "min": 20, "max": 80, "null_ratio": 0.01}

    db.conn.execute(
        "INSERT INTO monitoring_baselines (feature_id, baseline_stats, computed_at) VALUES (?, ?, ?)",
        (f1.id, json.dumps(baseline_stable), now),
    )
    db.conn.execute(
        "INSERT INTO monitoring_baselines (feature_id, baseline_stats, computed_at) VALUES (?, ?, ?)",
        (f2.id, json.dumps(baseline_drifted), now),
    )
    db.conn.commit()

    return db


class TestMonitoringPlugin:
    def test_compute_baseline(self, tmp_path: Path):
        db = CatalogDB(str(tmp_path / "test.db"))
        db.init_db()
        source = DataSource(name="src", path="/data/test.parquet")
        db.add_source(source)
        db.upsert_feature(
            Feature(
                name="src.x",
                data_source_id=source.id,
                column_name="x",
                dtype="double",
                stats={"mean": 5, "std": 1},
            )
        )

        plugin = MonitoringPlugin()
        result = plugin.execute(db, None, action="baseline")

        assert result.status == "success"
        assert result.data["baselines_saved"] == 1
        db.close()

    def test_check_detects_drift(self, db_with_baselines: CatalogDB):
        plugin = MonitoringPlugin()
        result = plugin.execute(db_with_baselines, None, action="check")

        assert result.status == "success"
        details = result.data["details"]
        assert len(details) == 2

        drifted = next(d for d in details if d["feature"] == "src.drifted")
        assert drifted["severity"] in ("warning", "critical")
        assert len(drifted["issues"]) > 0

    def test_check_stable_feature(self, db_with_baselines: CatalogDB):
        plugin = MonitoringPlugin()
        result = plugin.execute(db_with_baselines, None, action="check")

        stable = next(d for d in result.data["details"] if d["feature"] == "src.stable")
        assert stable["severity"] == "healthy"

    def test_export_report(self, db_with_baselines: CatalogDB):
        plugin = MonitoringPlugin()
        result = plugin.execute(db_with_baselines, None, action="check")
        md = export_monitoring_report(result.data)
        assert "# Feature Quality Report" in md
        assert "src.drifted" in md

    def test_plugin_properties(self):
        plugin = MonitoringPlugin()
        assert plugin.name == "monitoring"
