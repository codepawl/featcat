"""Dataset build audit tests without FastAPI TestClient."""

from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq
from typer.testing import CliRunner

from featcat.catalog.dataset_audit import record_dataset_build_audit
from featcat.catalog.local import LocalBackend
from featcat.catalog.training_dataset import TrainingDatasetBuildResult, TrainingDatasetValidationIssue
from featcat.cli import app
from featcat.server.routes.datasets import DatasetBuildRequest, build_dataset, list_dataset_builds

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


def _write_parquet(path: Path, data: dict) -> Path:
    pq.write_table(pa.table(data), path)
    return path


def _entity_path(tmp_path: Path) -> Path:
    return _write_parquet(
        tmp_path / "labels.parquet",
        {
            "customer_id": pa.array([1, 2]),
            "event_ts": pa.array(["2026-01-03", "2026-01-05"]),
        },
    )


def _source_path(tmp_path: Path) -> Path:
    return _write_parquet(
        tmp_path / "features.parquet",
        {
            "customer_id": pa.array([1, 2]),
            "feature_ts": pa.array(["2026-01-01", "2026-01-04"]),
            "avg_spend_30d": pa.array([10.0, 20.0]),
            "txn_count_30d": pa.array([1, 2]),
        },
    )


def test_api_dataset_build_records_success_audit(tmp_path: Path) -> None:
    entities = _entity_path(tmp_path)
    source = _source_path(tmp_path)
    output = tmp_path / "training.parquet"
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()

    try:
        response = build_dataset(
            DatasetBuildRequest(
                entity_df_path=str(entities),
                source_path=str(source),
                entity_key="customer_id",
                entity_timestamp_column="event_ts",
                source_event_timestamp_column="feature_ts",
                feature_columns=["avg_spend_30d", "txn_count_30d"],
                output_path=str(output),
            ),
            db=db,
        )
        audits = db.list_dataset_build_audits()
    finally:
        db.close()

    assert response.is_valid is True
    assert len(audits) == 1
    audit = audits[0]
    assert audit.status == "success"
    assert audit.entity_df_path == str(entities)
    assert audit.source_path == str(source)
    assert audit.output_path == str(output)
    assert audit.entity_key == "customer_id"
    assert audit.entity_timestamp_column == "event_ts"
    assert audit.source_event_timestamp_column == "feature_ts"
    assert audit.feature_columns == ["avg_spend_30d", "txn_count_30d"]
    assert audit.row_count == 2
    assert audit.feature_count == 2
    assert audit.unresolved_row_count == 0
    assert audit.missing_feature_value_count == 0
    assert audit.errors == []
    assert audit.warnings == []
    assert audit.actor == "api"


