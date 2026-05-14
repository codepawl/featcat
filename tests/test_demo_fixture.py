"""Tests for the demo fixture schema and the bundled demo-catalog.json."""

from __future__ import annotations

from pathlib import Path

import pytest

from featcat.demo.fixture import DemoFixture, load_demo_fixture


def _bundled_path() -> Path:
    return Path(__file__).parent.parent / "featcat" / "demo" / "data" / "demo-catalog.json"


def test_bundled_demo_fixture_validates() -> None:
    """The shipped demo-catalog.json must validate against the schema."""
    fixture = load_demo_fixture(_bundled_path())
    assert isinstance(fixture, DemoFixture)
    assert len(fixture.sources) >= 1
    assert len(fixture.features) >= 1


def test_bundled_fixture_has_expected_shape() -> None:
    fixture = load_demo_fixture(_bundled_path())
    source_names = {s.name for s in fixture.sources}
    assert source_names == {"device_logs", "client_logs", "demand_v2"}
    # Every feature must reference a known source (model validator covers it,
    # but assert outcome as well).
    for f in fixture.features:
        prefix = f.name.split(".", 1)[0]
        assert prefix in source_names


def test_load_demo_fixture_rejects_invalid_json(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    with pytest.raises(ValueError):
        load_demo_fixture(bad)


def test_features_must_reference_known_sources() -> None:
    """A feature with a source prefix not in `sources` should fail validation."""
    payload = {
        "description": "test",
        "version": "1.0",
        "sources": [{"name": "src_a", "path": "/demo/src_a.parquet"}],
        "features": [{"name": "src_b.x", "column_name": "x", "dtype": "int64"}],
        "docs": [],
        "groups": [],
        "lineage_edges": [],
    }
    with pytest.raises(ValueError):
        DemoFixture.model_validate(payload)


def test_features_must_be_dotted() -> None:
    payload = {
        "description": "test",
        "version": "1.0",
        "sources": [{"name": "src_a", "path": "/demo/src_a.parquet"}],
        "features": [{"name": "no_dot", "column_name": "x", "dtype": "int64"}],
        "docs": [],
        "groups": [],
        "lineage_edges": [],
    }
    with pytest.raises(ValueError):
        DemoFixture.model_validate(payload)


def test_missing_file_raises_value_error(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        load_demo_fixture(tmp_path / "does_not_exist.json")
