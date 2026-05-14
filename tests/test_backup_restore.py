"""Tests for the JSONL → catalog restore path."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from featcat.backup.dump import dump_catalog
from featcat.backup.restore import RestoreError, restore_catalog
from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def src_db(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "src.db"))
    db.init_db()
    src = db.add_source(DataSource(name="src", path="/data/src.parquet"))
    db.upsert_feature(Feature(name="src.col", data_source_id=src.id, column_name="col", dtype="float64"))
    try:
        yield db
    finally:
        db.close()


@pytest.fixture()
def dst_db(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "dst.db"))
    db.init_db()
    try:
        yield db
    finally:
        db.close()


def test_round_trip_preserves_features(src_db: LocalBackend, dst_db: LocalBackend, tmp_path: Path) -> None:
    dump_dir = tmp_path / "dump"
    dump_dir.mkdir()
    dump_catalog(src_db, dump_dir)

    counts = restore_catalog(dst_db, dump_dir, force=True)
    assert counts.get("features", 0) >= 1
    feature = dst_db.get_feature_by_name("src.col")
    assert feature is not None
    assert feature.dtype == "float64"


def test_restore_refuses_non_empty_target(src_db: LocalBackend, dst_db: LocalBackend, tmp_path: Path) -> None:
    dump_dir = tmp_path / "dump"
    dump_dir.mkdir()
    dump_catalog(src_db, dump_dir)
    dst_db.add_source(DataSource(name="other", path="/x.parquet"))

    with pytest.raises(RestoreError):
        restore_catalog(dst_db, dump_dir, force=False)


def test_restore_validates_metadata_version(dst_db: LocalBackend, tmp_path: Path) -> None:
    dump_dir = tmp_path / "dump"
    (dump_dir / "tables").mkdir(parents=True)
    (dump_dir / "metadata.json").write_text(
        json.dumps(
            {
                "version": 99,
                "featcat_version": "x",
                "backend": "sqlite",
                "backend_version": "3",
                "alembic_version": None,
                "created_at": "2026-05-14T00:00:00+00:00",
                "stats": {},
                "embedding_model": None,
            }
        ),
        encoding="utf-8",
    )
    (dump_dir / "manifest.json").write_text(json.dumps({"table_order": [], "row_counts": {}}), encoding="utf-8")

    with pytest.raises(RestoreError):
        restore_catalog(dst_db, dump_dir, force=True)


def test_restore_missing_files_errors(dst_db: LocalBackend, tmp_path: Path) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(RestoreError):
        restore_catalog(dst_db, empty, force=True)


def test_restore_rolls_back_on_failure(src_db: LocalBackend, dst_db: LocalBackend, tmp_path: Path) -> None:
    """A bad row mid-restore must roll back; the destination should look empty."""
    dump_dir = tmp_path / "dump"
    dump_dir.mkdir()
    dump_catalog(src_db, dump_dir)

    # Corrupt the features file with a row referencing a nonexistent source.
    bad = dump_dir / "tables" / "features.jsonl"
    bad.write_text(
        '{"id":"x","name":"bad","data_source_id":"nope","column_name":"c","dtype":"int64",'
        '"description":null,"owner":null,"tags":"[]","stats":"{}","status":"draft",'
        '"created_at":"2026-01-01T00:00:00","updated_at":"2026-01-01T00:00:00",'
        '"definition":null,"definition_type":null,"definition_updated_at":null,'
        '"generation_hints":null,"status_changed_at":null,"status_notes":null,'
        '"embedding":null,"search_vector":null}\n',
        encoding="utf-8",
    )

    with pytest.raises(RestoreError):
        restore_catalog(dst_db, dump_dir, force=True)

    # After the rollback the destination is back to empty.
    assert dst_db.get_feature_by_name("bad") is None
