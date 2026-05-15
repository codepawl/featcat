"""Regression coverage for plugins/monitoring.py paths not exercised by test_monitoring.py.

Targets the branches surfaced by `--cov-report=term-missing`:
- execute() routing to baseline / check / unknown actions
- _compute_baseline single-feature lookup + skip-when-stats-missing
- _run_check single-feature mode, exception handler, refresh_baseline, use_llm fan-out
- _check_feature zero-variance issue detection
- _add_llm_analysis + _persist_llm_outcome happy path (LLM mocked)
- _normalize_action_text str + dict shapes + empty input
- export_monitoring_report llm_analysis section
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pytest

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature
from featcat.plugins.monitoring import MonitoringPlugin, export_monitoring_report

if TYPE_CHECKING:
    from pathlib import Path


class StubLLM:
    """Minimal BaseLLM stand-in for monitoring tests.

    Mocked at the test boundary per the project pattern (see `mock_llm`
    fixture in conftest). Only the methods monitoring actually calls are
    implemented.
    """

    def __init__(self, payload: dict[str, Any] | None = None, raise_on_call: bool = False) -> None:
        self.payload = payload or {"analyses": []}
        self.raise_on_call = raise_on_call
        self.calls: list[dict[str, Any]] = []

    def generate_json(self, prompt: str, system: str | None = None, think: bool = False) -> dict[str, Any]:
        self.calls.append({"prompt": prompt, "system": system, "think": think})
        if self.raise_on_call:
            raise RuntimeError("LLM unavailable")
        return self.payload


@pytest.fixture()
def db_one_feature(tmp_path: Path) -> CatalogDB:
    db = CatalogDB(str(tmp_path / "one.db"))
    db.init_db()
    source = DataSource(name="src", path="/data/x.parquet")
    db.add_source(source)
    db.upsert_feature(
        Feature(
            name="src.alpha",
            data_source_id=source.id,
            column_name="alpha",
            dtype="double",
            stats={"mean": 10.0, "std": 2.0, "min": 0, "max": 20, "null_ratio": 0.0},
        )
    )
    yield db
    db.close()


class TestExecuteRouting:
    def test_baseline_action_dispatches_to_compute_baseline(self, db_one_feature: CatalogDB) -> None:
        result = MonitoringPlugin().execute(db_one_feature, None, action="baseline")
        assert result.status == "success"
        assert result.data["baselines_saved"] == 1

    def test_unknown_action_returns_error(self, db_one_feature: CatalogDB) -> None:
        result = MonitoringPlugin().execute(db_one_feature, None, action="not_a_real_action")
        assert result.status == "error"
        assert result.errors and "Unknown action" in result.errors[0]

    def test_description_property(self) -> None:
        assert "drift" in MonitoringPlugin().description.lower()


class TestComputeBaselineEdges:
    def test_baseline_single_feature_by_name(self, db_one_feature: CatalogDB) -> None:
        result = MonitoringPlugin().execute(db_one_feature, None, action="baseline", feature_name="src.alpha")
        assert result.status == "success"
        assert result.data["baselines_saved"] == 1
        assert result.data["total_features"] == 1

    def test_baseline_unknown_name_filters_to_empty(self, db_one_feature: CatalogDB) -> None:
        result = MonitoringPlugin().execute(db_one_feature, None, action="baseline", feature_name="src.missing")
        assert result.status == "success"
        assert result.data["baselines_saved"] == 0
        assert result.data["total_features"] == 0

    def test_baseline_skips_feature_without_stats(self, tmp_path: Path) -> None:
        db = CatalogDB(str(tmp_path / "nostats.db"))
        db.init_db()
        source = DataSource(name="src", path="/data/x.parquet")
        db.add_source(source)
        db.upsert_feature(Feature(name="src.empty", data_source_id=source.id, column_name="empty", dtype="int64"))
        try:
            result = MonitoringPlugin().execute(db, None, action="baseline")
            assert result.data["baselines_saved"] == 0
        finally:
            db.close()


class TestRunCheckEdges:
    def test_check_by_feature_name_runs_only_that_one(self, db_one_feature: CatalogDB) -> None:
        feat = db_one_feature.get_feature_by_name("src.alpha")
        assert feat is not None
        db_one_feature.save_baseline(feat.id, {"mean": 10.0, "std": 2.0, "min": 0, "max": 20, "null_ratio": 0.0})

        result = MonitoringPlugin().execute(db_one_feature, None, action="check", feature_name="src.alpha")
        assert result.status == "success"
        assert result.data["checked"] == 1
        assert result.data["details"][0]["feature"] == "src.alpha"

    def test_check_with_drift_increments_warning_counter(self, tmp_path: Path) -> None:
        """Drifted-by-mean feature lands in `warnings` bucket (line 115)."""
        db = CatalogDB(str(tmp_path / "warn.db"))
        db.init_db()
        source = DataSource(name="src", path="/data/x.parquet")
        db.add_source(source)
        db.upsert_feature(
            Feature(
                name="src.warn",
                data_source_id=source.id,
                column_name="warn",
                dtype="double",
                stats={"mean": 12.0, "std": 2.0, "min": 0, "max": 20, "null_ratio": 0.0},
            )
        )
        feat = db.get_feature_by_name("src.warn")
        assert feat is not None
        db.save_baseline(feat.id, {"mean": 10.0, "std": 2.0, "min": 0, "max": 20, "null_ratio": 0.0})

        try:
            result = MonitoringPlugin().execute(db, None, action="check")
            assert result.data["warnings"] + result.data["critical"] >= 1
        finally:
            db.close()

    def test_check_handles_exception_per_feature(
        self, db_one_feature: CatalogDB, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When _check_feature raises, run continues and records the error row (lines 167-176)."""
        feat = db_one_feature.get_feature_by_name("src.alpha")
        assert feat is not None
        db_one_feature.save_baseline(feat.id, {"mean": 10.0, "std": 2.0, "min": 0, "max": 20, "null_ratio": 0.0})

        plugin = MonitoringPlugin()

        def explode(self: MonitoringPlugin, feature: Feature, baseline: dict) -> dict:  # noqa: ARG001
            raise RuntimeError("boom")

        monkeypatch.setattr(MonitoringPlugin, "_check_feature", explode)
        result = plugin.execute(db_one_feature, None, action="check")
        assert result.status == "success"
        assert any(d["severity"] == "error" and d["feature"] == "src.alpha" for d in result.data["details"])
        assert result.data["critical"] >= 1

    def test_check_with_refresh_baseline_recomputes(self, db_one_feature: CatalogDB) -> None:
        """refresh_baseline=True triggers _compute_baseline pass after check (line 187)."""
        feat = db_one_feature.get_feature_by_name("src.alpha")
        assert feat is not None
        db_one_feature.save_baseline(feat.id, {"mean": 10.0, "std": 2.0, "min": 0, "max": 20, "null_ratio": 0.0})

        result = MonitoringPlugin().execute(db_one_feature, None, action="check", refresh_baseline=True)
        assert result.status == "success"

    def test_check_with_use_llm_invokes_llm(self, tmp_path: Path) -> None:
        """use_llm=True + issues triggers _add_llm_analysis (lines 183-184, 252-272)."""
        db = CatalogDB(str(tmp_path / "llm.db"))
        db.init_db()
        source = DataSource(name="src", path="/data/x.parquet")
        db.add_source(source)
        db.upsert_feature(
            Feature(
                name="src.drift",
                data_source_id=source.id,
                column_name="drift",
                dtype="double",
                stats={"mean": 80.0, "std": 15.0, "min": 10, "max": 200, "null_ratio": 0.15},
            )
        )
        feat = db.get_feature_by_name("src.drift")
        assert feat is not None
        db.save_baseline(feat.id, {"mean": 10.0, "std": 2.0, "min": 0, "max": 20, "null_ratio": 0.0})

        llm = StubLLM(
            payload={
                "analyses": [
                    {
                        "feature": "src.drift",
                        "likely_cause": "data pipeline bug",
                        "recommended_actions": ["Investigate ETL job", {"title": "Backfill", "detail": "rerun"}],
                    }
                ]
            }
        )
        try:
            result = MonitoringPlugin().execute(db, llm, action="check", use_llm=True)
            assert result.status == "success"
            assert llm.calls, "LLM should be called when use_llm=True and issues present"
            drift_row = next(d for d in result.data["details"] if d["feature"] == "src.drift")
            assert "llm_analysis" in drift_row

            # _persist_llm_outcome should have created at least one action item.
            actions = db.list_action_items(source="drift_alert")
            assert any(a["feature_name"] == "src.drift" for a in actions)
        finally:
            db.close()


