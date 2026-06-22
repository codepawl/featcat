"""Tests for the catalog module: models, db, scanner, and CLI."""

from __future__ import annotations

import sqlite3
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from sqlalchemy import text
from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import (
    BusinessMetric,
    ColumnInfo,
    DataSource,
    Entity,
    EntityRelationship,
    Feature,
    FeatureGroup,
    FeatureSet,
    FeatureView,
)
from featcat.catalog.scanner import scan_source
from featcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path

    from featcat.catalog.db import CatalogDB

runner = CliRunner()


# --- Model tests ---


class TestModels:
    def test_data_source_defaults(self):
        ds = DataSource(name="test", path="/tmp/test.parquet")
        assert ds.id
        assert ds.storage_type == "local"
        assert ds.format == "parquet"
        assert ds.entity_key is None
        assert ds.event_timestamp_column is None
        assert ds.created_timestamp_column is None

    def test_feature_defaults(self):
        f = Feature(name="test.col", data_source_id="abc", column_name="col")
        assert f.tags == []
        assert f.stats == {}
        assert f.leakage_risk == "low"
        assert f.entity_grain is None
        assert f.business_metric_name is None

    def test_business_metric_validation(self):
        metric = BusinessMetric(
            name="network_quality.bad_signal_days_7d",
            business_metric_name="bad_signal_days_7d",
            business_definition="So ngay tin hieu kem trong 7 ngay gan nhat",
            metric_domain="network_quality",
            lifecycle_stage="consume",
            metric_group="signal",
            metric_level="customer",
            entity_grain="customer_id",
            mapped_features=["network_quality_customer_7d.bad_signal_days_7d"],
        )

        assert metric.lifecycle_status == "draft"
        assert metric.allowed_use_cases == []

        with pytest.raises(ValueError, match="metric_domain"):
            BusinessMetric(
                name="invalid.domain",
                business_metric_name="bad_signal_days_7d",
                metric_domain="invalid",
                lifecycle_stage="consume",
                metric_level="customer",
                entity_grain="customer_id",
                mapped_features=["network_quality_customer_7d.bad_signal_days_7d"],
            )

        unmapped = BusinessMetric(
            name="network_quality.empty",
            business_metric_name="empty_metric",
            metric_domain="network_quality",
            lifecycle_stage="consume",
            metric_level="customer",
            entity_grain="customer_id",
        )
        assert unmapped.mapped_features == []

        with pytest.raises(ValueError, match="aggregation_rule"):
            BusinessMetric(
                name="network_quality.mixed",
                business_metric_name="mixed",
                metric_domain="network_quality",
                lifecycle_stage="consume",
                metric_level="mixed",
                entity_grain="device_id",
                mapped_features=["network_quality_customer_7d.bad_signal_days_7d"],
            )

    def test_entity_validation(self):
        entity = Entity(
            name="customer",
            primary_keys=["customer_id"],
            join_keys=["customer_id"],
            description="Customer level entity",
            owner="data-platform",
        )
        assert entity.lifecycle_status == "draft"

        with pytest.raises(ValueError, match="primary_keys"):
            Entity(name="bad", primary_keys=[], join_keys=["customer_id"])

        with pytest.raises(ValueError, match="lifecycle_status"):
            Entity(name="bad", primary_keys=["customer_id"], join_keys=["customer_id"], lifecycle_status="x")

    def test_entity_relationship_validation(self):
        rel = EntityRelationship(
            name="customer_has_contracts",
            left_entity="customer",
            right_entity="contract",
            relation_type="one_to_many",
            join_keys=[{"left_key": "customer_id", "right_key": "customer_id"}],
            valid_from="contract_start_date",
        )
        assert rel.lifecycle_status == "draft"

        with pytest.raises(ValueError, match="relation_type"):
            EntityRelationship(
                name="bad",
                left_entity="customer",
                right_entity="contract",
                relation_type="invalid",
                join_keys=[{"left_key": "customer_id", "right_key": "customer_id"}],
            )

        with pytest.raises(ValueError, match="join_keys"):
            EntityRelationship(
                name="bad",
                left_entity="customer",
                right_entity="contract",
                relation_type="one_to_many",
                join_keys=[],
            )

    def test_column_info(self):
        ci = ColumnInfo(column_name="x", dtype="int64", stats={"mean": 5.0})
        assert ci.column_name == "x"
        assert ci.stats["mean"] == 5.0


