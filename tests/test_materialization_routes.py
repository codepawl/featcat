"""Materialization route tests without FastAPI TestClient."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.server.routes.online import OnlineMaterializationRequest, materialize_online_features, router

if TYPE_CHECKING:
    from pathlib import Path


def _write_parquet(path: Path, data: dict[str, list[Any]]) -> None:
    pq.write_table(pa.table(data), path)


def _setup_backend(
    tmp_path: Path,
    *,
    data: dict[str, list[Any]],
    feature_columns: list[str] | None = None,
    entity_key: str | None = "customer_id",
    event_timestamp_column: str | None = "event_ts",
) -> LocalBackend:
    parquet_path = tmp_path / "transactions.parquet"
    _write_parquet(parquet_path, data)

    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    source = DataSource(
        name="transactions",
        path=str(parquet_path),
        entity_key=entity_key,
        event_timestamp_column=event_timestamp_column,
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


def test_materialization_route_serializes_successful_result(tmp_path: Path) -> None:
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
            "txn_count_30d": [1, 2, 3],
        },
        feature_columns=["avg_spend_30d", "txn_count_30d"],
    )
    try:
        response = materialize_online_features(
            OnlineMaterializationRequest(
                source_name="transactions",
                feature_columns=["avg_spend_30d", "txn_count_30d"],
                project="churn",
                feature_view="transactions",
                actor="api-test",
            ),
            db=db,
        )
    finally:
        db.close()

    payload = response.model_dump()
    assert payload["is_valid"] is True
    assert payload["errors"] == []
    assert payload["warnings"] == []
    assert payload["source_name"] == "transactions"
    assert payload["source_path"] == str(tmp_path / "transactions.parquet")
    assert payload["project"] == "churn"
    assert payload["feature_view"] == "transactions"
    assert payload["entity_key"] == "customer_id"
    assert payload["event_timestamp_column"] == "event_ts"
    assert payload["created_timestamp_column"] is None
    assert payload["feature_columns"] == ["avg_spend_30d", "txn_count_30d"]
    assert payload["entity_count"] == 2
    assert payload["feature_count"] == 2
    assert payload["requested"] == 4
    assert payload["written"] == 4
    assert payload["skipped_older"] == 0
    assert payload["skipped_same_timestamp"] == 0


def test_materialization_route_returns_structured_validation_failure(tmp_path: Path) -> None:
    db = _setup_backend(
        tmp_path,
        data={
            "customer_id": [1],
            "event_ts": ["2026-05-25T10:00:00Z"],
            "avg_spend_30d": [10.0],
        },
    )
    try:
        response = materialize_online_features(
            OnlineMaterializationRequest(
                source_name="transactions",
                feature_columns=["missing_feature"],
                project="churn",
                feature_view="transactions",
            ),
            db=db,
        )
    finally:
        db.close()

    assert response.model_dump() == {
        "is_valid": False,
        "errors": [
            {
                "code": "missing_feature_column",
                "message": "Parquet source is missing feature column: missing_feature",
                "field": "missing_feature",
            }
        ],
        "warnings": [],
        "source_name": "transactions",
        "source_path": str(tmp_path / "transactions.parquet"),
        "project": "churn",
        "feature_view": "transactions",
        "entity_key": "customer_id",
        "event_timestamp_column": "event_ts",
        "created_timestamp_column": None,
        "feature_columns": ["missing_feature"],
        "entity_count": 0,
        "feature_count": 1,
        "requested": 0,
        "written": 0,
        "skipped_older": 0,
        "skipped_same_timestamp": 0,
    }


def test_materialization_route_is_registered_without_testclient() -> None:
    routes = {(route.path, tuple(sorted(route.methods or []))) for route in router.routes}

    assert ("/materialize", ("POST",)) in routes
