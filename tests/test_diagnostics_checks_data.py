"""Unit tests for ``featcat.diagnostics.checks_data``.

Each test seeds a fresh on-disk catalog at ``tmp_path/catalog.db`` and points
``FEATCAT_CATALOG_DB_PATH`` at it so the checks resolve via ``get_backend()``.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING

import pytest
from sqlalchemy import text

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.config import Settings
from featcat.diagnostics import CheckStatus
from featcat.diagnostics.checks_data import (
    data_doc_coverage,
    data_drift_recency,
    data_lineage_coverage,
    data_sources_registered,
    data_sources_scannable,
    data_stats_coverage,
)

if TYPE_CHECKING:
    from pathlib import Path


def _make_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    db_path = str(tmp_path / "catalog.db")
    monkeypatch.setenv("FEATCAT_DB_BACKEND", "sqlite")
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)
    monkeypatch.delenv("FEATCAT_DB_URL", raising=False)
    monkeypatch.delenv("FEATCAT_SERVER_URL", raising=False)
    return Settings(catalog_db_path=db_path)


@pytest.fixture()
def empty_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    settings = _make_settings(tmp_path, monkeypatch)
    LocalBackend(settings.catalog_db_path).init_db()
    return settings


@pytest.fixture()
def seeded_catalog(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Settings:
    """Catalog with 1 source pointing at a real file + 2 features (one with stats)."""
    settings = _make_settings(tmp_path, monkeypatch)
    data_file = tmp_path / "data.parquet"
    data_file.write_text("dummy")  # presence is all `data_sources_scannable` checks
    backend = LocalBackend(settings.catalog_db_path)
    backend.init_db()
    src = DataSource(name="src", path=str(data_file))
    backend.add_source(src)
    backend.upsert_feature(
        Feature(
            name="src.col_a",
            data_source_id=src.id,
            column_name="col_a",
            dtype="int64",
            stats={"mean": 1.0, "std": 0.1, "null_ratio": 0.0},
        )
    )
    backend.upsert_feature(
        Feature(
            name="src.col_b",
            data_source_id=src.id,
            column_name="col_b",
            dtype="int64",
            stats={},  # missing stats
        )
    )
    backend.close()
    return settings


class TestSourcesRegistered:
    def test_warn_when_empty(self, empty_catalog: Settings) -> None:
        result = data_sources_registered(empty_catalog)
        assert result.status is CheckStatus.WARN
        assert result.resolution is not None

    def test_pass_when_populated(self, seeded_catalog: Settings) -> None:
        result = data_sources_registered(seeded_catalog)
        assert result.status is CheckStatus.PASS
        assert result.metadata["count"] == 1


class TestSourcesScannable:
    def test_pass_when_paths_exist(self, seeded_catalog: Settings) -> None:
        result = data_sources_scannable(seeded_catalog)
        assert result.status is CheckStatus.PASS

    def test_fail_when_all_missing(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = _make_settings(tmp_path, monkeypatch)
        backend = LocalBackend(settings.catalog_db_path)
        backend.init_db()
        backend.add_source(DataSource(name="ghost", path="/does/not/exist"))
        backend.close()
        result = data_sources_scannable(settings)
        assert result.status is CheckStatus.FAIL
        assert "ghost" in result.detail

    def test_warn_when_partial(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        settings = _make_settings(tmp_path, monkeypatch)
        live = tmp_path / "live.parquet"
        live.write_text("x")
        backend = LocalBackend(settings.catalog_db_path)
        backend.init_db()
        backend.add_source(DataSource(name="live", path=str(live)))
        backend.add_source(DataSource(name="missing", path="/nope"))
        backend.close()
        result = data_sources_scannable(settings)
        assert result.status is CheckStatus.WARN

    def test_skip_when_no_sources(self, empty_catalog: Settings) -> None:
        result = data_sources_scannable(empty_catalog)
        assert result.status is CheckStatus.SKIP


class TestStatsCoverage:
    def test_warn_on_partial(self, seeded_catalog: Settings) -> None:
        # 1/2 features have stats → 50% coverage → WARN per threshold.
        result = data_stats_coverage(seeded_catalog)
        assert result.status is CheckStatus.WARN
        assert result.resolution is not None

    def test_skip_on_no_features(self, empty_catalog: Settings) -> None:
        result = data_stats_coverage(empty_catalog)
        assert result.status is CheckStatus.SKIP


class TestDocCoverage:
    def test_skip_on_empty(self, empty_catalog: Settings) -> None:
        result = data_doc_coverage(empty_catalog)
        assert result.status is CheckStatus.SKIP

    def test_fail_on_zero_docs(self, seeded_catalog: Settings) -> None:
        # 2 features, 0 docs → 0% < 40% → FAIL per spec.
        result = data_doc_coverage(seeded_catalog)
        assert result.status is CheckStatus.FAIL
        assert result.resolution is not None


class TestDriftRecency:
    def test_fail_when_never_run(self, seeded_catalog: Settings) -> None:
        result = data_drift_recency(seeded_catalog)
        assert result.status is CheckStatus.FAIL
        assert "ever recorded" in result.detail.lower()

    def test_pass_when_recent(self, seeded_catalog: Settings) -> None:
        db = LocalBackend(seeded_catalog.catalog_db_path)
        try:
            with db.session() as s:
                feat = s.execute(text("SELECT id FROM features LIMIT 1")).scalar()
                assert feat is not None
                s.execute(
                    text(
                        "INSERT INTO monitoring_checks "
                        "(id, feature_id, feature_name, severity, psi, checked_at) "
                        "VALUES ('c1', :fid, 'src.col_a', 'healthy', 0.0, :ts)"
                    ),
                    {"fid": feat, "ts": datetime.now(timezone.utc).isoformat()},
                )
                s.commit()
        finally:
            db.close()
        result = data_drift_recency(seeded_catalog)
        assert result.status is CheckStatus.PASS

    def test_warn_when_stale(self, seeded_catalog: Settings) -> None:
        ten_days_ago = (datetime.now(timezone.utc) - timedelta(days=10)).isoformat()
        db = LocalBackend(seeded_catalog.catalog_db_path)
        try:
            with db.session() as s:
                feat = s.execute(text("SELECT id FROM features LIMIT 1")).scalar()
                assert feat is not None
                s.execute(
                    text(
                        "INSERT INTO monitoring_checks "
                        "(id, feature_id, feature_name, severity, psi, checked_at) "
                        "VALUES ('c1', :fid, 'src.col_a', 'healthy', 0.0, :ts)"
                    ),
                    {"fid": feat, "ts": ten_days_ago},
                )
                s.commit()
        finally:
            db.close()
        result = data_drift_recency(seeded_catalog)
        assert result.status is CheckStatus.WARN


class TestLineageCoverage:
    def test_skip_on_empty(self, empty_catalog: Settings) -> None:
        result = data_lineage_coverage(empty_catalog)
        assert result.status is CheckStatus.SKIP

    def test_warn_on_no_edges(self, seeded_catalog: Settings) -> None:
        # 2 features, 0 edges → 0% → WARN (per spec, lineage is informational)
        result = data_lineage_coverage(seeded_catalog)
        assert result.status is CheckStatus.WARN
