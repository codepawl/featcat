"""Tests for the demo seed/clear orchestrator."""

from __future__ import annotations

from pathlib import Path

import pytest

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.demo import (
    bundled_fixture_path,
    clear_demo,
    load_demo_fixture,
    seed_demo,
)
from featcat.demo.fixture import DemoFixture


@pytest.fixture()
def empty_db(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def fixture() -> DemoFixture:
    return load_demo_fixture(bundled_fixture_path())


def test_seed_creates_demo_data(empty_db: LocalBackend, fixture: DemoFixture) -> None:
    stats = seed_demo(empty_db, fixture)
    assert stats.sources_created == len(fixture.sources)
    assert stats.features_created == len(fixture.features)
    assert stats.docs_created == len(fixture.docs)
    assert stats.groups_created == len(fixture.groups)
    assert stats.lineage_edges_created == len(fixture.lineage_edges)


def test_seed_marks_features_with_demo_tag(empty_db: LocalBackend, fixture: DemoFixture) -> None:
    seed_demo(empty_db, fixture)
    demo_features = empty_db.list_features(tag="demo")
    assert len(demo_features) == len(fixture.features)


def test_seed_is_idempotent(empty_db: LocalBackend, fixture: DemoFixture) -> None:
    first = seed_demo(empty_db, fixture)
    second = seed_demo(empty_db, fixture)
    assert second.sources_created == 0
    assert second.features_created == 0
    assert second.docs_created == 0
    assert second.groups_created == 0
    assert second.lineage_edges_created == 0
    # After two seeds the catalog still has exactly the seeded shape.
    assert len(empty_db.list_features(tag="demo")) == first.features_created


def test_clear_removes_only_demo_data(empty_db: LocalBackend, fixture: DemoFixture) -> None:
    # Pre-existing real (non-demo) data.
    real_src = empty_db.add_source(DataSource(name="real_src", path="/data/real.parquet"))
    empty_db.upsert_feature(
        Feature(
            name="real_src.real_col",
            data_source_id=real_src.id,
            column_name="real_col",
            dtype="float64",
        )
    )

    seed_demo(empty_db, fixture)
    stats = clear_demo(empty_db)
    assert stats.features_removed == len(fixture.features)
    assert stats.sources_removed == len(fixture.sources)
    assert stats.groups_removed == len(fixture.groups)
    assert stats.lineage_edges_removed == len(fixture.lineage_edges)
    assert stats.docs_removed == len(fixture.docs)

    assert empty_db.get_source_by_name("real_src") is not None
    assert empty_db.get_feature_by_name("real_src.real_col") is not None
    assert empty_db.list_features(tag="demo") == []


def test_clear_on_empty_catalog_is_noop(empty_db: LocalBackend) -> None:
    stats = clear_demo(empty_db)
    assert stats.features_removed == 0
    assert stats.sources_removed == 0
    assert stats.groups_removed == 0
    assert stats.lineage_edges_removed == 0
    assert stats.docs_removed == 0