def test_cli_dataset_build_validation_failure_records_audit(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FEATCAT_USER", "alice")
    entities = _entity_path(tmp_path)
    source = _write_parquet(
        tmp_path / "bad_features.parquet",
        {
            "feature_ts": pa.array(["2026-01-01"]),
            "avg_spend_30d": pa.array([10.0]),
        },
    )
    output = tmp_path / "should_not_write.parquet"

    result = runner.invoke(
        app,
        [
            "dataset",
            "build",
            "--entities",
            str(entities),
            "--source",
            str(source),
            "--entity-key",
            "customer_id",
            "--entity-timestamp",
            "event_ts",
            "--source-timestamp",
            "feature_ts",
            "--features",
            "avg_spend_30d",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["is_valid"] is False

    db = LocalBackend(str(tmp_path / "catalog.db"))
    try:
        audits = db.list_dataset_build_audits()
    finally:
        db.close()

    assert len(audits) == 1
    audit = audits[0]
    assert audit.status == "validation_failed"
    assert audit.entity_df_path == str(entities)
    assert audit.source_path == str(source)
    assert audit.output_path == str(output)
    assert audit.feature_columns == ["avg_spend_30d"]
    assert audit.row_count == 0
    assert audit.feature_count == 1
    assert {error["code"] for error in audit.errors} == {"source_dataframe_missing_entity_key"}
    assert audit.actor == "alice"


def test_dataset_build_audit_sanitizes_s3_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    entities = "s3://access:secret@featcat-smoke/training-dataset/entities.parquet"
    source = _source_path(tmp_path)
    output = "s3://access:secret@featcat-smoke/training-dataset/output.parquet"

    result = runner.invoke(
        app,
        [
            "dataset",
            "build",
            "--entities",
            entities,
            "--source",
            str(source),
            "--entity-key",
            "customer_id",
            "--entity-timestamp",
            "event_ts",
            "--source-timestamp",
            "feature_ts",
            "--features",
            "avg_spend_30d",
            "--output",
            output,
            "--json",
        ],
    )

    assert result.exit_code == 1

    db = LocalBackend(str(tmp_path / "catalog.db"))
    try:
        audit = db.list_dataset_build_audits()[0]
    finally:
        db.close()

    assert audit.entity_df_path == "s3://featcat-smoke/training-dataset/entities.parquet"
    assert audit.output_path == "s3://featcat-smoke/training-dataset/output.parquet"
    serialized = json.dumps(audit.model_dump(), default=str)
    assert "access" not in serialized
    assert "secret" not in serialized


def _audit_result(
    *,
    is_valid: bool = True,
    row_count: int = 2,
    output_path: str | None = "training.parquet",
) -> TrainingDatasetBuildResult:
    return TrainingDatasetBuildResult(
        is_valid=is_valid,
        errors=[]
        if is_valid
        else [
            TrainingDatasetValidationIssue(
                code="source_dataframe_missing_entity_key",
                message="Source dataframe is missing entity key column: customer_id",
                field="entity_key",
            )
        ],
        entity_df_path="labels.parquet",
        source_path="features.parquet",
        entity_key="customer_id",
        entity_timestamp_column="event_ts",
        source_event_timestamp_column="feature_ts",
        feature_columns=["avg_spend_30d", "txn_count_30d"],
        output_path=output_path,
        row_count=row_count,
        feature_count=2,
        unresolved_row_count=0,
        missing_feature_value_count=0,
    )


def test_list_dataset_build_audits_returns_newest_first(tmp_path: Path) -> None:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    try:
        record_dataset_build_audit(db, result=_audit_result(row_count=1), source_name=None, actor="first")
        time.sleep(0.001)
        record_dataset_build_audit(db, result=_audit_result(row_count=2), source_name=None, actor="second")

        audits = db.list_dataset_build_audits()
    finally:
        db.close()

    assert [audit.actor for audit in audits] == ["second", "first"]
    assert [audit.row_count for audit in audits] == [2, 1]


def test_list_dataset_build_audits_respects_limit(tmp_path: Path) -> None:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    try:
        for index in range(3):
            record_dataset_build_audit(
                db,
                result=_audit_result(row_count=index + 1),
                source_name=None,
                actor=f"run-{index}",
            )

        audits = db.list_dataset_build_audits(limit=2)
    finally:
        db.close()

    assert len(audits) == 2


def test_list_dataset_build_audits_filters_status(tmp_path: Path) -> None:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    try:
        record_dataset_build_audit(db, result=_audit_result(is_valid=True), source_name=None, actor="success")
        record_dataset_build_audit(
            db,
            result=_audit_result(is_valid=False, output_path=None),
            source_name=None,
            actor="failed",
        )

        audits = db.list_dataset_build_audits(status="validation_failed")
    finally:
        db.close()

    assert len(audits) == 1
    assert audits[0].status == "validation_failed"
    assert audits[0].actor == "failed"


def test_dataset_builds_route_schema_serializes_without_testclient(tmp_path: Path) -> None:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    try:
        record_dataset_build_audit(db, result=_audit_result(), source_name=None, actor="api")

        response = list_dataset_builds(limit=20, status=None, db=db)
    finally:
        db.close()

    assert len(response) == 1
    payload = response[0].model_dump()
    assert payload["status"] == "success"
    assert payload["entity_df_path"] == "labels.parquet"
    assert payload["feature_columns"] == ["avg_spend_30d", "txn_count_30d"]
    assert payload["actor"] == "api"
    assert isinstance(payload["created_at"], str)


def test_cli_dataset_builds_list_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    try:
        record_dataset_build_audit(db, result=_audit_result(is_valid=True), source_name=None, actor="success")
        record_dataset_build_audit(
            db,
            result=_audit_result(is_valid=False, output_path=None),
            source_name=None,
            actor="failed",
        )
    finally:
        db.close()

    result = runner.invoke(
        app,
        [
            "dataset",
            "builds",
            "list",
            "--limit",
            "20",
            "--status",
            "validation_failed",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload) == 1
    assert payload[0]["status"] == "validation_failed"
    assert payload[0]["actor"] == "failed"


def test_dataset_builds_list_does_not_expose_s3_credentials(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    entities = "s3://access:secret@featcat-smoke/training-dataset/entities.parquet"
    source = _source_path(tmp_path)

    result = runner.invoke(
        app,
        [
            "dataset",
            "build",
            "--entities",
            entities,
            "--source",
            str(source),
            "--entity-key",
            "customer_id",
            "--entity-timestamp",
            "event_ts",
            "--source-timestamp",
            "feature_ts",
            "--features",
            "avg_spend_30d",
            "--json",
        ],
    )
    assert result.exit_code == 1

    list_result = runner.invoke(app, ["dataset", "builds", "list", "--json"])

    assert list_result.exit_code == 0, list_result.output
    serialized = list_result.output
    assert "s3://featcat-smoke/training-dataset/entities.parquet" in serialized
    assert "access" not in serialized
    assert "secret" not in serialized
