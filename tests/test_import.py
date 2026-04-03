"""Integration tests for the initial import workflow."""

from __future__ import annotations

from pathlib import Path

import pytest

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature
from featcat.catalog.scanner import scan_source


FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def db(tmp_path: Path) -> CatalogDB:
    db_path = str(tmp_path / "test.db")
    catalog = CatalogDB(db_path)
    catalog.init_db()
    yield catalog
    catalog.close()


def _run_import(db: CatalogDB) -> None:
    """Simulate the import_initial.py logic against test fixtures."""
    sources_cfg = [
        {"name": "device_performance", "path": str(FIXTURES_DIR / "device_performance.parquet")},
        {"name": "user_behavior_30d", "path": str(FIXTURES_DIR / "user_behavior_30d.parquet")},
    ]
    tag_rules = {
        "device_id": ["device", "identifier"],
        "cpu_usage": ["device", "performance"],
        "memory_usage": ["device", "performance"],
        "latency_ms": ["device", "network"],
        "error_count": ["device", "reliability"],
        "region": ["device", "geo"],
        "user_id": ["user", "identifier"],
        "session_count": ["user", "behavior"],
        "data_usage_gb": ["user", "usage"],
        "complaint_count": ["user", "churn"],
        "avg_session_duration": ["user", "engagement"],
        "churn_label": ["user", "target"],
        "timestamp": ["temporal"],
    }

    for cfg in sources_cfg:
        existing = db.get_source_by_name(cfg["name"])
        if existing:
            source = existing
        else:
            source = DataSource(name=cfg["name"], path=cfg["path"])
            db.add_source(source)

        columns = scan_source(cfg["path"])
        for col in columns:
            feature = Feature(
                name=f"{cfg['name']}.{col.column_name}",
                data_source_id=source.id,
                column_name=col.column_name,
                dtype=col.dtype,
                stats=col.stats,
                tags=tag_rules.get(col.column_name, []),
                owner="ds-team",
            )
            db.upsert_feature(feature)


class TestImport:
    def test_import_registers_sources(self, db: CatalogDB):
        _run_import(db)
        sources = db.list_sources()
        names = {s.name for s in sources}
        assert "device_performance" in names
        assert "user_behavior_30d" in names

    def test_import_registers_all_features(self, db: CatalogDB):
        _run_import(db)
        features = db.list_features()
        names = {f.name for f in features}
        assert "device_performance.cpu_usage" in names
        assert "device_performance.latency_ms" in names
        assert "user_behavior_30d.churn_label" in names
        assert "user_behavior_30d.data_usage_gb" in names

    def test_import_feature_count(self, db: CatalogDB):
        _run_import(db)
        device_feats = db.list_features(source_name="device_performance")
        user_feats = db.list_features(source_name="user_behavior_30d")
        assert len(device_feats) == 7  # 7 columns
        assert len(user_feats) == 7  # 7 columns

    def test_import_stats_populated(self, db: CatalogDB):
        _run_import(db)
        feat = db.get_feature_by_name("device_performance.cpu_usage")
        assert feat is not None
        assert "mean" in feat.stats
        assert "null_ratio" in feat.stats
        assert feat.stats["total_count"] == 15

    def test_import_tags_assigned(self, db: CatalogDB):
        _run_import(db)
        feat = db.get_feature_by_name("user_behavior_30d.churn_label")
        assert feat is not None
        assert "user" in feat.tags
        assert "target" in feat.tags

    def test_import_owner_set(self, db: CatalogDB):
        _run_import(db)
        feat = db.get_feature_by_name("device_performance.error_count")
        assert feat is not None
        assert feat.owner == "ds-team"

    def test_import_idempotent(self, db: CatalogDB):
        _run_import(db)
        count_1 = len(db.list_features())

        _run_import(db)
        count_2 = len(db.list_features())

        assert count_1 == count_2  # No duplicates

    def test_import_idempotent_sources(self, db: CatalogDB):
        _run_import(db)
        src_count_1 = len(db.list_sources())

        _run_import(db)
        src_count_2 = len(db.list_sources())

        assert src_count_1 == src_count_2
