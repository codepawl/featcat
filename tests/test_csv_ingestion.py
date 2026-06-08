"""CSV source ingestion, dataset building, and materialization coverage."""

from __future__ import annotations

import csv
from typing import TYPE_CHECKING, Any

from featcat.catalog.local import LocalBackend
from featcat.catalog.materialization import materialize_latest_from_source
from featcat.catalog.models import DataSource, Feature
from featcat.catalog.online_store import get_online_features
from featcat.catalog.scanner import detect_file_format, discover_files, scan_source
from featcat.catalog.training_dataset import build_training_dataset

if TYPE_CHECKING:
    from pathlib import Path


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> Path:
    with path.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return path


def test_discover_and_scan_csv_source(tmp_path: Path) -> None:
    csv_path = _write_csv(
        tmp_path / "features.csv",
        [
            {"user_id": 1, "event_ts": "2026-01-01T00:00:00Z", "score": 10.5},
            {"user_id": 2, "event_ts": "2026-01-02T00:00:00Z", "score": 20.5},
        ],
    )

    assert detect_file_format(str(csv_path)) == "csv"
    assert discover_files(str(tmp_path), formats=("csv",)) == [str(csv_path)]

    columns = scan_source(str(csv_path))

    assert [column.column_name for column in columns] == ["user_id", "event_ts", "score"]
    assert columns[2].stats["null_count"] == 0


def test_training_dataset_builds_point_in_time_join_from_csv(tmp_path: Path) -> None:
    entity_path = _write_csv(
        tmp_path / "entities.csv",
        [{"user_id": 1, "event_ts": "2026-01-03T00:00:00Z"}],
    )
    source_path = _write_csv(
        tmp_path / "features.csv",
        [
            {"user_id": 1, "event_ts": "2026-01-01T00:00:00Z", "score": 10},
            {"user_id": 1, "event_ts": "2026-01-02T00:00:00Z", "score": 20},
            {"user_id": 1, "event_ts": "2026-01-04T00:00:00Z", "score": 999},
        ],
    )

    result = build_training_dataset(
        entity_df_path=str(entity_path),
        feature_columns=["score"],
        data_source=DataSource(
            name="features",
            path=str(source_path),
            format="csv",
            entity_key="user_id",
            event_timestamp_column="event_ts",
        ),
    )

    assert result.is_valid is True
    assert result.dataframe is not None
    assert result.dataframe["score"].to_list() == [20]


def test_materialization_supports_registered_csv_source(tmp_path: Path) -> None:
    source_path = _write_csv(
        tmp_path / "transactions.csv",
        [
            {"customer_id": 1, "event_ts": "2026-05-25T09:00:00Z", "avg_spend_30d": 10.0},
            {"customer_id": 1, "event_ts": "2026-05-25T10:00:00Z", "avg_spend_30d": 20.0},
            {"customer_id": 2, "event_ts": "2026-05-25T08:00:00Z", "avg_spend_30d": 30.0},
        ],
    )
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    source = db.add_source(
        DataSource(
            name="transactions",
            path=str(source_path),
            format="csv",
            entity_key="customer_id",
            event_timestamp_column="event_ts",
        )
    )
    db.upsert_feature(
        Feature(
            name="transactions.avg_spend_30d",
            data_source_id=source.id,
            column_name="avg_spend_30d",
            dtype="double",
        )
    )

    try:
        result = materialize_latest_from_source(db, source_name="transactions", feature_columns=["avg_spend_30d"])
        online = get_online_features(
            db,
            entity_keys=[{"customer_id": 1}, {"customer_id": 2}],
            feature_refs=["transactions.avg_spend_30d"],
        )
    finally:
        db.close()

    assert result.is_valid is True
    assert result.requested == 2
    assert online.rows[0].features["transactions.avg_spend_30d"] == 20.0
    assert online.rows[1].features["transactions.avg_spend_30d"] == 30.0
