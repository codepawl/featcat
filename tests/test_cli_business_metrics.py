"""Tests for `featcat metric ...` commands."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path


runner = CliRunner()


def _seed(tmp_path: Path) -> None:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    source = DataSource(name="network_quality_customer_7d", path=str(tmp_path / "network.parquet"))
    db.add_source(source)
    db.upsert_feature(
        Feature(
            name="network_quality_customer_7d.bad_signal_days_7d",
            data_source_id=source.id,
            column_name="bad_signal_days_7d",
            dtype="int64",
        )
    )
    db.close()


def test_metric_upsert_list_and_info(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    _seed(tmp_path)

    result = runner.invoke(
        app,
        [
            "metric",
            "upsert",
            "network_quality.bad_signal_days_7d",
            "--business-metric-name",
            "bad_signal_days_7d",
            "--business-definition",
            "So ngay tin hieu kem trong 7 ngay gan nhat",
            "--metric-domain",
            "network_quality",
            "--lifecycle-stage",
            "consume",
            "--metric-group",
            "signal",
            "--metric-level",
            "customer",
            "--entity-grain",
            "customer_id",
            "--mapped-feature",
            "network_quality_customer_7d.bad_signal_days_7d",
            "--owner",
            "network-data",
            "--allowed-use-case",
            "churn",
        ],
    )
    assert result.exit_code == 0, result.output

    result = runner.invoke(
        app,
        ["metric", "list", "--metric-domain", "network_quality", "--json"],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload[0]["name"] == "network_quality.bad_signal_days_7d"

    result = runner.invoke(app, ["metric", "info", "network_quality.bad_signal_days_7d"])
    assert result.exit_code == 0, result.output
    assert "network_quality" in result.output
    assert "bad_signal_days_7d" in result.output
