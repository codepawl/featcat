"""Tests for the BackupMetadata / BackupManifest schemas."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from featcat.backup.metadata import BackupManifest, BackupMetadata


def test_metadata_round_trips_json() -> None:
    m = BackupMetadata(
        version=1,
        featcat_version="0.4.2",
        backend="sqlite",
        backend_version="3.45.0",
        alembic_version=None,
        created_at=datetime(2026, 5, 14, 10, 0, tzinfo=timezone.utc),
        stats={"sources": 3, "features": 10, "groups": 3, "lineage_edges": 3},
        embedding_model=None,
    )
    raw = m.model_dump_json()
    m2 = BackupMetadata.model_validate_json(raw)
    assert m2 == m


def test_metadata_rejects_unknown_version() -> None:
    with pytest.raises(ValueError):
        BackupMetadata.model_validate(
            {
                "version": 99,
                "featcat_version": "0.4.2",
                "backend": "sqlite",
                "backend_version": "3.45.0",
                "alembic_version": None,
                "created_at": "2026-05-14T10:00:00+00:00",
                "stats": {},
                "embedding_model": None,
            }
        )


def test_metadata_rejects_unknown_backend() -> None:
    with pytest.raises(ValueError):
        BackupMetadata.model_validate(
            {
                "version": 1,
                "featcat_version": "0.4.2",
                "backend": "mysql",
                "backend_version": "8",
                "alembic_version": None,
                "created_at": "2026-05-14T10:00:00+00:00",
                "stats": {},
                "embedding_model": None,
            }
        )


def test_manifest_records_row_counts() -> None:
    m = BackupManifest(
        table_order=["data_sources", "features"],
        row_counts={"data_sources": 3, "features": 10},
    )
    assert m.row_counts["features"] == 10


def test_manifest_rejects_unknown_fields() -> None:
    with pytest.raises(ValueError):
        BackupManifest.model_validate({"table_order": [], "row_counts": {}, "extra": "nope"})
