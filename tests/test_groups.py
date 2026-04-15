"""Tests for feature groups (Feature 2)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from typer.testing import CliRunner

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature, FeatureGroup
from featcat.cli import app

runner = CliRunner()


@pytest.fixture()
def db_with_features(tmp_path: Path):
    """DB with a source and some features for group testing."""
    db = CatalogDB(str(tmp_path / "test.db"))
    db.init_db()
    source = DataSource(name="src", path="/data/test.parquet")
    db.add_source(source)
    for col in ["col_a", "col_b", "col_c"]:
        db.upsert_feature(Feature(
            name=f"src.{col}", data_source_id=source.id,
            column_name=col, dtype="int64",
        ))
    yield db
    db.close()


class TestFeatureGroups:
    def test_create_and_get(self, db_with_features: CatalogDB) -> None:
        db = db_with_features
        group = FeatureGroup(name="test_group", description="Test", project="proj", owner="alice")
        db.create_group(group)
        result = db.get_group_by_name("test_group")
        assert result is not None
        assert result.name == "test_group"
        assert result.project == "proj"

    def test_list_groups(self, db_with_features: CatalogDB) -> None:
        db = db_with_features
        db.create_group(FeatureGroup(name="g1", project="p1"))
        db.create_group(FeatureGroup(name="g2", project="p2"))
        all_groups = db.list_groups()
        assert len(all_groups) == 2
        filtered = db.list_groups(project="p1")
        assert len(filtered) == 1
        assert filtered[0].name == "g1"

    def test_add_and_list_members(self, db_with_features: CatalogDB) -> None:
        db = db_with_features
        group = FeatureGroup(name="g1")
        db.create_group(group)
        features = db.list_features()
        fids = [f.id for f in features[:2]]
        added = db.add_group_members(group.id, fids)
        assert added == 2
        members = db.list_group_members(group.id)
        assert len(members) == 2
        assert db.count_group_members(group.id) == 2

    def test_add_duplicate_member(self, db_with_features: CatalogDB) -> None:
        db = db_with_features
        group = FeatureGroup(name="g1")
        db.create_group(group)
        features = db.list_features()
        fid = features[0].id
        db.add_group_members(group.id, [fid])
        added = db.add_group_members(group.id, [fid])  # duplicate
        assert added == 0

    def test_remove_member(self, db_with_features: CatalogDB) -> None:
        db = db_with_features
        group = FeatureGroup(name="g1")
        db.create_group(group)
        features = db.list_features()
        db.add_group_members(group.id, [features[0].id, features[1].id])
        db.remove_group_member(group.id, features[0].id)
        members = db.list_group_members(group.id)
        assert len(members) == 1

    def test_delete_group_cascades(self, db_with_features: CatalogDB) -> None:
        db = db_with_features
        group = FeatureGroup(name="g1")
        db.create_group(group)
        features = db.list_features()
        db.add_group_members(group.id, [features[0].id])
        db.delete_group(group.id)
        assert db.get_group_by_name("g1") is None
        # Members should be gone too (CASCADE)
        assert db.count_group_members(group.id) == 0

    def test_duplicate_name_fails(self, db_with_features: CatalogDB) -> None:
        import sqlite3

        db = db_with_features
        db.create_group(FeatureGroup(name="g1"))
        with pytest.raises(sqlite3.IntegrityError):
            db.create_group(FeatureGroup(name="g1"))

    def test_update_group(self, db_with_features: CatalogDB) -> None:
        db = db_with_features
        group = FeatureGroup(name="g1", description="old")
        db.create_group(group)
        db.update_group(group.id, description="new", project="proj2")
        updated = db.get_group_by_name("g1")
        assert updated is not None
        assert updated.description == "new"
        assert updated.project == "proj2"


class TestGroupCLI:
    def test_workflow(self, tmp_path: Path, sample_parquet: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["source", "add", "src", str(sample_parquet)])
        runner.invoke(app, ["source", "scan", "src"])

        # Create group
        result = runner.invoke(app, ["group", "create", "mygroup", "-d", "Test group", "-p", "proj"])
        assert result.exit_code == 0
        assert "created" in result.output.lower()

        # List
        result = runner.invoke(app, ["group", "list"])
        assert "mygroup" in result.output

        # Add feature
        result = runner.invoke(app, ["group", "add", "mygroup", "src.user_id"])
        assert result.exit_code == 0

        # Show
        result = runner.invoke(app, ["group", "show", "mygroup"])
        assert "src.user_id" in result.output

        # Remove
        result = runner.invoke(app, ["group", "remove", "mygroup", "src.user_id"])
        assert result.exit_code == 0

        # Delete
        result = runner.invoke(app, ["group", "delete", "mygroup", "--yes"])
        assert result.exit_code == 0
        assert "deleted" in result.output.lower()
