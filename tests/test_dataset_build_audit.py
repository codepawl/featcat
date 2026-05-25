"""Dataset build audit tests without FastAPI TestClient."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq
from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.cli import app
from featcat.server.routes.datasets import DatasetBuildRequest, build_dataset

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
