"""Online store CLI tests."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq
from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.materialization import MaterializationIssue, MaterializationResult
from featcat.catalog.materialization_audit import record_materialization_audit
from featcat.catalog.models import DataSource, Feature
from featcat.catalog.online_store import get_online_features
from featcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
    return path


def _write_parquet(path: Path, data: dict[str, list[Any]]) -> Path:
    pq.write_table(pa.table(data), path)
    return path


def _seed_catalog(tmp_path: Path) -> None:
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
    db.close()


def _seed_materialization_catalog(
    tmp_path: Path,
    *,
    data: dict[str, list[Any]] | None = None,
    feature_columns: list[str] | None = None,
) -> Path:
    parquet_path = _write_parquet(
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
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    source = DataSource(
        name="transactions",
        path=str(parquet_path),
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
    db.close()
    return parquet_path


def _write_row(
    *,
    customer_id: int = 1,
    feature_ref: str = "transactions.avg_spend_30d",
    value: Any = 10.0,
    write_id: str | None = None,
) -> dict[str, Any]:
    row = {
        "entity_key": {"customer_id": customer_id},
        "feature_ref": feature_ref,
        "value": value,
        "value_dtype": "float64",
        "event_timestamp": "2026-05-25T09:00:00Z",
        "created_timestamp": "2026-05-25T09:01:00Z",
    }
    if write_id is not None:
        row["write_id"] = write_id
    return row


def test_online_write_command_writes_rows_and_returns_counts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    monkeypatch.delenv("FEATCAT_SERVER_URL", raising=False)
    _seed_catalog(tmp_path)
    rows_path = _write_jsonl(
        tmp_path / "rows.jsonl",
        [
            _write_row(customer_id=1, value=10.0),
            _write_row(customer_id=2, feature_ref="transactions.txn_count_30d", value=3, write_id="count-2"),
        ],
    )

    result = runner.invoke(
        app,
        [
            "online",
            "write",
            "--input",
            str(rows_path),
            "--project",
            "churn",
            "--feature-view",
            "transactions",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["requested"] == 2
    assert payload["written"] == 2
    assert payload["skipped_older"] == 0
    assert payload["skipped_same_timestamp"] == 0
    assert payload["errors"] == []


def test_online_get_command_returns_ordered_rows(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    monkeypatch.delenv("FEATCAT_SERVER_URL", raising=False)
    _seed_catalog(tmp_path)
    rows_path = _write_jsonl(
        tmp_path / "rows.jsonl",
        [
            _write_row(customer_id=1, value=10.0),
            _write_row(customer_id=2, value=20.0),
        ],
    )
    write_result = runner.invoke(app, ["online", "write", "--input", str(rows_path), "--json"])
    assert write_result.exit_code == 0, write_result.output
    entities_path = _write_jsonl(
        tmp_path / "entities.jsonl",
        [{"customer_id": 2}, {"customer_id": 1}],
    )

    result = runner.invoke(
        app,
        [
            "online",
            "get",
            "--entities",
            str(entities_path),
            "--features",
            "transactions.avg_spend_30d",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert [row["entity_key"] for row in payload["rows"]] == [{"customer_id": 2}, {"customer_id": 1}]
    assert [row["features"]["transactions.avg_spend_30d"] for row in payload["rows"]] == [20.0, 10.0]


def test_online_write_invalid_jsonl_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_SERVER_URL", raising=False)
    bad_path = tmp_path / "bad.jsonl"
    bad_path.write_text('{"entity_key": {"customer_id": 1}\n', encoding="utf-8")

    result = runner.invoke(app, ["online", "write", "--input", str(bad_path), "--json"])

    assert result.exit_code == 1
    assert "Invalid JSONL" in result.output
    assert "bad.jsonl:1" in result.output


def test_online_write_missing_input_file_exits_nonzero(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_SERVER_URL", raising=False)

    result = runner.invoke(app, ["online", "write", "--input", str(tmp_path / "missing.jsonl"), "--json"])

    assert result.exit_code == 1
    assert "Input file not found" in result.output


def test_online_get_preserves_null_feature_value_as_found(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    monkeypatch.delenv("FEATCAT_SERVER_URL", raising=False)
    _seed_catalog(tmp_path)
    rows_path = _write_jsonl(tmp_path / "rows.jsonl", [_write_row(customer_id=1, value=None)])
    write_result = runner.invoke(app, ["online", "write", "--input", str(rows_path), "--json"])
    assert write_result.exit_code == 0, write_result.output
    entities_path = _write_jsonl(tmp_path / "entities.jsonl", [{"customer_id": 1}])

    result = runner.invoke(
        app,
        [
            "online",
            "get",
            "--entities",
            str(entities_path),
            "--features",
            "transactions.avg_spend_30d",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    row = payload["rows"][0]
    assert row["features"]["transactions.avg_spend_30d"] is None
    assert row["metadata"]["transactions.avg_spend_30d"]["found"] is True
    assert row["metadata"]["transactions.avg_spend_30d"]["event_timestamp"] == "2026-05-25T09:00:00Z"


def test_online_materialize_command_succeeds_for_registered_local_parquet(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    monkeypatch.delenv("FEATCAT_SERVER_URL", raising=False)
    _seed_materialization_catalog(tmp_path)

    result = runner.invoke(
        app,
        [
            "online",
            "materialize",
            "--source",
            "transactions",
            "--features",
            "avg_spend_30d,txn_count_30d",
            "--project",
            "churn",
            "--feature-view",
            "transactions",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["is_valid"] is True
    assert payload["source_name"] == "transactions"
    assert payload["project"] == "churn"
    assert payload["feature_view"] == "transactions"
    assert payload["entity_count"] == 2
    assert payload["feature_count"] == 2
    assert payload["requested"] == 4
    assert payload["written"] == 4
    assert payload["errors"] == []


def test_online_materialize_command_writes_values_readable_from_online_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    monkeypatch.delenv("FEATCAT_SERVER_URL", raising=False)
    _seed_materialization_catalog(tmp_path)

    result = runner.invoke(
        app,
        [
            "online",
            "materialize",
            "--source",
            "transactions",
            "--features",
            "avg_spend_30d,txn_count_30d",
            "--project",
            "churn",
            "--feature-view",
            "transactions",
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output

    db = LocalBackend(str(tmp_path / "catalog.db"))
    try:
        db.init_db()
        read_result = get_online_features(
            db,
            entity_keys=[{"customer_id": 1}, {"customer_id": 2}],
            feature_refs=["transactions.avg_spend_30d", "transactions.txn_count_30d"],
            project="churn",
            feature_view="transactions",
        )
    finally:
        db.close()

    assert read_result.rows[0].features == {
        "transactions.avg_spend_30d": 20.0,
        "transactions.txn_count_30d": 2,
    }
    assert read_result.rows[1].features == {
        "transactions.avg_spend_30d": 30.0,
        "transactions.txn_count_30d": 3,
    }


def test_online_materialize_missing_feature_returns_structured_json_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    monkeypatch.delenv("FEATCAT_SERVER_URL", raising=False)
    _seed_materialization_catalog(
        tmp_path,
        data={
            "customer_id": [1],
            "event_ts": ["2026-05-25T10:00:00Z"],
            "avg_spend_30d": [10.0],
        },
        feature_columns=["avg_spend_30d", "missing_feature"],
    )

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
    assert payload["requested"] == 0
    assert payload["errors"] == [
        {
            "code": "missing_feature_column",
            "message": "Parquet source is missing feature column: missing_feature",
            "field": "missing_feature",
        }
    ]


def test_online_materialize_missing_source_returns_structured_json_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    monkeypatch.delenv("FEATCAT_SERVER_URL", raising=False)

    result = runner.invoke(
        app,
        [
            "online",
            "materialize",
            "--source",
            "missing",
            "--features",
            "avg_spend_30d",
            "--json",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.output)
    assert payload["is_valid"] is False
    assert payload["source_name"] == "missing"
    assert payload["feature_columns"] == ["avg_spend_30d"]
    assert payload["errors"] == [
        {
            "code": "source_not_found",
            "message": "DataSource is not registered: missing",
            "field": "source_name",
        }
    ]


def test_online_materializations_list_json_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    try:
        record_materialization_audit(
            db,
            result=MaterializationResult(
                is_valid=False,
                errors=[
                    MaterializationIssue(
                        code="missing_feature_column",
                        message="Parquet source is missing feature column: missing_feature",
                        field="missing_feature",
                    )
                ],
                source_name="transactions",
                source_path="s3://access:secret@featcat-smoke/materialization/source.parquet",
                project="churn",
                feature_view="transactions",
                entity_key="customer_id",
                event_timestamp_column="event_ts",
                feature_columns=["missing_feature"],
                feature_count=1,
            ),
            actor="cli-test",
        )
    finally:
        db.close()

    result = runner.invoke(
        app,
        [
            "online",
            "materializations",
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
    assert payload[0]["source_name"] == "transactions"
    assert payload[0]["feature_columns"] == ["missing_feature"]
    assert payload[0]["actor"] == "cli-test"
    serialized = result.output
    assert "s3://featcat-smoke/materialization/source.parquet" in serialized
    assert "access" not in serialized
    assert "secret" not in serialized


def test_online_materialization_schedule_add_creates_interval_schedule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    monkeypatch.setenv("FEATCAT_USER", "scheduler-test")

    result = runner.invoke(
        app,
        [
            "online",
            "materializations",
            "schedules",
            "add",
            "--name",
            "hourly-transactions",
            "--source",
            "transactions",
            "--features",
            "avg_spend_30d,txn_count_30d",
            "--interval-seconds",
            "3600",
            "--project",
            "churn",
            "--feature-view",
            "transactions",
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["name"] == "hourly-transactions"
    assert payload["source_name"] == "transactions"
    assert payload["feature_columns"] == ["avg_spend_30d", "txn_count_30d"]
    assert payload["schedule_type"] == "interval"
    assert payload["interval_seconds"] == 3600
    assert payload["project"] == "churn"
    assert payload["feature_view"] == "transactions"
    assert payload["enabled"] is True
    assert payload["actor"] == "scheduler-test"


def test_online_materialization_schedules_list_json_shows_created_schedule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    try:
        db.create_materialization_schedule(
            name="hourly-transactions",
            source_name="transactions",
            feature_columns=["avg_spend_30d"],
            interval_seconds=3600,
        )
    finally:
        db.close()

    result = runner.invoke(app, ["online", "materializations", "schedules", "list", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert len(payload) == 1
    assert payload[0]["name"] == "hourly-transactions"
    assert payload[0]["source_name"] == "transactions"
    assert payload[0]["feature_columns"] == ["avg_spend_30d"]


def test_online_materialization_schedule_disable_prevents_run_once_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    _seed_materialization_catalog(tmp_path)
    db = LocalBackend(str(tmp_path / "catalog.db"))
    now = datetime(2000, 1, 1, tzinfo=timezone.utc)
    try:
        schedule = db.create_materialization_schedule(
            name="hourly-transactions",
            source_name="transactions",
            feature_columns=["avg_spend_30d"],
            interval_seconds=3600,
            project="churn",
            feature_view="transactions",
            next_run_at=now - timedelta(seconds=1),
            now=now - timedelta(hours=1),
        )
    finally:
        db.close()

    disable = runner.invoke(app, ["online", "materializations", "schedules", "disable", "hourly-transactions"])
    run = runner.invoke(app, ["online", "materializations", "run-once", "--runner-id", "cli-test", "--json"])

    assert disable.exit_code == 0, disable.output
    assert run.exit_code == 0, run.output
    payload = json.loads(run.output)
    assert payload["claimed"] == 0

    db = LocalBackend(str(tmp_path / "catalog.db"))
    try:
        stored = db.get_materialization_schedule(schedule.id)
        audits = db.list_materialization_audits()
    finally:
        db.close()

    assert stored is not None
    assert stored.enabled is False
    assert audits == []


def test_online_materialization_schedule_enable_reallows_claim(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    _seed_materialization_catalog(tmp_path)
    db = LocalBackend(str(tmp_path / "catalog.db"))
    now = datetime(2000, 1, 1, tzinfo=timezone.utc)
    try:
        db.create_materialization_schedule(
            name="hourly-transactions",
            source_name="transactions",
            feature_columns=["avg_spend_30d"],
            interval_seconds=3600,
            project="churn",
            feature_view="transactions",
            enabled=False,
            next_run_at=now - timedelta(seconds=1),
            now=now - timedelta(hours=1),
        )
    finally:
        db.close()

    enable = runner.invoke(app, ["online", "materializations", "schedules", "enable", "hourly-transactions"])
    run = runner.invoke(app, ["online", "materializations", "run-once", "--runner-id", "cli-test", "--json"])

    assert enable.exit_code == 0, enable.output
    assert run.exit_code == 0, run.output
    payload = json.loads(run.output)
    assert payload["claimed"] == 1
    assert payload["runs"][0]["status"] == "success"


def test_online_materializations_run_once_executes_due_schedule_and_writes_audit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    _seed_materialization_catalog(tmp_path)
    db = LocalBackend(str(tmp_path / "catalog.db"))
    now = datetime(2000, 1, 1, tzinfo=timezone.utc)
    try:
        schedule = db.create_materialization_schedule(
            name="hourly-transactions",
            source_name="transactions",
            feature_columns=["avg_spend_30d"],
            interval_seconds=3600,
            project="churn",
            feature_view="transactions",
            next_run_at=now - timedelta(seconds=1),
            now=now - timedelta(hours=1),
        )
    finally:
        db.close()

    result = runner.invoke(app, ["online", "materializations", "run-once", "--runner-id", "cli-test", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["runner_id"] == "cli-test"
    assert payload["claimed"] == 1
    assert payload["runs"][0]["schedule_id"] == schedule.id
    assert payload["runs"][0]["status"] == "success"

    db = LocalBackend(str(tmp_path / "catalog.db"))
    try:
        audits = db.list_materialization_audits()
        online = get_online_features(
            db,
            entity_keys=[{"customer_id": 1}],
            feature_refs=["transactions.avg_spend_30d"],
            project="churn",
            feature_view="transactions",
        )
    finally:
        db.close()

    assert audits[0].schedule_id == schedule.id
    assert audits[0].status == "success"
    assert online.rows[0].features["transactions.avg_spend_30d"] == 20.0


def test_online_materializations_run_once_does_not_execute_non_due_schedule(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)
    _seed_materialization_catalog(tmp_path)
    db = LocalBackend(str(tmp_path / "catalog.db"))
    try:
        db.create_materialization_schedule(
            name="future-transactions",
            source_name="transactions",
            feature_columns=["avg_spend_30d"],
            interval_seconds=3600,
            project="churn",
            feature_view="transactions",
            next_run_at=datetime.now(timezone.utc) + timedelta(hours=1),
        )
    finally:
        db.close()

    result = runner.invoke(app, ["online", "materializations", "run-once", "--runner-id", "cli-test", "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["claimed"] == 0


def test_online_materialization_schedule_add_invalid_feature_list_exits_nonzero(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("FEATCAT_CATALOG_DB_PATH", raising=False)

    result = runner.invoke(
        app,
        [
            "online",
            "materializations",
            "schedules",
            "add",
            "--name",
            "bad",
            "--source",
            "transactions",
            "--features",
            ",,",
            "--interval-seconds",
            "3600",
            "--json",
        ],
    )

    assert result.exit_code == 1
    assert "No feature columns provided" in result.output
