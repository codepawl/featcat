"""Tests for the JSONL catalog dumper."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from featcat.backup.dump import TABLE_ORDER, dump_catalog
from featcat.backup.metadata import BackupManifest, BackupMetadata
from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def populated_db(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    src = db.add_source(DataSource(name="src", path="/data/src.parquet"))
    db.upsert_feature(Feature(name="src.col", data_source_id=src.id, column_name="col", dtype="float64"))
    try:
        yield db
    finally:
        db.close()


def test_dump_writes_metadata_and_per_table_jsonl(populated_db: LocalBackend, tmp_path: Path) -> None:
    out = tmp_path / "dump"
    out.mkdir()
    meta, manifest = dump_catalog(populated_db, out)
    assert isinstance(meta, BackupMetadata)
    assert isinstance(manifest, BackupManifest)
    assert (out / "metadata.json").exists()
    assert (out / "manifest.json").exists()
    assert (out / "tables" / "data_sources.jsonl").exists()
    assert (out / "tables" / "features.jsonl").exists()


def test_dump_jsonl_rows_match_manifest_counts(populated_db: LocalBackend, tmp_path: Path) -> None:
    out = tmp_path / "dump"
    out.mkdir()
    _, manifest = dump_catalog(populated_db, out)
    for table_name, count in manifest.row_counts.items():
        path = out / "tables" / f"{table_name}.jsonl"
        if not path.exists():
            assert count == 0
            continue
        actual = sum(1 for line in path.open() if line.strip())
        assert actual == count, f"{table_name}: jsonl has {actual} rows, manifest says {count}"


def test_dump_table_order_matches_module_constant(populated_db: LocalBackend, tmp_path: Path) -> None:
    out = tmp_path / "dump"
    out.mkdir()
    _, manifest = dump_catalog(populated_db, out)
    assert manifest.table_order == TABLE_ORDER


def test_dump_skips_scheduler_state(populated_db: LocalBackend, tmp_path: Path) -> None:
    out = tmp_path / "dump"
    out.mkdir()
    _, manifest = dump_catalog(populated_db, out)
    assert "job_schedules" not in manifest.table_order
    assert "job_logs" not in manifest.table_order
    assert "alembic_version" not in manifest.table_order


def test_dump_metadata_records_stats(populated_db: LocalBackend, tmp_path: Path) -> None:
    out = tmp_path / "dump"
    out.mkdir()
    meta, _ = dump_catalog(populated_db, out)
    assert meta.stats["sources"] >= 1
    assert meta.stats["features"] >= 1
    assert meta.backend in ("sqlite", "postgres")
