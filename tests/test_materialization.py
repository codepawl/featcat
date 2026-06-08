"""Service-level tests for offline-to-online materialization."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq

from featcat.catalog.local import LocalBackend
from featcat.catalog.materialization import materialize_latest_from_feature_view, materialize_latest_from_source
from featcat.catalog.models import DataSource, Feature, FeatureView
from featcat.catalog.online_store import get_online_features

if TYPE_CHECKING:
    from pathlib import Path


def _write_parquet(path: Path, data: dict[str, list[Any]]) -> None:
    pq.write_table(pa.table(data), path)


def _setup_backend(
    tmp_path: Path,
    *,
    data: dict[str, list[Any]] | None = None,
    entity_key: str | None = "customer_id",
    event_timestamp_column: str | None = "event_ts",
    created_timestamp_column: str | None = None,
    feature_columns: list[str] | None = None,
) -> LocalBackend:
    parquet_path = tmp_path / "transactions.parquet"
    if data is not None:
        _write_parquet(parquet_path, data)

    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    source = DataSource(
        name="transactions",
        path=str(parquet_path),
        entity_key=entity_key,
        event_timestamp_column=event_timestamp_column,
        created_timestamp_column=created_timestamp_column,
    )
    db.add_source(source)
    for column in feature_columns or ["avg_spend_30d"]:
        db.upsert_feature(
            Feature(
                name=f"transactions.{column}",
                data_source_id=source.id,
                column_name=column,
                dtype="float64",
            )
        )
    return db


def _read_feature(
    db: LocalBackend,
    *,
    entity_key: dict[str, Any],
    feature_ref: str = "transactions.avg_spend_30d",
    project: str = "",
    feature_view: str = "",
) -> tuple[Any, bool]:
    result = get_online_features(
        db,
        entity_keys=[entity_key],
        feature_refs=[feature_ref],
        project=project,
        feature_view=feature_view,
    )
    row = result.rows[0]
    return row.features[feature_ref], row.metadata[feature_ref].found


def _issue_codes(result: Any) -> list[str]:
    return [error.code for error in result.errors]


def test_registered_local_parquet_source_materializes_latest_row_per_entity(tmp_path: Path) -> None:
    db = _setup_backend(
        tmp_path,
        data={
            "customer_id": [1, 1, 2],
            "event_ts": [
                "2026-05-25T09:00:00Z",
                "2026-05-25T10:00:00Z",
                "2026-05-25T08:00:00Z",
            ],
            "avg_spend_30d": [10.0, 20.0, 30.0],
        },
    )
    try:
        result = materialize_latest_from_source(
            db,
            source_name="transactions",
            feature_columns=["avg_spend_30d"],
        )
        value_1, found_1 = _read_feature(db, entity_key={"customer_id": 1})
        value_2, found_2 = _read_feature(db, entity_key={"customer_id": 2})
    finally:
        db.close()

    assert result.is_valid is True
    assert result.entity_count == 2
    assert result.requested == 2
    assert result.written == 2
    assert (value_1, found_1) == (20.0, True)
    assert (value_2, found_2) == (30.0, True)


def test_newer_event_timestamp_wins(tmp_path: Path) -> None:
    db = _setup_backend(
        tmp_path,
        data={
            "customer_id": [1, 1],
            "event_ts": ["2026-05-25T11:00:00Z", "2026-05-25T10:00:00Z"],
            "avg_spend_30d": [50.0, 10.0],
        },
    )
    try:
        materialize_latest_from_source(db, source_name="transactions", feature_columns=["avg_spend_30d"])
        value, found = _read_feature(db, entity_key={"customer_id": 1})
    finally:
        db.close()

    assert (value, found) == (50.0, True)


def test_newer_created_timestamp_breaks_same_event_time_tie(tmp_path: Path) -> None:
    db = _setup_backend(
        tmp_path,
        data={
            "customer_id": [1, 1],
            "event_ts": ["2026-05-25T10:00:00Z", "2026-05-25T10:00:00Z"],
            "created_ts": ["2026-05-25T10:01:00Z", "2026-05-25T10:02:00Z"],
            "avg_spend_30d": [10.0, 20.0],
        },
        created_timestamp_column="created_ts",
    )
    try:
        materialize_latest_from_source(db, source_name="transactions", feature_columns=["avg_spend_30d"])
        value, found = _read_feature(db, entity_key={"customer_id": 1})
    finally:
        db.close()

    assert (value, found) == (20.0, True)


def test_exact_tie_uses_deterministic_row_index_fallback(tmp_path: Path) -> None:
    db = _setup_backend(
        tmp_path,
        data={
            "customer_id": [1, 1],
            "event_ts": ["2026-05-25T10:00:00Z", "2026-05-25T10:00:00Z"],
            "created_ts": ["2026-05-25T10:01:00Z", "2026-05-25T10:01:00Z"],
            "avg_spend_30d": [10.0, 20.0],
        },
        created_timestamp_column="created_ts",
    )
    try:
        materialize_latest_from_source(db, source_name="transactions", feature_columns=["avg_spend_30d"])
        value, found = _read_feature(db, entity_key={"customer_id": 1})
    finally:
        db.close()

    assert (value, found) == (20.0, True)


def test_multiple_feature_columns_expand_to_multiple_online_writes(tmp_path: Path) -> None:
    db = _setup_backend(
        tmp_path,
        data={
            "customer_id": [1, 2],
            "event_ts": ["2026-05-25T10:00:00Z", "2026-05-25T11:00:00Z"],
            "avg_spend_30d": [10.0, 20.0],
            "txn_count_30d": [3, 4],
        },
        feature_columns=["avg_spend_30d", "txn_count_30d"],
    )
    try:
        result = materialize_latest_from_source(
            db,
            source_name="transactions",
            feature_columns=["avg_spend_30d", "txn_count_30d"],
        )
        read_result = get_online_features(
            db,
            entity_keys=[{"customer_id": 1}],
            feature_refs=["transactions.avg_spend_30d", "transactions.txn_count_30d"],
        )
    finally:
        db.close()

    assert result.requested == 4
    assert result.written == 4
    assert result.feature_count == 2
    assert read_result.rows[0].features == {
        "transactions.avg_spend_30d": 10.0,
        "transactions.txn_count_30d": 3,
    }


def test_null_feature_value_is_written_and_reads_found_true(tmp_path: Path) -> None:
    db = _setup_backend(
        tmp_path,
        data={
            "customer_id": [1],
            "event_ts": ["2026-05-25T10:00:00Z"],
            "avg_spend_30d": pa.array([None], type=pa.float64()),
        },
    )
    try:
        result = materialize_latest_from_source(db, source_name="transactions", feature_columns=["avg_spend_30d"])
        value, found = _read_feature(db, entity_key={"customer_id": 1})
    finally:
        db.close()

    assert result.written == 1
    assert value is None
    assert found is True


def test_missing_entity_key_metadata_returns_structured_validation_failure(tmp_path: Path) -> None:
    db = _setup_backend(
        tmp_path,
        data={
            "customer_id": [1],
            "event_ts": ["2026-05-25T10:00:00Z"],
            "avg_spend_30d": [10.0],
        },
        entity_key=None,
    )
    try:
        result = materialize_latest_from_source(db, source_name="transactions", feature_columns=["avg_spend_30d"])
    finally:
        db.close()

    assert result.is_valid is False
    assert _issue_codes(result) == ["missing_entity_key"]
    assert result.requested == 0


def test_missing_event_timestamp_metadata_returns_structured_validation_failure(tmp_path: Path) -> None:
    db = _setup_backend(
        tmp_path,
        data={
            "customer_id": [1],
            "event_ts": ["2026-05-25T10:00:00Z"],
            "avg_spend_30d": [10.0],
        },
        event_timestamp_column=None,
    )
    try:
        result = materialize_latest_from_source(db, source_name="transactions", feature_columns=["avg_spend_30d"])
    finally:
        db.close()

    assert result.is_valid is False
    assert _issue_codes(result) == ["missing_event_timestamp_column"]
    assert result.requested == 0


def test_missing_feature_column_returns_structured_validation_failure(tmp_path: Path) -> None:
    db = _setup_backend(
        tmp_path,
        data={
            "customer_id": [1],
            "event_ts": ["2026-05-25T10:00:00Z"],
            "avg_spend_30d": [10.0],
        },
        feature_columns=["avg_spend_30d", "txn_count_30d"],
    )
    try:
        result = materialize_latest_from_source(
            db,
            source_name="transactions",
            feature_columns=["avg_spend_30d", "txn_count_30d"],
        )
    finally:
        db.close()

    assert result.is_valid is False
    assert _issue_codes(result) == ["missing_feature_column"]
    assert result.requested == 0


def test_validation_failure_does_not_write_online_values(tmp_path: Path) -> None:
    db = _setup_backend(
        tmp_path,
        data={
            "customer_id": [1],
            "event_ts": ["2026-05-25T10:00:00Z"],
            "avg_spend_30d": [10.0],
        },
    )
    try:
        result = materialize_latest_from_source(db, source_name="transactions", feature_columns=["missing_feature"])
        value, found = _read_feature(db, entity_key={"customer_id": 1})
    finally:
        db.close()

    assert result.is_valid is False
    assert result.requested == 0
    assert value is None
    assert found is False


def test_feature_view_materialization_resolves_feature_columns(tmp_path: Path) -> None:
    db = _setup_backend(
        tmp_path,
        data={
            "customer_id": [1, 1, 2],
            "event_ts": [
                "2026-05-25T09:00:00Z",
                "2026-05-25T10:00:00Z",
                "2026-05-25T08:00:00Z",
            ],
            "bad_signal_days_7d": [1, 2, 3],
        },
        feature_columns=["bad_signal_days_7d"],
    )
    db.upsert_feature_view(
        FeatureView(
            name="network.bad_signal_view",
            entity="customer",
            source_name="transactions",
            feature_names=["transactions.bad_signal_days_7d"],
        )
    )
    try:
        result = materialize_latest_from_feature_view(
            db,
            feature_view_name="network.bad_signal_view",
        )
        value, found = _read_feature(
            db,
            entity_key={"customer_id": 1},
            feature_ref="transactions.bad_signal_days_7d",
            feature_view="network.bad_signal_view",
        )
    finally:
        db.close()

    assert result.is_valid is True
    assert result.feature_view == "network.bad_signal_view"
    assert result.feature_columns == ["bad_signal_days_7d"]
    assert (value, found) == (2, True)
