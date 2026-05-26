"""Online store route tests without FastAPI TestClient."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.server.routes.online import (
    OnlineFeatureReadRequest,
    OnlineFeatureWriteRequest,
    OnlineFeatureWriteRow,
    read_online_features,
    write_online_features,
)

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


def _row(
    *,
    entity_key: dict[str, Any] | None = None,
    feature_ref: str = "transactions.avg_spend_30d",
    value: Any = 1.0,
    event_timestamp: str = "2026-05-25T10:00:00Z",
    created_timestamp: str | None = None,
    write_id: str | None = None,
) -> OnlineFeatureWriteRow:
    return OnlineFeatureWriteRow(
        entity_key=entity_key or {"customer_id": 1},
        feature_ref=feature_ref,
        value=value,
        value_dtype="float64",
        event_timestamp=_dt(event_timestamp),
        created_timestamp=_dt(created_timestamp) if created_timestamp else None,
        write_id=write_id,
    )


def test_write_route_serializes_success_result(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        response = write_online_features(
            OnlineFeatureWriteRequest(
                project="churn",
                feature_view="transactions",
                source_name="transactions",
                source_path="/tmp/transactions.parquet",
                actor="api-test",
                rows=[_row(value=10.0)],
            ),
            db=db,
        )
    finally:
        db.close()

    payload = response.model_dump()
    assert payload["requested"] == 1
    assert payload["written"] == 1
    assert payload["skipped_older"] == 0
    assert payload["skipped_same_timestamp"] == 0
    assert payload["errors"] == []


def test_write_route_handles_skipped_rows(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        write_online_features(
            OnlineFeatureWriteRequest(rows=[_row(value=20.0, event_timestamp="2026-05-25T11:00:00Z")]),
            db=db,
        )
        response = write_online_features(
            OnlineFeatureWriteRequest(rows=[_row(value=10.0, event_timestamp="2026-05-25T10:00:00Z")]),
            db=db,
        )
    finally:
        db.close()

    assert response.written == 0
    assert response.skipped_older == 1


def test_read_route_preserves_entity_order(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        write_online_features(
            OnlineFeatureWriteRequest(
                rows=[
                    _row(entity_key={"customer_id": 1}, value=10.0),
                    _row(entity_key={"customer_id": 2}, value=20.0),
                ]
            ),
            db=db,
        )
        response = read_online_features(
            OnlineFeatureReadRequest(
                entity_keys=[{"customer_id": 2}, {"customer_id": 1}],
                feature_refs=["transactions.avg_spend_30d"],
            ),
            db=db,
        )
    finally:
        db.close()

    assert [row.entity_key for row in response.rows] == [{"customer_id": 2}, {"customer_id": 1}]
    assert [row.features["transactions.avg_spend_30d"] for row in response.rows] == [20.0, 10.0]


def test_read_route_preserves_feature_order(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        write_online_features(
            OnlineFeatureWriteRequest(
                rows=[
                    _row(feature_ref="transactions.avg_spend_30d", value=10.0),
                    _row(feature_ref="transactions.txn_count_30d", value=3, write_id="count"),
                ]
            ),
            db=db,
        )
        response = read_online_features(
            OnlineFeatureReadRequest(
                entity_keys=[{"customer_id": 1}],
                feature_refs=["transactions.txn_count_30d", "transactions.avg_spend_30d"],
            ),
            db=db,
        )
    finally:
        db.close()

    assert list(response.rows[0].features) == ["transactions.txn_count_30d", "transactions.avg_spend_30d"]
    assert response.rows[0].features["transactions.txn_count_30d"] == 3
    assert response.rows[0].features["transactions.avg_spend_30d"] == 10.0


def test_read_route_distinguishes_null_value_from_missing_row(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        write_online_features(
            OnlineFeatureWriteRequest(rows=[_row(entity_key={"customer_id": 1}, value=None)]),
            db=db,
        )
        response = read_online_features(
            OnlineFeatureReadRequest(
                entity_keys=[{"customer_id": 1}, {"customer_id": 2}],
                feature_refs=["transactions.avg_spend_30d"],
            ),
            db=db,
        )
    finally:
        db.close()

    present = response.rows[0]
    missing = response.rows[1]
    assert present.features["transactions.avg_spend_30d"] is None
    assert present.metadata["transactions.avg_spend_30d"].found is True
    assert present.metadata["transactions.avg_spend_30d"].event_timestamp is not None
    assert missing.features["transactions.avg_spend_30d"] is None
    assert missing.metadata["transactions.avg_spend_30d"].found is False
    assert missing.metadata["transactions.avg_spend_30d"].event_timestamp is None


def test_write_route_validation_errors_are_structured(tmp_path: Path) -> None:
    db = _setup_backend(tmp_path)
    try:
        response = write_online_features(
            OnlineFeatureWriteRequest(
                rows=[
                    _row(
                        entity_key={"customer_id": {"nested": 1}},
                        value=10.0,
                    ),
                    _row(feature_ref="missing.feature", value=20.0),
                ]
            ),
            db=db,
        )
    finally:
        db.close()

    payload = response.model_dump()
    assert payload["requested"] == 2
    assert payload["written"] == 0
    assert payload["errors"] == [
        {
            "index": 0,
            "code": "invalid_entity_key",
            "message": "entity_key values must be primitive JSON values",
            "field": "entity_key",
        },
        {
            "index": 1,
            "code": "unknown_feature_ref",
            "message": "Feature is not registered: missing.feature",
            "field": "feature_ref",
        },
    ]
