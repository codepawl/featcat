"""Materialization schedule route tests without FastAPI TestClient."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from fastapi import HTTPException
from fastapi.routing import APIRoute
from pydantic import ValidationError

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.server.app import build_app
from featcat.server.routes.online import (
    OnlineMaterializationScheduleCreateRequest,
    OnlineMaterializationSchedulePatchRequest,
    create_materialization_schedule,
    list_materialization_schedules,
    patch_materialization_schedule,
    run_materialization_schedule,
)

if TYPE_CHECKING:
    from pathlib import Path


NOW = datetime(2026, 5, 26, 12, 0, tzinfo=timezone.utc)


def _write_parquet(path: Path, data: dict[str, list[Any]]) -> None:
    pq.write_table(pa.table(data), path)


def _backend(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    return db


def _seed_materialization_source(db: LocalBackend, tmp_path: Path) -> None:
    parquet_path = tmp_path / "transactions.parquet"
    _write_parquet(
        parquet_path,
        {
            "customer_id": [1, 1, 2],
            "event_ts": [
                "2026-05-25T09:00:00Z",
                "2026-05-25T10:00:00Z",
                "2026-05-25T08:00:00Z",
            ],
            "avg_spend_30d": [10.0, 20.0, 30.0],
        },
    )
    source = DataSource(
        name="transactions",
        path=str(parquet_path),
        entity_key="customer_id",
        event_timestamp_column="event_ts",
    )
    db.add_source(source)
    db.upsert_feature(
        Feature(
            name="transactions.avg_spend_30d",
            data_source_id=source.id,
            column_name="avg_spend_30d",
            dtype="float64",
        )
    )


def _create_request(*, name: str = "transactions-hourly") -> OnlineMaterializationScheduleCreateRequest:
    return OnlineMaterializationScheduleCreateRequest(
        name=name,
        source_name="transactions",
        feature_columns=["avg_spend_30d"],
        interval_seconds=60,
        project="churn",
        feature_view="transactions",
        actor="api-test",
    )


def test_list_materialization_schedules_returns_records(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        created = create_materialization_schedule(_create_request(), db=db)
        response = list_materialization_schedules(db=db)
    finally:
        db.close()

    assert [row.id for row in response] == [created.id]
    assert response[0].name == "transactions-hourly"
    assert response[0].schedule_type == "interval"


def test_create_interval_schedule_validates_required_fields(tmp_path: Path) -> None:
    with pytest.raises(ValidationError):
        OnlineMaterializationScheduleCreateRequest.model_validate(
            {
                "name": "transactions-hourly",
                "source_name": "transactions",
                "interval_seconds": 60,
            }
        )

    db = _backend(tmp_path)
    try:
        with pytest.raises(HTTPException) as excinfo:
            create_materialization_schedule(
                OnlineMaterializationScheduleCreateRequest(
                    name="transactions-hourly",
                    source_name="transactions",
                    feature_columns=[],
                    interval_seconds=60,
                ),
                db=db,
            )
    finally:
        db.close()

    assert excinfo.value.status_code == 400
    assert excinfo.value.detail == "feature_columns must be non-empty"


def test_disable_materialization_schedule_works(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        created = create_materialization_schedule(_create_request(), db=db)
        response = patch_materialization_schedule(
            created.id,
            OnlineMaterializationSchedulePatchRequest(enabled=False),
            db=db,
        )
        stored = db.get_materialization_schedule(created.id)
    finally:
        db.close()

    assert response.enabled is False
    assert stored is not None
    assert stored.enabled is False


def test_enable_materialization_schedule_works(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        payload = _create_request().model_dump()
        payload["enabled"] = False
        created = create_materialization_schedule(
            OnlineMaterializationScheduleCreateRequest(**payload),
            db=db,
        )
        response = patch_materialization_schedule(
            created.id,
            OnlineMaterializationSchedulePatchRequest(enabled=True),
            db=db,
        )
        stored = db.get_materialization_schedule(created.id)
    finally:
        db.close()

    assert response.enabled is True
    assert stored is not None
    assert stored.enabled is True


def test_manual_run_records_materialization_audit_with_schedule_id(tmp_path: Path) -> None:
    db = _backend(tmp_path)
    try:
        _seed_materialization_source(db, tmp_path)
        created = create_materialization_schedule(_create_request(), db=db)
        response = run_materialization_schedule(created.id, db=db)
        audits = db.list_materialization_audits()
    finally:
        db.close()

    assert response.schedule_id == created.id
    assert response.status == "success"
    assert len(audits) == 1
    assert audits[0].schedule_id == created.id
    assert audits[0].actor == "api-test"


def test_materialization_schedule_routes_are_registered_without_testclient() -> None:
    app = build_app()
    routes = {(route.path, method) for route in app.routes if isinstance(route, APIRoute) for method in route.methods}

    assert ("/api/online/materialization-schedules", "GET") in routes
    assert ("/api/online/materialization-schedules", "POST") in routes
    assert ("/api/online/materialization-schedules/{schedule_id}", "PATCH") in routes
    assert ("/api/online/materialization-schedules/{schedule_id}/run", "POST") in routes