class TestCheckFeatureEdges:
    def test_zero_variance_issue_recorded(self, tmp_path: Path) -> None:
        """current.std == 0 triggers zero_variance issue (line 233)."""
        db = CatalogDB(str(tmp_path / "zv.db"))
        db.init_db()
        source = DataSource(name="src", path="/data/x.parquet")
        db.add_source(source)
        db.upsert_feature(
            Feature(
                name="src.flat",
                data_source_id=source.id,
                column_name="flat",
                dtype="double",
                stats={"mean": 5.0, "std": 0.0, "min": 5, "max": 5, "null_ratio": 0.0},
            )
        )
        feat = db.get_feature_by_name("src.flat")
        assert feat is not None
        db.save_baseline(feat.id, {"mean": 5.0, "std": 1.0, "min": 0, "max": 10, "null_ratio": 0.0})

        try:
            result = MonitoringPlugin().execute(db, None, action="check")
            flat = next(d for d in result.data["details"] if d["feature"] == "src.flat")
            assert any(i["issue"] == "zero_variance" for i in flat["issues"])
        finally:
            db.close()


class TestNormalizeActionText:
    def test_dict_with_title_and_description(self) -> None:
        title, rec = MonitoringPlugin._normalize_action_text(
            {"title": "Investigate", "description": "Check the ETL job for null spikes"}
        )
        assert title == "Investigate"
        assert "ETL" in rec

    def test_dict_fallback_to_action_field(self) -> None:
        title, rec = MonitoringPlugin._normalize_action_text({"action": "Rerun pipeline"})
        assert title == "Rerun pipeline"
        # When no description/detail/recommendation, falls back to title text.
        assert rec == "Rerun pipeline"

    def test_str_input(self) -> None:
        title, rec = MonitoringPlugin._normalize_action_text("Backfill the table\nfor the past 7 days")
        assert title == "Backfill the table"
        assert "past 7 days" in rec

    def test_empty_string_returns_empty(self) -> None:
        assert MonitoringPlugin._normalize_action_text("") == ("", "")
        assert MonitoringPlugin._normalize_action_text("   ") == ("", "")

    def test_long_title_truncated_to_120_chars(self) -> None:
        long_line = "x" * 200
        title, _ = MonitoringPlugin._normalize_action_text(long_line)
        assert len(title) == 120