# --- DB tests ---


class TestDB:
    def test_add_and_get_source(self, db: CatalogDB):
        source = DataSource(
            name="s1",
            path="/data/test.parquet",
            entity_key="user_id",
            event_timestamp_column="event_ts",
            created_timestamp_column="created_at",
        )
        db.add_source(source)
        got = db.get_source_by_name("s1")
        assert got is not None
        assert got.name == "s1"
        assert got.id == source.id
        assert got.entity_key == "user_id"
        assert got.event_timestamp_column == "event_ts"
        assert got.created_timestamp_column == "created_at"

    def test_duplicate_source_fails(self, db: CatalogDB):
        db.add_source(DataSource(name="dup", path="/a"))
        with pytest.raises(Exception, match="UNIQUE constraint"):
            db.add_source(DataSource(name="dup", path="/b"))

    def test_list_sources(self, db: CatalogDB):
        db.add_source(DataSource(name="a", path="/a"))
        db.add_source(DataSource(name="b", path="/b"))
        sources = db.list_sources()
        assert len(sources) == 2

    def test_upsert_feature(self, db: CatalogDB):
        source = DataSource(name="src", path="/x")
        db.add_source(source)

        f = Feature(
            name="src.col1",
            data_source_id=source.id,
            column_name="col1",
            dtype="int64",
            stats={"mean": 10},
            entity_grain="customer_id",
        )
        db.upsert_feature(f)
        features = db.list_features()
        assert len(features) == 1
        assert features[0].stats["mean"] == 10
        assert features[0].entity_grain == "customer_id"

        # Upsert with new stats
        f2 = Feature(
            name="src.col1",
            data_source_id=source.id,
            column_name="col1",
            dtype="int64",
            stats={"mean": 20},
            entity_grain="customer_id",
        )
        db.upsert_feature(f2)
        features = db.list_features()
        assert len(features) == 1
        assert features[0].stats["mean"] == 20
        assert features[0].entity_grain == "customer_id"

    def test_feature_tags(self, db: CatalogDB):
        source = DataSource(name="src", path="/x")
        db.add_source(source)
        f = Feature(name="src.c", data_source_id=source.id, column_name="c")
        db.upsert_feature(f)

        db.update_feature_tags(f.id, ["churn", "30d"])
        got = db.get_feature_by_name("src.c")
        assert set(got.tags) == {"churn", "30d"}

    def test_search_features(self, db: CatalogDB):
        source = DataSource(name="src", path="/x")
        db.add_source(source)
        db.upsert_feature(
            Feature(
                name="src.revenue",
                data_source_id=source.id,
                column_name="revenue",
                tags=["billing"],
            )
        )
        db.upsert_feature(
            Feature(
                name="src.age",
                data_source_id=source.id,
                column_name="age",
                tags=["demographic"],
            )
        )
        results = db.search_features("revenue")
        assert len(results) == 1
        assert results[0].name == "src.revenue"

        results = db.search_features("billing")
        assert len(results) == 1

    def test_business_metric_crud_and_filters(self, db: CatalogDB):
        source = DataSource(name="network_quality_customer_7d", path="/network")
        db.add_source(source)
        feature = Feature(
            name="network_quality_customer_7d.bad_signal_days_7d",
            data_source_id=source.id,
            column_name="bad_signal_days_7d",
            dtype="int64",
        )
        db.upsert_feature(feature)

        metric = BusinessMetric(
            name="network_quality.bad_signal_days_7d",
            business_metric_name="bad_signal_days_7d",
            business_definition="So ngay tin hieu kem trong 7 ngay gan nhat",
            metric_domain="network_quality",
            lifecycle_stage="consume",
            metric_group="signal",
            metric_level="customer",
            entity_grain="customer_id",
            mapped_features=[feature.name],
            owner="network-data",
            allowed_use_cases=["churn"],
        )

        db.upsert_business_metric(metric)
        got = db.get_business_metric_by_name(metric.name)

        assert got is not None
        assert got.business_metric_name == "bad_signal_days_7d"
        assert got.mapped_features == [feature.name]
        assert got.allowed_use_cases == ["churn"]

        filtered = db.list_business_metrics(
            metric_domain="network_quality",
            lifecycle_stage="consume",
            metric_level="customer",
            owner="network-data",
        )
        assert [m.name for m in filtered] == [metric.name]

        updated = metric.model_copy(update={"owner": "ml-platform", "lifecycle_status": "validated"})
        db.upsert_business_metric(updated)
        got = db.get_business_metric_by_name(metric.name)
        assert got is not None
        assert got.owner == "ml-platform"
        assert got.lifecycle_status == "validated"

    def test_business_metric_rejects_unknown_mapped_feature(self, db: CatalogDB):
        metric = BusinessMetric(
            name="network_quality.missing",
            business_metric_name="missing",
            metric_domain="network_quality",
            lifecycle_stage="consume",
            metric_level="customer",
            entity_grain="customer_id",
            mapped_features=["missing.feature"],
        )

        with pytest.raises(ValueError, match="unknown feature"):
            db.upsert_business_metric(metric)

    def test_entity_and_relationship_crud(self, db: CatalogDB):
        customer = Entity(
            name="customer",
            primary_keys=["customer_id"],
            join_keys=["customer_id"],
            owner="data-platform",
        )
        contract = Entity(
            name="contract",
            primary_keys=["contract_id"],
            join_keys=["contract_id", "customer_id"],
            owner="data-platform",
        )
        db.upsert_entity(customer)
        db.upsert_entity(contract)

        rel = EntityRelationship(
            name="customer_has_contracts",
            left_entity="customer",
            right_entity="contract",
            relation_type="one_to_many",
            join_keys=[{"left_key": "customer_id", "right_key": "customer_id"}],
            description="One customer can have multiple contracts",
            owner="data-platform",
        )
        db.upsert_entity_relationship(rel)

        got_entity = db.get_entity_by_name("customer")
        assert got_entity is not None
        assert got_entity.primary_keys == ["customer_id"]

        got_rel = db.get_entity_relationship_by_name("customer_has_contracts")
        assert got_rel is not None
        assert got_rel.left_entity == "customer"
        assert got_rel.join_keys[0].left_key == "customer_id"
        assert got_rel.join_keys[0].right_key == "customer_id"

        assert [e.name for e in db.list_entities()] == ["contract", "customer"]
        assert [r.name for r in db.list_entity_relationships(left_entity="customer")] == ["customer_has_contracts"]

    def test_feature_view_and_set_crud(self, db: CatalogDB, tmp_path: Path):
        source_path = tmp_path / "src.parquet"
        pq.write_table(
            pa.table({"bad_signal_days_7d": [1], "contract_level_metric": [2]}),
            source_path,
        )
        source = DataSource(name="src", path=str(source_path))
        db.add_source(source)
        db.upsert_feature(
            Feature(
                name="src.bad_signal_days_7d",
                data_source_id=source.id,
                column_name="bad_signal_days_7d",
                entity_grain="customer_id",
            )
        )
        db.upsert_feature(
            Feature(
                name="src.contract_level_metric",
                data_source_id=source.id,
                column_name="contract_level_metric",
                entity_grain="contract_id",
            )
        )

        view = FeatureView(
            name="customer_network_view",
            entity="customer",
            source_name="src",
            feature_names=["src.bad_signal_days_7d"],
            owner="platform",
        )
        db.upsert_feature_view(view)
        got_view = db.get_feature_view_by_name("customer_network_view")
        assert got_view is not None
        assert got_view.entity == "customer"
        assert got_view.feature_names == ["src.bad_signal_days_7d"]

        feature_set = FeatureSet(
            name="churn_features_v1",
            target_entity="customer",
            feature_names=["src.bad_signal_days_7d"],
            owner="ml-platform",
        )
        db.upsert_feature_set(feature_set)
        got_set = db.get_feature_set_by_name("churn_features_v1")
        assert got_set is not None
        assert got_set.target_entity == "customer"
        assert got_set.feature_names == ["src.bad_signal_days_7d"]

        with pytest.raises(ValueError, match="rollup rule"):
            db.upsert_feature_set(
                FeatureSet(
                    name="bad_set",
                    target_entity="customer",
                    feature_names=["src.contract_level_metric"],
                    rollup_rules={},
                )
            )


