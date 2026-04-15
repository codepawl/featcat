"""Tests for feature definitions (Feature 3)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from typer.testing import CliRunner

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature
from featcat.cli import app

runner = CliRunner()


@pytest.fixture()
def db_with_feature(tmp_path: Path):
    db = CatalogDB(str(tmp_path / "test.db"))
    db.init_db()
    source = DataSource(name="src", path="/data/test.parquet")
    db.add_source(source)
    feature = Feature(name="src.col_a", data_source_id=source.id, column_name="col_a", dtype="int64")
    db.upsert_feature(feature)
    yield db, feature
    db.close()


class TestFeatureDefinitions:
    def test_set_and_get_sql(self, db_with_feature) -> None:
        db, feature = db_with_feature
        db.set_feature_definition(feature.id, "SELECT col_a FROM table", "sql")
        defn = db.get_feature_definition(feature.id)
        assert defn is not None
        assert defn["definition"] == "SELECT col_a FROM table"
        assert defn["definition_type"] == "sql"

    def test_set_and_get_python(self, db_with_feature) -> None:
        db, feature = db_with_feature
        db.set_feature_definition(feature.id, "df['col'].rolling(30).mean()", "python")
        defn = db.get_feature_definition(feature.id)
        assert defn is not None
        assert defn["definition_type"] == "python"

    def test_set_and_get_manual(self, db_with_feature) -> None:
        db, feature = db_with_feature
        db.set_feature_definition(feature.id, "Computed from raw sensor data", "manual")
        defn = db.get_feature_definition(feature.id)
        assert defn is not None
        assert defn["definition_type"] == "manual"

    def test_none_by_default(self, db_with_feature) -> None:
        db, feature = db_with_feature
        defn = db.get_feature_definition(feature.id)
        assert defn is None

    def test_overwrite(self, db_with_feature) -> None:
        db, feature = db_with_feature
        db.set_feature_definition(feature.id, "old", "sql")
        db.set_feature_definition(feature.id, "new", "python")
        defn = db.get_feature_definition(feature.id)
        assert defn is not None
        assert defn["definition"] == "new"
        assert defn["definition_type"] == "python"

    def test_clear(self, db_with_feature) -> None:
        db, feature = db_with_feature
        db.set_feature_definition(feature.id, "SELECT 1", "sql")
        db.clear_feature_definition(feature.id)
        defn = db.get_feature_definition(feature.id)
        assert defn is None


class TestDefinitionCLI:
    def test_set_and_show(self, tmp_path: Path, sample_parquet: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["source", "add", "src", str(sample_parquet)])
        runner.invoke(app, ["source", "scan", "src"])

        # Set SQL definition
        result = runner.invoke(app, ["feature", "set-definition", "src.user_id", "--sql", "SELECT user_id FROM users"])
        assert result.exit_code == 0
        assert "set" in result.output.lower()

        # Show definition
        result = runner.invoke(app, ["feature", "show-definition", "src.user_id"])
        assert result.exit_code == 0
        assert "SELECT user_id FROM users" in result.output

    def test_requires_exactly_one_type(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        # No type provided
        result = runner.invoke(app, ["feature", "set-definition", "src.col"])
        assert result.exit_code == 1

    def test_show_no_definition(self, tmp_path: Path, sample_parquet: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["source", "add", "src", str(sample_parquet)])
        runner.invoke(app, ["source", "scan", "src"])
        result = runner.invoke(app, ["feature", "show-definition", "src.user_id"])
        assert result.exit_code == 0
        assert "no definition" in result.output.lower()

    def test_info_includes_definition(self, tmp_path: Path, sample_parquet: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["source", "add", "src", str(sample_parquet)])
        runner.invoke(app, ["source", "scan", "src"])
        runner.invoke(app, ["feature", "set-definition", "src.user_id", "--manual", "Primary user identifier"])
        result = runner.invoke(app, ["feature", "info", "src.user_id"])
        assert "Primary user identifier" in result.output
