"""Tests for the Quality Monitoring plugin and statistics utilities."""

from __future__ import annotations

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
    compute_kl_divergence,
    compute_psi,
    compute_wasserstein,
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

    def test_no_psi_no_issues_is_unknown(self):
        """Regression for UAT 'monitoring rows missing PSI' / 'severity
        unknown with numeric score' twin findings: the classifier must
        not silently bucket no-signal cases as healthy."""
        assert classify_severity(None, []) == "unknown"

    def test_no_psi_with_issues_is_warning(self):
        """When PSI is missing but issues fired, the issues are the
        signal — not 'unknown'. (e.g. baseline missing std but null-spike
        check still fired against null_ratio.)"""
        assert classify_severity(None, [{"issue": "null_spike"}]) == "warning"
        assert classify_severity(None, [{"issue": "range_violation"}]) == "critical"

    def test_every_numeric_psi_maps_to_concrete_severity(self):
        """Every numeric PSI in a representative grid must map to one of
        {healthy, warning, critical} — never 'unknown', which is reserved
        for no-signal cases."""
        for psi in (0.0, 0.05, 0.099, 0.1, 0.11, 0.20, 0.24, 0.25, 0.26, 1.0, 10.0):
            result = classify_severity(psi, [])
            assert result in ("healthy", "warning", "critical"), (
                f"PSI={psi} mapped to {result!r}; numeric PSI must never be 'unknown'"
            )


class TestComputeKLDivergence:
    """KL divergence is supplementary to PSI — exact value isn't a contract,
    but the directional invariants (identical → 0, more shift → larger)
    are."""

    def test_compute_kl_divergence_known_distribution(self) -> None:
        """KL of two identical histograms is 0 (up to Laplace-smoothing
        floor — assert near-zero, not exact 0)."""
        hist = [10.0, 20.0, 30.0, 25.0, 15.0]
        kl = compute_kl_divergence(hist, hist)
        assert kl is not None
        assert kl < 1e-3

    def test_kl_grows_with_distribution_shift(self) -> None:
        baseline = [50.0, 30.0, 15.0, 5.0]
        small_shift = [45.0, 32.0, 16.0, 7.0]
        big_shift = [5.0, 15.0, 30.0, 50.0]
        kl_small = compute_kl_divergence(baseline, small_shift)
        kl_big = compute_kl_divergence(baseline, big_shift)
        assert kl_small is not None and kl_big is not None
        assert kl_big > kl_small > 0

    def test_kl_returns_none_on_shape_mismatch(self) -> None:
        assert compute_kl_divergence([1.0, 2.0], [1.0, 2.0, 3.0]) is None

    def test_kl_returns_none_on_empty_input(self) -> None:
        assert compute_kl_divergence([], []) is None

    def test_kl_handles_zero_bins_without_blowing_up(self) -> None:
        """Laplace smoothing must keep KL finite when current has empty bins
        the baseline filled."""
        baseline = [10.0, 10.0, 10.0, 10.0]
        current = [40.0, 0.0, 0.0, 0.0]
        kl = compute_kl_divergence(baseline, current)
        assert kl is not None
        assert kl > 0


class TestComputeWasserstein:
    def test_compute_wasserstein_known_shift(self) -> None:
        """Wasserstein of [0]*100 vs [10]*100 returns 10 (each unit of
        mass moves exactly 10 units along the value axis)."""
        baseline = [0.0] * 100
        current = [10.0] * 100
        w = compute_wasserstein(baseline, current)
        assert w is not None
        assert abs(w - 10.0) < 1e-6

    def test_wasserstein_identical_samples_is_zero(self) -> None:
        samples = [1.0, 2.0, 3.0, 4.0, 5.0]
        w = compute_wasserstein(samples, samples)
        assert w == 0.0

    def test_wasserstein_returns_none_on_empty(self) -> None:
        assert compute_wasserstein([], [1.0, 2.0]) is None
        assert compute_wasserstein([1.0, 2.0], []) is None


