"""Tests for the catalog module: models, db, scanner, and CLI."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from typer.testing import CliRunner

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature, ColumnInfo
from featcat.catalog.scanner import scan_source
from featcat.cli import app

runner = CliRunner()


# --- Model tests ---


class TestModels:
    def test_data_source_defaults(self):
        ds = DataSource(name="test", path="/tmp/test.parquet")
        assert ds.id
        assert ds.storage_type == "local"
        assert ds.format == "parquet"

    def test_feature_defaults(self):
        f = Feature(name="test.col", data_source_id="abc", column_name="col")
        assert f.tags == []
        assert f.stats == {}

    def test_column_info(self):
        ci = ColumnInfo(column_name="x", dtype="int64", stats={"mean": 5.0})
        assert ci.column_name == "x"
        assert ci.stats["mean"] == 5.0


# --- DB tests ---


class TestDB:
    def test_add_and_get_source(self, db: CatalogDB):
        source = DataSource(name="s1", path="/data/test.parquet")
        db.add_source(source)
        got = db.get_source_by_name("s1")
        assert got is not None
        assert got.name == "s1"
        assert got.id == source.id

    def test_duplicate_source_fails(self, db: CatalogDB):
        db.add_source(DataSource(name="dup", path="/a"))
        with pytest.raises(Exception):
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
        )
        db.upsert_feature(f)
        features = db.list_features()
        assert len(features) == 1
        assert features[0].stats["mean"] == 10

        # Upsert with new stats
        f2 = Feature(
            name="src.col1",
            data_source_id=source.id,
            column_name="col1",
            dtype="int64",
            stats={"mean": 20},
        )
        db.upsert_feature(f2)
        features = db.list_features()
        assert len(features) == 1
        assert features[0].stats["mean"] == 20

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
