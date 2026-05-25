"""Service-level tests for the core online feature store."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

import pytest

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature, OnlineFeatureWrite
from featcat.catalog.online_store import canonical_entity_key, get_online_features, write_online_features

if TYPE_CHECKING:
    from pathlib import Path


def _dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _setup_backend(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    source = DataSource(name="transactions", path=str(tmp_path / "transactions.parquet"))
    db.add_source(source)
    db.upsert_feature(
        Feature(
            name="transactions.avg_spend_30d",
            data_source_id=source.id,
            column_name="avg_spend_30d",
            dtype="float64",
        )
    )
    db.upsert_feature(
        Feature(
            name="transactions.txn_count_30d",
            data_source_id=source.id,
            column_name="txn_count_30d",
            dtype="int64",
        )
    )
    return db


def _write(
    *,
    entity_key: dict[str, Any] | None = None,
    feature_ref: str = "transactions.avg_spend_30d",
    value: Any = 1.0,
    event_timestamp: str = "2026-05-25T10:00:00Z",
    created_timestamp: str | None = None,
    write_id: str | None = None,
) -> OnlineFeatureWrite:
    return OnlineFeatureWrite(
        entity_key=entity_key or {"customer_id": 1},
        feature_ref=feature_ref,
        value=value,
        value_dtype="float64",
        event_timestamp=_dt(event_timestamp),
        created_timestamp=_dt(created_timestamp) if created_timestamp else None,
        write_id=write_id,
    )


def _read_value(
    db: LocalBackend,
    *,
    entity_key: dict[str, Any] | None = None,
    feature_ref: str = "transactions.avg_spend_30d",
    project: str = "",
    feature_view: str = "",
) -> tuple[Any, bool]:
    result = get_online_features(
        db,
        entity_keys=[entity_key or {"customer_id": 1}],
        feature_refs=[feature_ref],
        project=project,
        feature_view=feature_view,
    )
    row = result.rows[0]
    return row.features[feature_ref], row.metadata[feature_ref].found


def test_entity_key_canonicalization_stable_for_reordered_composite_keys() -> None:
    left = canonical_entity_key({"region": "us", "customer_id": 1})
    right = canonical_entity_key({"customer_id": 1, "region": "us"})

    assert left == right
    assert left == '{"customer_id":1,"region":"us"}'


def test_nested_entity_key_values_rejected() -> None:
    with pytest.raises(ValueError, match="primitive JSON"):
        canonical_entity_key({"customer_id": {"nested": 1}})

    with pytest.raises(ValueError, match="primitive JSON"):
        canonical_entity_key({"customer_id": [1]})


def test_new_row_inserts(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        result = write_online_features(db, rows=[_write(value=10.0)])
        value, found = _read_value(db)
    finally:
        db.close()

    assert result.requested == 1
    assert result.written == 1
    assert value == 10.0
    assert found is True


def test_newer_event_timestamp_overwrites(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        write_online_features(db, rows=[_write(value=10.0, event_timestamp="2026-05-25T10:00:00Z")])
        result = write_online_features(db, rows=[_write(value=20.0, event_timestamp="2026-05-25T11:00:00Z")])
        value, _found = _read_value(db)
    finally:
        db.close()

    assert result.written == 1
    assert value == 20.0


def test_older_event_timestamp_skips(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        write_online_features(db, rows=[_write(value=20.0, event_timestamp="2026-05-25T11:00:00Z")])
        result = write_online_features(db, rows=[_write(value=10.0, event_timestamp="2026-05-25T10:00:00Z")])
        value, _found = _read_value(db)
    finally:
        db.close()

    assert result.skipped_older == 1
    assert value == 20.0


def test_same_timestamp_newer_created_timestamp_overwrites(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        write_online_features(
            db,
            rows=[_write(value=10.0, created_timestamp="2026-05-25T10:01:00Z")],
        )
        result = write_online_features(
            db,
            rows=[_write(value=20.0, created_timestamp="2026-05-25T10:02:00Z")],
        )
        value, _found = _read_value(db)
    finally:
        db.close()

    assert result.written == 1
    assert value == 20.0


def test_same_timestamp_older_created_timestamp_skips(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        write_online_features(
            db,
            rows=[_write(value=20.0, created_timestamp="2026-05-25T10:02:00Z")],
        )
        result = write_online_features(
            db,
            rows=[_write(value=10.0, created_timestamp="2026-05-25T10:01:00Z")],
        )
        value, _found = _read_value(db)
    finally:
        db.close()

    assert result.skipped_same_timestamp == 1
    assert value == 20.0


def test_same_timestamp_deterministic_write_id_behavior(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        write_online_features(db, rows=[_write(value=10.0, write_id="b")])
        lower = write_online_features(db, rows=[_write(value=5.0, write_id="a")])
        value_after_lower, _found = _read_value(db)
        higher = write_online_features(db, rows=[_write(value=30.0, write_id="c")])
        value_after_higher, _found = _read_value(db)
    finally:
        db.close()

    assert lower.skipped_same_timestamp == 1
    assert value_after_lower == 10.0
    assert higher.written == 1
    assert value_after_higher == 30.0


def test_null_feature_value_writes_and_reads_found_true(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        write_online_features(db, rows=[_write(value=None)])
        value, found = _read_value(db)
    finally:
        db.close()

    assert value is None
    assert found is True


def test_missing_entity_reads_found_false(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        write_online_features(db, rows=[_write(entity_key={"customer_id": 1}, value=10.0)])
        value, found = _read_value(db, entity_key={"customer_id": 2})
    finally:
        db.close()

    assert value is None
    assert found is False


def test_read_preserves_entity_order(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        write_online_features(
            db,
            rows=[
                _write(entity_key={"customer_id": 1}, value=10.0),
                _write(entity_key={"customer_id": 2}, value=20.0),
            ],
        )
        result = get_online_features(
            db,
            entity_keys=[{"customer_id": 2}, {"customer_id": 1}],
            feature_refs=["transactions.avg_spend_30d"],
        )
    finally:
        db.close()

    assert [row.entity_key for row in result.rows] == [{"customer_id": 2}, {"customer_id": 1}]
    assert [row.features["transactions.avg_spend_30d"] for row in result.rows] == [20.0, 10.0]


def test_read_preserves_feature_order(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        write_online_features(
            db,
            rows=[
                _write(feature_ref="transactions.avg_spend_30d", value=10.0),
                _write(feature_ref="transactions.txn_count_30d", value=3, write_id="count"),
            ],
        )
        result = get_online_features(
            db,
            entity_keys=[{"customer_id": 1}],
            feature_refs=["transactions.txn_count_30d", "transactions.avg_spend_30d"],
        )
    finally:
        db.close()

    assert list(result.rows[0].features) == ["transactions.txn_count_30d", "transactions.avg_spend_30d"]
    assert result.rows[0].features == {
        "transactions.txn_count_30d": 3,
        "transactions.avg_spend_30d": 10.0,
    }


def test_project_feature_view_isolation_prevents_overwrite(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        write_online_features(db, rows=[_write(value=10.0)], project="a", feature_view="v1")
        write_online_features(db, rows=[_write(value=20.0)], project="b", feature_view="v1")
        write_online_features(db, rows=[_write(value=30.0)], project="a", feature_view="v2")
        value_a_v1, found_a_v1 = _read_value(db, project="a", feature_view="v1")
        value_b_v1, found_b_v1 = _read_value(db, project="b", feature_view="v1")
        value_a_v2, found_a_v2 = _read_value(db, project="a", feature_view="v2")
    finally:
        db.close()

    assert (value_a_v1, found_a_v1) == (10.0, True)
    assert (value_b_v1, found_b_v1) == (20.0, True)
    assert (value_a_v2, found_a_v2) == (30.0, True)