class TestSourceMutations:
    """delete_source / update_source / scan_logs landed alongside the Sources
    UI — see ``docs/superpowers/specs/2026-05-12-sources-ui-design.md``. These
    tests pin the contract the UI relies on: cascade-delete cleans every
    dependent table, update only touches mutable fields, scan logs are
    queryable by source.
    """

    def test_delete_source_cascades_features_docs_baselines(self, db: CatalogDB):
        from datetime import datetime, timezone

        source = DataSource(name="cascade_src", path="/tmp/x.parquet")
        db.add_source(source)

        feature = Feature(
            name="cascade_src.col1",
            data_source_id=source.id,
            column_name="col1",
            dtype="int64",
        )
        db.upsert_feature(feature)

        # Add a doc + baseline so we can prove cascade reaches them.
        db.save_feature_doc(feature.id, {"short_description": "x"}, model_used="test")
        db.save_baseline(feature.id, {"mean": 1.0})
        # Add a group membership so cascade reaches feature_group_members.
        group = FeatureGroup(name="g1")
        db.create_group(group)
        db.add_group_members(group.id, [feature.id])

        removed = db.delete_source("cascade_src")

        assert removed == 1
        assert db.get_source_by_name("cascade_src") is None
        assert db.list_features() == []
        assert db.get_feature_doc(feature.id) is None
        assert db.get_baseline(feature.id) is None
        # Group itself stays; only its membership row was cascaded.
        assert db.get_group_by_name("g1") is not None
        assert db.count_group_members(group.id) == 0
        del datetime, timezone  # silence unused warnings on linters that scan top of test bodies

    def test_delete_source_returns_zero_when_no_features(self, db: CatalogDB):
        db.add_source(DataSource(name="empty_src", path="/tmp/empty.parquet"))
        removed = db.delete_source("empty_src")
        assert removed == 0
        assert db.get_source_by_name("empty_src") is None

    def test_delete_source_raises_when_missing(self, db: CatalogDB):
        with pytest.raises(KeyError, match="Source not found"):
            db.delete_source("never_added")

    def test_update_source_description_only(self, db: CatalogDB):
        original = DataSource(name="upd_src", path="/tmp/u.parquet", description="initial")
        db.add_source(original)

        updated = db.update_source("upd_src", description="changed")
        assert updated.description == "changed"
        # Re-read to confirm it persisted (not just returned in-memory).
        reread = db.get_source_by_name("upd_src")
        assert reread is not None
        assert reread.description == "changed"
        # Path/storage/format untouched.
        assert reread.path == "/tmp/u.parquet"
        assert reread.format == "parquet"

    def test_update_source_format(self, db: CatalogDB):
        db.add_source(DataSource(name="fmt_src", path="/tmp/f.csv"))
        updated = db.update_source("fmt_src", format="csv")
        assert updated.format == "csv"

    def test_update_source_join_metadata(self, db: CatalogDB):
        db.add_source(DataSource(name="join_src", path="/tmp/j.parquet"))

        updated = db.update_source(
            "join_src",
            entity_key="account_id",
            event_timestamp_column="event_ts",
            created_timestamp_column="created_ts",
        )

        assert updated.entity_key == "account_id"
        assert updated.event_timestamp_column == "event_ts"
        assert updated.created_timestamp_column == "created_ts"
        reread = db.get_source_by_name("join_src")
        assert reread is not None
        assert reread.entity_key == "account_id"
        assert reread.event_timestamp_column == "event_ts"
        assert reread.created_timestamp_column == "created_ts"

    def test_update_source_no_fields_is_noop(self, db: CatalogDB):
        original = DataSource(name="noop", path="/tmp/n.parquet", description="d")
        db.add_source(original)
        result = db.update_source("noop")
        assert result.description == "d"

    def test_update_source_raises_when_missing(self, db: CatalogDB):
        with pytest.raises(KeyError, match="Source not found"):
            db.update_source("ghost", description="x")

    def test_get_source_impact_counts_features_and_groups(self, db: CatalogDB):
        source = DataSource(name="impact_src", path="/tmp/i.parquet")
        db.add_source(source)
        f1 = Feature(name="impact_src.a", data_source_id=source.id, column_name="a")
        f2 = Feature(name="impact_src.b", data_source_id=source.id, column_name="b")
        db.upsert_feature(f1)
        db.upsert_feature(f2)
        g1 = FeatureGroup(name="grp_a")
        g2 = FeatureGroup(name="grp_b")
        db.create_group(g1)
        db.create_group(g2)
        db.add_group_members(g1.id, [f1.id])
        db.add_group_members(g2.id, [f1.id, f2.id])

        impact = db.get_source_impact("impact_src")

        assert impact["features_count"] == 2
        names = {g["name"]: g["feature_count"] for g in impact["groups"]}
        assert names == {"grp_a": 1, "grp_b": 2}

    def test_get_source_impact_empty_for_missing_source(self, db: CatalogDB):
        impact = db.get_source_impact("not_a_real_source")
        assert impact == {"features_count": 0, "groups": []}

    def test_record_and_list_scan_logs(self, db: CatalogDB):
        from datetime import datetime, timedelta, timezone

        source = DataSource(name="log_src", path="/tmp/l.parquet")
        db.add_source(source)

        t0 = datetime.now(timezone.utc)
        log_a = db.record_scan_log(
            source.id,
            started_at=t0,
            finished_at=t0 + timedelta(seconds=2),
            duration_seconds=2.0,
            status="success",
            files_scanned=1,
            features_added=4,
            triggered_by="api",
        )
        log_b = db.record_scan_log(
            source.id,
            started_at=t0 + timedelta(seconds=10),
            finished_at=t0 + timedelta(seconds=11),
            duration_seconds=1.0,
            status="failed",
            error_message="parquet read error",
            triggered_by="cli",
        )

        assert log_a and log_b and log_a != log_b

        rows = db.list_scan_logs(source.id, limit=10)
        assert len(rows) == 2
        # Newest first.
        assert rows[0].id == log_b
        assert rows[0].status == "failed"
        assert rows[0].error_message == "parquet read error"
        assert rows[1].features_added == 4
        assert rows[1].triggered_by == "api"

    def test_scan_logs_cascade_with_source_delete(self, db: CatalogDB):
        from datetime import datetime, timezone

        source = DataSource(name="cl_src", path="/tmp/cl.parquet")
        db.add_source(source)
        now = datetime.now(timezone.utc)
        db.record_scan_log(
            source.id,
            started_at=now,
            finished_at=now,
            duration_seconds=0.1,
            status="success",
            triggered_by="api",
        )
        assert len(db.list_scan_logs(source.id)) == 1

        db.delete_source("cl_src")
        # Scan logs cascade with the source row.
        assert db.list_scan_logs(source.id) == []