class TestMonitoringCheckIncludesNewMetrics:
    """End-to-end: a check on a drifted feature returns kl_divergence and
    wasserstein keys in the detail row + persists them via
    save_monitoring_result."""

    def test_monitoring_check_includes_new_metrics(self, tmp_path: Path) -> None:
        db = CatalogDB(str(tmp_path / "klw.db"))
        db.init_db()
        source = DataSource(name="src", path="/data/test.parquet")
        db.add_source(source)
        db.upsert_feature(
            Feature(
                name="src.shifted",
                data_source_id=source.id,
                column_name="shifted",
                dtype="double",
                stats={"mean": 50.0, "std": 8.0, "min": 30, "max": 70, "null_ratio": 0.05},
            )
        )
        feat = db.get_feature_by_name("src.shifted")
        assert feat is not None
        db.save_baseline(
            feat.id,
            {"mean": 10.0, "std": 2.0, "min": 0, "max": 20, "null_ratio": 0.01},
        )

        try:
            plugin = MonitoringPlugin()
            result = plugin.execute(db, None, action="check")
            assert result.status == "success"

            row = next(d for d in result.data["details"] if d["feature"] == "src.shifted")
            assert "kl_divergence" in row, "result row must surface kl_divergence"
            assert "wasserstein" in row, "result row must surface wasserstein"
            assert row["kl_divergence"] is not None
            assert row["wasserstein"] is not None
            # Severity logic must stay PSI-driven (constraint: no changes
            # to severity enum / classifier).
            assert row["severity"] in ("warning", "critical")

            # Both metrics must round-trip through save → get_feature_metric_history.
            history = db.get_feature_metric_history("src.shifted", days=1)
            assert history, "history should contain the just-saved row"
            latest = history[-1]
            assert latest["kl_divergence"] is not None
            assert latest["wasserstein"] is not None
        finally:
            db.close()


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
    baseline_stable = {"mean": 50.0, "std": 10.0, "min": 20, "max": 80, "null_ratio": 0.01}
    baseline_drifted = {"mean": 50.0, "std": 10.0, "min": 20, "max": 80, "null_ratio": 0.01}

    db.save_baseline(f1.id, baseline_stable)
    db.save_baseline(f2.id, baseline_drifted)

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


class TestMonitoringUnknownSeverity:
    """Regressions for UAT drift bug #1 — 'monitoring rows missing PSI'
    and 'severity unknown / health-vs-monitoring inconsistency'.

    Both symptoms trace to one root cause: features with no current stats
    were silently labelled 'healthy' instead of 'unknown', persisting
    psi=NULL rows that misled the dashboards.
    """

    def test_feature_without_current_stats_is_unknown(self, tmp_path: Path) -> None:
        db = CatalogDB(str(tmp_path / "t.db"))
        db.init_db()
        src = DataSource(name="src", path="/data/t.parquet")
        db.add_source(src)
        # Feature with empty stats but a baseline saved (the column got
        # removed from the source between baseline and check).
        feat = Feature(
            name="src.gone",
            data_source_id=src.id,
            column_name="gone",
            dtype="float64",
            stats={},
        )
        db.upsert_feature(feat)
        persisted = db.get_feature_by_name("src.gone")
        assert persisted is not None
        db.save_baseline(persisted.id, {"mean": 5.0, "std": 1.0, "null_ratio": 0.0})

        plugin = MonitoringPlugin()
        result = plugin.execute(db, None, action="check")

        details = result.data["details"]
        gone = next(d for d in details if d["feature"] == "src.gone")
        assert gone["severity"] == "unknown"
        assert gone["psi"] is None
        # Aggregate counters split the unknown out from healthy.
        assert result.data["unknown"] >= 1

    def test_unknown_rows_excluded_from_actionable_issues(self, tmp_path: Path) -> None:
        """An 'unknown' row is a data gap, not an actionable issue —
        export_monitoring_report's Issues section should skip it so the
        operator doesn't get a false alarm asking the LLM to interpret
        nothing."""
        db = CatalogDB(str(tmp_path / "t.db"))
        db.init_db()
        src = DataSource(name="src", path="/data/t.parquet")
        db.add_source(src)
        db.upsert_feature(
            Feature(
                name="src.gone",
                data_source_id=src.id,
                column_name="gone",
                dtype="float64",
                stats={},
            )
        )
        persisted = db.get_feature_by_name("src.gone")
        assert persisted is not None
        db.save_baseline(persisted.id, {"mean": 5.0, "std": 1.0, "null_ratio": 0.0})

        plugin = MonitoringPlugin()
        result = plugin.execute(db, None, action="check")
        md = export_monitoring_report(result.data)
        # The Unknown bucket count is surfaced in the summary table.
        assert "| Unknown | 1 |" in md
        # But the Issues section (warning/critical) does not include it.
        assert "## Issues" not in md or "src.gone" not in md.split("## Issues", 1)[1]