class TestPersistLLMOutcomeEdges:
    def test_missing_feature_short_circuits(self, db_one_feature: CatalogDB) -> None:
        """When the feature in the issue is not in the catalog, persist is a no-op (lines 276-278)."""
        plugin = MonitoringPlugin()
        plugin._persist_llm_outcome(
            db_one_feature,
            issue={"feature": "src.nonexistent", "severity": "warning", "psi": 0.15, "issues": []},
            analysis={"likely_cause": "x", "recommended_actions": ["something"]},
        )
        # No new action items should have been created against the alpha feature
        actions = db_one_feature.list_action_items()
        assert all(a["feature_name"] != "src.nonexistent" for a in actions)

    def test_dedupes_against_existing_pending_action(self, db_one_feature: CatalogDB) -> None:
        """If a pending action with the same title exists, skip creating duplicate (line 295)."""
        feat = db_one_feature.get_feature_by_name("src.alpha")
        assert feat is not None
        db_one_feature.create_action_item(feat.id, "drift_alert", "Already pending", "rec")

        plugin = MonitoringPlugin()
        plugin._persist_llm_outcome(
            db_one_feature,
            issue={"feature": "src.alpha", "severity": "warning", "psi": 0.15, "issues": []},
            analysis={
                "likely_cause": "x",
                "recommended_actions": ["Already pending", "Something new"],
            },
        )

        items = db_one_feature.list_action_items(source="drift_alert")
        titles = [i["title"] for i in items]
        assert titles.count("Already pending") == 1
        assert "Something new" in titles


class TestAddLLMAnalysisFailureSwallowed:
    def test_llm_raise_does_not_propagate(self, db_one_feature: CatalogDB) -> None:
        """_add_llm_analysis catches LLM exceptions so a monitoring run still completes."""
        feat = db_one_feature.get_feature_by_name("src.alpha")
        assert feat is not None
        db_one_feature.save_baseline(feat.id, {"mean": 10.0, "std": 2.0, "min": 0, "max": 20, "null_ratio": 0.0})
        # Force an "issue" by mutating the feature stats away from baseline
        db_one_feature.upsert_feature(
            Feature(
                name="src.alpha",
                data_source_id=db_one_feature.list_features()[0].data_source_id,
                column_name="alpha",
                dtype="double",
                stats={"mean": 80.0, "std": 15.0, "min": 10, "max": 200, "null_ratio": 0.15},
            )
        )

        llm = StubLLM(raise_on_call=True)
        result = MonitoringPlugin().execute(db_one_feature, llm, action="check", use_llm=True)
        assert result.status == "success"
        assert llm.calls, "LLM should be called even when it ends up raising"


class TestExportMonitoringReportLLMSection:
    def test_renders_llm_analysis_section(self) -> None:
        report = {
            "timestamp": "2026-05-15T00:00:00+00:00",
            "total_features": 1,
            "checked": 1,
            "healthy": 0,
            "warnings": 1,
            "critical": 0,
            "unknown": 0,
            "details": [
                {
                    "feature": "src.alpha",
                    "severity": "warning",
                    "psi": 0.15,
                    "issues": [{"message": "Null ratio spike"}],
                    "llm_analysis": {
                        "likely_cause": "Pipeline gap on 2026-05-01",
                        "recommended_actions": ["Backfill", "Add monitoring on upstream job"],
                    },
                }
            ],
        }
        md = export_monitoring_report(report)
        assert "Likely cause" in md
        assert "Pipeline gap" in md
        assert "Backfill" in md
        assert "Add monitoring on upstream job" in md