# --- Scanner tests ---


class TestScanner:
    def test_scan_parquet(self, sample_parquet: Path):
        columns = scan_source(str(sample_parquet))
        assert len(columns) == 4

        names = {c.column_name for c in columns}
        assert names == {"user_id", "age", "revenue", "city"}

        # Check that numeric columns have stats
        age_col = next(c for c in columns if c.column_name == "age")
        assert age_col.dtype == "int64"
        assert "mean" in age_col.stats
        assert "null_ratio" in age_col.stats
        assert age_col.stats["null_count"] == 1

        # Check string column
        city_col = next(c for c in columns if c.column_name == "city")
        assert city_col.dtype == "string"
        assert "unique_count" in city_col.stats

    def test_scan_directory(self, sample_parquet: Path):
        # sample_parquet is in tmp_path dir, scanning the dir should work
        columns = scan_source(str(sample_parquet.parent))
        assert len(columns) == 4

    def test_scan_nonexistent(self):
        with pytest.raises(FileNotFoundError):
            scan_source("/nonexistent/path")


class TestLegacyDbMigration:
    """init_db() must idempotently add columns to catalogs created before
    they existed, so legacy on-disk SQLite databases keep working after upgrade.
    """

    def test_adds_features_status_and_lineage_columns_to_legacy_db(self, tmp_path: Path):
        db_path = tmp_path / "legacy.db"
        # Hand-craft a pre-T1.1 / pre-T3.1 schema: features + feature_lineage
        # without status/status_changed_at/status_notes/parent_type/transform/
        # detected_method/parent_source_id/parent_column.
        conn = sqlite3.connect(str(db_path))
        conn.executescript(
            """
            CREATE TABLE data_sources (
                id TEXT PRIMARY KEY, name TEXT UNIQUE, path TEXT, storage_type TEXT,
                format TEXT, description TEXT, created_at TIMESTAMP, updated_at TIMESTAMP
            );
            CREATE TABLE features (
                id TEXT PRIMARY KEY, name TEXT UNIQUE, data_source_id TEXT,
                column_name TEXT, dtype TEXT, description TEXT, tags TEXT,
                owner TEXT, stats TEXT, created_at TIMESTAMP, updated_at TIMESTAMP
            );
            CREATE TABLE feature_lineage (
                id TEXT PRIMARY KEY, child_feature_id TEXT,
                parent_feature_id TEXT, created_at TIMESTAMP
            );
            """
        )
        conn.commit()
        conn.close()

        backend = LocalBackend(str(db_path))
        backend.init_db()

        with backend.session() as s:
            source_cols = {row["name"] for row in s.execute(text("PRAGMA table_info(data_sources)")).mappings()}
            features_cols = {row["name"] for row in s.execute(text("PRAGMA table_info(features)")).mappings()}
            lineage_cols = {row["name"] for row in s.execute(text("PRAGMA table_info(feature_lineage)")).mappings()}

        assert {"entity_key", "event_timestamp_column", "created_timestamp_column"} <= source_cols
        assert {"status", "status_changed_at", "status_notes"} <= features_cols
        assert {"parent_type", "parent_source_id", "parent_column", "transform", "detected_method"} <= lineage_cols

        # status defaults to 'draft' on the new column for any pre-existing rows.
        with backend.session() as s:
            s.execute(
                text(
                    "INSERT INTO features (id, name, data_source_id, column_name, dtype, created_at, updated_at) "
                    "VALUES ('f1', 'src.col', 'ds1', 'col', 'int64', '2026-01-01', '2026-01-01')"
                )
            )
            s.commit()
            row = s.execute(text("SELECT status FROM features WHERE id='f1'")).mappings().first()
            assert row is not None
            assert row["status"] == "draft"

        # Running init_db again must be idempotent — the suppressed
        # OperationalError covers "duplicate column" on re-add.
        backend.init_db()

        backend.close()


