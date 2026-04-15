"""Tests for usage tracking (Feature 4)."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest
from typer.testing import CliRunner

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature
from featcat.catalog.usage import log_feature_usage, resolve_user
from featcat.cli import app

runner = CliRunner()


@pytest.fixture()
def db_with_features(tmp_path: Path):
    db = CatalogDB(str(tmp_path / "test.db"))
    db.init_db()
    source = DataSource(name="src", path="/data/test.parquet")
    db.add_source(source)
    features = []
    for col in ["col_a", "col_b", "col_c"]:
        f = Feature(name=f"src.{col}", data_source_id=source.id, column_name=col, dtype="int64")
        db.upsert_feature(f)
        features.append(f)
    yield db, features
    db.close()


class TestResolveUser:
    def test_env_var(self, monkeypatch) -> None:
        monkeypatch.setenv("FEATCAT_USER", "testuser")
        assert resolve_user() == "testuser"

    def test_fallback_login(self, monkeypatch) -> None:
        monkeypatch.delenv("FEATCAT_USER", raising=False)
        with patch("os.getlogin", return_value="sysuser"):
            assert resolve_user() == "sysuser"

    def test_fallback_unknown(self, monkeypatch) -> None:
        monkeypatch.delenv("FEATCAT_USER", raising=False)
        with patch("os.getlogin", side_effect=OSError):
            assert resolve_user() == "unknown"


class TestLogFeatureUsage:
    def test_swallows_errors(self) -> None:
        """log_feature_usage should never raise, even with bad input."""
        # Pass None as db - should not raise
        log_feature_usage(None, "bad_id", "view")  # type: ignore[arg-type]


class TestUsageTracking:
    def test_log_and_get_top(self, db_with_features) -> None:
        db, features = db_with_features
        # Log some usage
        for _ in range(5):
            db.log_usage(features[0].id, "view")
        for _ in range(3):
            db.log_usage(features[1].id, "view")
        db.log_usage(features[0].id, "query")

        top = db.get_top_features(limit=10, days=30)
        assert len(top) == 2
        assert top[0]["name"] == "src.col_a"
        assert top[0]["view_count"] == 5
        assert top[0]["query_count"] == 1

    def test_orphaned_features(self, db_with_features) -> None:
        db, features = db_with_features
        # Only use features[0]
        db.log_usage(features[0].id, "view")
        orphaned = db.get_orphaned_features(days=30)
        orphaned_names = [r["name"] for r in orphaned]
        assert "src.col_b" in orphaned_names
        assert "src.col_c" in orphaned_names
        assert "src.col_a" not in orphaned_names

    def test_usage_activity(self, db_with_features) -> None:
        db, features = db_with_features
        db.log_usage(features[0].id, "view")
        db.log_usage(features[1].id, "query")
        activity = db.get_usage_activity(days=7)
        assert len(activity) >= 1
        today = activity[0]
        assert today["view_count"] + today["query_count"] == 2

    def test_feature_usage(self, db_with_features) -> None:
        db, features = db_with_features
        db.log_usage(features[0].id, "view")
        db.log_usage(features[0].id, "view")
        db.log_usage(features[0].id, "query")
        usage = db.get_feature_usage(features[0].id, days=30)
        assert usage["views"] == 2
        assert usage["queries"] == 1
        assert usage["total"] == 3
        assert usage["last_seen"] is not None


class TestUsageCLI:
    def test_usage_top(self, tmp_path: Path, sample_parquet: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["source", "add", "src", str(sample_parquet)])
        runner.invoke(app, ["source", "scan", "src"])
        # View a feature to generate usage
        runner.invoke(app, ["feature", "info", "src.user_id"])
        result = runner.invoke(app, ["usage", "top"])
        assert result.exit_code == 0
        # Should show the feature we viewed
        assert "src.user_id" in result.output

    def test_usage_orphaned(self, tmp_path: Path, sample_parquet: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["source", "add", "src", str(sample_parquet)])
        runner.invoke(app, ["source", "scan", "src"])
        result = runner.invoke(app, ["usage", "orphaned"])
        assert result.exit_code == 0
        # All features should be orphaned (no usage yet)
        assert "src." in result.output or "no recent usage" in result.output.lower() or "Orphaned" in result.output

    def test_usage_activity(self, tmp_path: Path, sample_parquet: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["source", "add", "src", str(sample_parquet)])
        runner.invoke(app, ["source", "scan", "src"])
        runner.invoke(app, ["feature", "info", "src.user_id"])
        result = runner.invoke(app, ["usage", "activity"])
        assert result.exit_code == 0

    def test_feature_info_logs_usage(self, tmp_path: Path, sample_parquet: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["source", "add", "src", str(sample_parquet)])
        runner.invoke(app, ["source", "scan", "src"])
        runner.invoke(app, ["feature", "info", "src.user_id"])

        # Check that usage was logged
        db = CatalogDB(str(tmp_path / "catalog.db"))
        db.init_db()
        feature = db.get_feature_by_name("src.user_id")
        assert feature is not None
        usage = db.get_feature_usage(feature.id, days=30)
        db.close()
        assert usage["views"] >= 1

    def test_feature_search_logs_usage(self, tmp_path: Path, sample_parquet: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["source", "add", "src", str(sample_parquet)])
        runner.invoke(app, ["source", "scan", "src"])
        runner.invoke(app, ["feature", "search", "user"])

        db = CatalogDB(str(tmp_path / "catalog.db"))
        db.init_db()
        feature = db.get_feature_by_name("src.user_id")
        assert feature is not None
        top = db.get_top_features(limit=10, days=30)
        db.close()
        # user_id should appear in search results usage
        assert any(r["name"] == "src.user_id" for r in top)
