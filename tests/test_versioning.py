"""Feature versioning tests."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature


@pytest.fixture()
def db_with_feature(tmp_path: Path):
    db = CatalogDB(str(tmp_path / "test.db"))
    db.init_db()
    source = DataSource(name="src", path="/data/test.parquet")
    db.add_source(source)
    feature = Feature(
        name="src.col_a",
        data_source_id=source.id,
        column_name="col_a",
        dtype="int64",
        tags=["original"],
        owner="alice",
    )
    db.upsert_feature(feature)
    yield db
    db.close()


class TestVersionSchema:
    def test_feature_versions_table_exists(self, db_with_feature: CatalogDB):
        row = db_with_feature.conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='feature_versions'"
        ).fetchone()
        assert row is not None

    def test_list_versions_empty(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        versions = db_with_feature.list_feature_versions(feature.id)
        assert versions == []


class TestVersionCreation:
    def test_tag_update_creates_version(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        db_with_feature.update_feature_tags(feature.id, ["original", "new_tag"])
        versions = db_with_feature.list_feature_versions(feature.id)
        assert len(versions) == 1
        assert versions[0]["version"] == 1
        assert "tags" in versions[0]["change_summary"]
        assert versions[0]["snapshot"]["tags"] == ["original"]

    def test_metadata_update_creates_version(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        db_with_feature.update_feature_metadata(feature.id, owner="bob", description="updated")
        versions = db_with_feature.list_feature_versions(feature.id)
        assert len(versions) == 1
        assert "owner" in versions[0]["change_summary"]
        assert versions[0]["snapshot"]["owner"] == "alice"

    def test_no_version_on_identical_update(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        db_with_feature.update_feature_tags(feature.id, ["original"])
        assert db_with_feature.list_feature_versions(feature.id) == []

    def test_no_version_on_stats_upsert(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        feature.stats = {"mean": 42.0}
        db_with_feature.upsert_feature(feature)
        assert db_with_feature.list_feature_versions(feature.id) == []

    def test_sequential_version_numbers(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        db_with_feature.update_feature_tags(feature.id, ["v1"])
        db_with_feature.update_feature_tags(feature.id, ["v2"])
        db_with_feature.update_feature_tags(feature.id, ["v3"])
        versions = db_with_feature.list_feature_versions(feature.id)
        assert [v["version"] for v in versions] == [3, 2, 1]


class TestRollback:
    def test_rollback_restores_state(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        db_with_feature.update_feature_tags(feature.id, ["changed"])
        db_with_feature.update_feature_metadata(feature.id, owner="bob")
        db_with_feature.rollback_feature(feature.id, 1)
        updated = db_with_feature.get_feature_by_name("src.col_a")
        assert updated.tags == ["original"]
        assert updated.owner == "alice"

    def test_rollback_creates_new_version(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        db_with_feature.update_feature_tags(feature.id, ["changed"])
        db_with_feature.rollback_feature(feature.id, 1)
        versions = db_with_feature.list_feature_versions(feature.id)
        assert len(versions) == 2
        assert "rollback to v1" in versions[0]["change_summary"]

    def test_rollback_nonexistent_raises(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        with pytest.raises(ValueError, match="Version 99 not found"):
            db_with_feature.rollback_feature(feature.id, 99)

    def test_get_specific_version(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        db_with_feature.update_feature_tags(feature.id, ["v1_tags"])
        v = db_with_feature.get_feature_version(feature.id, 1)
        assert v is not None
        assert v["snapshot"]["tags"] == ["original"]

    def test_get_nonexistent_version(self, db_with_feature: CatalogDB):
        feature = db_with_feature.get_feature_by_name("src.col_a")
        assert db_with_feature.get_feature_version(feature.id, 999) is None
