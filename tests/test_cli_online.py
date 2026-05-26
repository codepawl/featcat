"""Online store CLI tests."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any

from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.write_text("\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8")
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