# --- CLI tests ---


class TestCLI:
    def test_init(self, tmp_path: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0
        assert "initialized" in result.output.lower()
        assert (tmp_path / "catalog.db").exists()

    def test_source_add_and_list(self, tmp_path: Path, sample_parquet: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        result = runner.invoke(app, ["source", "add", "test_src", str(sample_parquet)])
        assert result.exit_code == 0
        assert "added" in result.output.lower()

        result = runner.invoke(app, ["source", "list"])
        assert result.exit_code == 0
        assert "test_src" in result.output

    def test_source_scan(self, tmp_path: Path, sample_parquet: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["source", "add", "mydata", str(sample_parquet)])

        result = runner.invoke(app, ["source", "scan", "mydata"])
        assert result.exit_code == 0
        assert "4 features" in result.output.lower()

    def test_feature_list(self, tmp_path: Path, sample_parquet: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["source", "add", "ds", str(sample_parquet)])
        runner.invoke(app, ["source", "scan", "ds"])

        result = runner.invoke(app, ["feature", "list"])
        assert result.exit_code == 0
        assert "ds.age" in result.output

    def test_feature_info(self, tmp_path: Path, sample_parquet: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["source", "add", "ds", str(sample_parquet)])
        runner.invoke(app, ["source", "scan", "ds"])

        result = runner.invoke(app, ["feature", "info", "ds.revenue"])
        assert result.exit_code == 0
        assert "revenue" in result.output
        assert "double" in result.output

    def test_feature_tag(self, tmp_path: Path, sample_parquet: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["source", "add", "ds", str(sample_parquet)])
        runner.invoke(app, ["source", "scan", "ds"])

        result = runner.invoke(app, ["feature", "tag", "ds.age", "demographic", "user"])
        assert result.exit_code == 0
        assert "demographic" in result.output

    def test_feature_search(self, tmp_path: Path, sample_parquet: Path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["source", "add", "ds", str(sample_parquet)])
        runner.invoke(app, ["source", "scan", "ds"])

        result = runner.invoke(app, ["feature", "search", "revenue"])
        assert result.exit_code == 0
        assert "revenue" in result.output
