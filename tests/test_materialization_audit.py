"""Materialization audit tests without FastAPI TestClient."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq
import pytest
from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.materialization import MaterializationIssue, MaterializationResult
from featcat.catalog.materialization_audit import record_materialization_audit
from featcat.catalog.models import DataSource, Feature
from featcat.cli import app
from featcat.server.routes import online
from featcat.server.routes.online import OnlineMaterializationRequest, list_materialization_runs

if TYPE_CHECKING:
    from pathlib import Path

runner = CliRunner()


def _write_parquet(path: Path, data: dict[str, list[Any]]) -> Path:
    pq.write_table(pa.table(data), path)
    return path


def _seed_materialization_catalog(
    tmp_path: Path,
    *,
    data: dict[str, list[Any]] | None = None,
    feature_columns: list[str] | None = None,
    source_path: str | None = None,
) -> LocalBackend:
    parquet_path = source_path or str(
        _write_parquet(
            tmp_path / "transactions.parquet",
            data
            or {
                "customer_id": [1, 1, 2],
                "event_ts": [
                    "2026-05-25T09:00:00Z",
                    "2026-05-25T10:00:00Z",
                    "2026-05-25T08:00:00Z",
                ],
                "avg_spend_30d": [10.0, 20.0, 30.0],
                "txn_count_30d": [1, 2, 3],
            },
        )
    )
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    source = DataSource(
        name="transactions",
        path=parquet_path,
        entity_key="customer_id",
        event_timestamp_column="event_ts",
    )
    db.add_source(source)
    for column in feature_columns or ["avg_spend_30d", "txn_count_30d"]:
        db.upsert_feature(
            Feature(
                name=f"transactions.{column}",
                data_source_id=source.id,
                column_name=column,
                dtype="float64",
            )
        )
    return db


def _audit_result(
    *,
    is_valid: bool = True,
    source_path: str | None = "transactions.parquet",
    written: int = 4,
) -> MaterializationResult:
    return MaterializationResult(
        is_valid=is_valid,
        errors=[]
        if is_valid
        else [
            MaterializationIssue(
                code="missing_feature_column",
                message="Parquet source is missing feature column: missing_feature",
                field="missing_feature",
            )
        ],
        source_name="transactions",
        source_path=source_path,
        project="churn",
        feature_view="transactions",
        entity_key="customer_id",
        event_timestamp_column="event_ts",
        feature_columns=["avg_spend_30d", "txn_count_30d"],
        entity_count=2 if is_valid else 0,
        feature_count=2,
        requested=4 if is_valid else 0,
        written=written if is_valid else 0,
    )


def test_api_materialization_records_success_audit(tmp_path: Path) -> None:
    db = _seed_materialization_catalog(tmp_path)
    try:
        response = online.materialize_online_features(
            OnlineMaterializationRequest(
                source_name="transactions",
                feature_columns=["avg_spend_30d", "txn_count_30d"],
                project="churn",
                feature_view="transactions",
                actor="api-test",
            ),
            db=db,
        )
        audits = db.list_materialization_audits()
    finally:
        db.close()

    assert response.is_valid is True
    assert len(audits) == 1
    audit = audits[0]
    assert audit.status == "success"
    assert audit.source_name == "transactions"
    assert audit.source_path == str(tmp_path / "transactions.parquet")
    assert audit.project == "churn"
    assert audit.feature_view == "transactions"
    assert audit.entity_key == "customer_id"
    assert audit.event_timestamp_column == "event_ts"
    assert audit.created_timestamp_column is None
    assert audit.feature_columns == ["avg_spend_30d", "txn_count_30d"]
    assert audit.entity_count == 2
    assert audit.feature_count == 2
    assert audit.requested == 4
    assert audit.written == 4
    assert audit.skipped_older == 0
    assert audit.skipped_same_timestamp == 0
    assert audit.errors == []
    assert audit.warnings == []
    assert audit.actor == "api-test"


def test_cli_materialization_validation_failure_records_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FEATCAT_USER", "alice")
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    monkeypatch.delenv("FEATCAT_SERVER_URL", raising=False)
    db = _seed_materialization_catalog(
        tmp_path,
        data={
            "customer_id": [1],
            "event_ts": ["2026-05-25T10:00:00Z"],
            "avg_spend_30d": [10.0],
        },
        feature_columns=["avg_spend_30d", "missing_feature"],
    )
    db.close()

    result = runner.invoke(
        app,
        [
            "online",
            "materialize",
            "--source",
            "transactions",
            "--features",
            "missing_feature",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["is_valid"] is False

    db = LocalBackend(str(tmp_path / "catalog.db"))
    try:
        audits = db.list_materialization_audits()
    finally:
        db.close()

    assert len(audits) == 1
    audit = audits[0]
    assert audit.status == "validation_failed"
    assert audit.source_name == "transactions"
    assert audit.feature_columns == ["missing_feature"]
    assert audit.entity_count == 0
    assert audit.feature_count == 1
    assert audit.requested == 0
    assert audit.written == 0
    assert audit.errors == [
        {
            "code": "missing_feature_column",
            "message": "Parquet source is missing feature column: missing_feature",
            "field": "missing_feature",
        }
    ]
    assert audit.actor == "alice"


def test_api_materialization_unexpected_error_records_error_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()

    def raise_boom(*args: object, **kwargs: object) -> MaterializationResult:
        raise RuntimeError("boom")

    monkeypatch.setattr(online, "materialize_latest_from_source", raise_boom)

    try:
        with pytest.raises(RuntimeError, match="boom"):
            online.materialize_online_features(
                OnlineMaterializationRequest(
                    source_name="transactions",
                    feature_columns=["avg_spend_30d"],
                    project="churn",
                    feature_view="transactions",
                    actor="api-test",
                ),
                db=db,
            )
        audits = db.list_materialization_audits()
    finally:
        db.close()

    assert len(audits) == 1
    audit = audits[0]
    assert audit.status == "error"
    assert audit.source_name == "transactions"
    assert audit.project == "churn"
    assert audit.feature_view == "transactions"
    assert audit.feature_columns == ["avg_spend_30d"]
    assert audit.errors == [{"code": "materialization_error", "message": "boom", "field": None}]
    assert audit.actor == "api-test"


def test_materialization_audit_sanitizes_s3_credentials(tmp_path: Path) -> None:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    result = MaterializationResult(
        is_valid=False,
        errors=[
            MaterializationIssue(
                code="missing_s3_config",
                message="S3-compatible parquet paths require configuration",
                field="source_path",
            )
        ],
        source_name="transactions",
        source_path="s3://access:secret@featcat-smoke/materialization/source.parquet",
        project="churn",
        feature_view="transactions",
        entity_key="customer_id",
        event_timestamp_column="event_ts",
        feature_columns=["avg_spend_30d"],
        feature_count=1,
    )

    try:
        record_materialization_audit(db, result=result, actor="api")
        audit = db.list_materialization_audits()[0]
    finally:
        db.close()

    assert audit.source_path == "s3://featcat-smoke/materialization/source.parquet"
    serialized = json.dumps(audit.model_dump(), default=str)
    assert "access" not in serialized
    assert "secret" not in serialized


def test_list_materialization_audits_returns_newest_first(tmp_path: Path) -> None:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    try:
        record_materialization_audit(db, result=_audit_result(written=1), actor="first")
        time.sleep(0.001)
        record_materialization_audit(db, result=_audit_result(written=2), actor="second")

        audits = db.list_materialization_audits()
    finally:
        db.close()

    assert [audit.actor for audit in audits] == ["second", "first"]
    assert [audit.written for audit in audits] == [2, 1]


def test_list_materialization_audits_respects_limit(tmp_path: Path) -> None:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    try:
        for index in range(3):
            record_materialization_audit(db, result=_audit_result(written=index + 1), actor=f"run-{index}")

        audits = db.list_materialization_audits(limit=2)
    finally:
        db.close()

    assert len(audits) == 2


def test_list_materialization_audits_filters_status(tmp_path: Path) -> None:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    try:
        record_materialization_audit(db, result=_audit_result(is_valid=True), actor="success")
        record_materialization_audit(db, result=_audit_result(is_valid=False, written=0), actor="failed")

        audits = db.list_materialization_audits(status="validation_failed")
    finally:
        db.close()

    assert len(audits) == 1
    assert audits[0].status == "validation_failed"
    assert audits[0].actor == "failed"


def test_materialization_history_route_serializes_records_without_testclient(tmp_path: Path) -> None:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    try:
        record_materialization_audit(db, result=_audit_result(), actor="api")

        response = list_materialization_runs(limit=20, status=None, db=db)
    finally:
        db.close()

    assert len(response) == 1
    payload = response[0].model_dump()
    assert payload["status"] == "success"
    assert payload["source_name"] == "transactions"
    assert payload["feature_columns"] == ["avg_spend_30d", "txn_count_30d"]
    assert payload["actor"] == "api"
    assert isinstance(payload["created_at"], str)


def test_materialization_history_route_does_not_expose_s3_credentials(tmp_path: Path) -> None:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    try:
        record_materialization_audit(
            db,
            result=_audit_result(source_path="s3://access:secret@featcat-smoke/materialization/source.parquet"),
            actor="api",
        )

        response = list_materialization_runs(limit=20, status=None, db=db)
    finally:
        db.close()

    serialized = json.dumps([row.model_dump() for row in response], default=str)
    assert "s3://featcat-smoke/materialization/source.parquet" in serialized
    assert "access" not in serialized
    assert "secret" not in serialized
