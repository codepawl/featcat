"""Tests for dataset build API schemas and CLI command."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq
from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource
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
            "customer_id": pa.array([2, 1]),
            "event_ts": pa.array(["2026-01-05", "2026-01-03"]),
            "label": pa.array([0, 1]),
        },
    )


def _source_path(tmp_path: Path) -> Path:
    return _write_parquet(
        tmp_path / "features.parquet",
        {
            "customer_id": pa.array([1, 1, 2]),
            "feature_ts": pa.array(["2026-01-01", "2026-01-04", "2026-01-02"]),
            "avg_spend_30d": pa.array([10.0, 40.0, 20.0]),
            "txn_count_30d": pa.array([1, 4, 2]),
        },
    )


def test_cli_dataset_build_with_local_parquet_succeeds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    entities = _entity_path(tmp_path)
    source = _source_path(tmp_path)
    output = tmp_path / "training.parquet"

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
            "avg_spend_30d,txn_count_30d",
            "--output",
            str(output),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["is_valid"] is True
    assert payload["row_count"] == 2
    assert payload["feature_count"] == 2
    assert payload["output_path"] == str(output)
    assert output.exists()
    assert pq.read_table(output).to_pydict()["avg_spend_30d"] == [20.0, 10.0]


def test_cli_dataset_build_missing_required_column_returns_structured_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.chdir(tmp_path)
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
    assert {error["code"] for error in payload["errors"]} == {"source_dataframe_missing_entity_key"}
    assert payload["output_path"] is None
    assert not output.exists()


def test_dataset_build_route_schema_serializes_without_testclient(tmp_path: Path) -> None:
    entities = _entity_path(tmp_path)
    source = _source_path(tmp_path)
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    db.add_source(
        DataSource(
            name="features",
            path=str(source),
            entity_key="customer_id",
            event_timestamp_column="feature_ts",
        )
    )

    try:
        response = build_dataset(
            DatasetBuildRequest(
                entity_df_path=str(entities),
                source_name="features",
                entity_timestamp_column="event_ts",
                feature_columns=["avg_spend_30d"],
            ),
            db=db,
        )
    finally:
        db.close()

    payload = response.model_dump()
    assert payload["is_valid"] is True
    assert payload["source_path"] == str(source)
    assert payload["entity_key"] == "customer_id"
    assert payload["source_event_timestamp_column"] == "feature_ts"
    assert payload["row_count"] == 2
    assert "dataframe" not in payload
