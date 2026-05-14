"""Tests for doctor, stats, export, and cache CLI commands."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from typer.testing import CliRunner

from featcat.cli import app

runner = CliRunner()


@pytest.fixture()
def catalog_env(tmp_path: Path, sample_parquet: Path, monkeypatch):
    """Set up a working catalog environment."""
    monkeypatch.chdir(tmp_path)
    runner.invoke(app, ["init"])
    runner.invoke(app, ["source", "add", "ds", str(sample_parquet)])
    runner.invoke(app, ["source", "scan", "ds"])
    return tmp_path


class TestDoctor:
    """`featcat doctor` is a Typer sub-app since the diagnostics refactor.

    No subcommand runs all groups; subcommands target one group. Exit code
    is 1 if any check returns FAIL — fresh catalogs typically have stale-drift
    FAILs, so these tests don't assert exit_code == 0 for the bare invocation.
    """

    def test_bare_doctor_emits_groups(self, catalog_env: Path) -> None:
        result = runner.invoke(app, ["doctor"])
        # Crash-free (exit 2 = doctor itself crashed; anything else is fine).
        assert result.exit_code != 2, result.output
        assert "Python" in result.output
        # Each group should render even on a fresh catalog.
        for group_label in ("Db", "Llm", "Data", "Network", "Deploy"):
            assert group_label in result.output

    def test_doctor_db_subcommand_only_runs_db(self, catalog_env: Path) -> None:
        result = runner.invoke(app, ["doctor", "db"])
        assert result.exit_code != 2, result.output
        assert "Db" in result.output
        # Other groups should NOT appear when a subcommand is invoked.
        assert "Llm" not in result.output
        assert "Network" not in result.output

    def test_doctor_json_envelope_is_parseable(self, catalog_env: Path) -> None:
        result = runner.invoke(app, ["doctor", "--json"])
        # Strip any header line from the pre-check (we still print Python version line
        # before the JSON body only in human mode — so JSON mode body should parse cleanly).
        payload = json.loads(result.stdout)
        assert payload["version"] == 1
        assert set(payload["summary"]) == {"pass", "warn", "fail", "skip"}
        assert set(payload["groups"]) == {"deploy", "db", "llm", "network", "data"}
        # Each group has a list of checks.
        for group_name, group in payload["groups"].items():
            assert group["group"] == group_name
            assert isinstance(group["checks"], list)

    def test_doctor_db_json_only_runs_db(self, catalog_env: Path) -> None:
        result = runner.invoke(app, ["doctor", "db", "--json"])
        payload = json.loads(result.stdout)
        # Single-group invocations emit just that group, not an empty shell for every group.
        assert set(payload["groups"]) == {"db"}
        assert payload["groups"]["db"]["checks"]


class TestStats:
    def test_stats_runs(self, catalog_env):
        result = runner.invoke(app, ["stats"])
        assert result.exit_code == 0
        assert "Features" in result.output
        assert "Sources" in result.output
        assert "Doc coverage" in result.output


class TestExport:
    def test_export_json_stdout(self, catalog_env):
        result = runner.invoke(app, ["export", "--format", "json"])
        assert result.exit_code == 0
        assert "ds.user_id" in result.output

    def test_export_csv_stdout(self, catalog_env):
        result = runner.invoke(app, ["export", "--format", "csv"])
        assert result.exit_code == 0
        assert "name,column_name" in result.output

    def test_export_markdown_stdout(self, catalog_env):
        result = runner.invoke(app, ["export", "--format", "markdown"])
        assert result.exit_code == 0
        assert "| ds." in result.output

    def test_export_to_file(self, catalog_env):
        result = runner.invoke(app, ["export", "--format", "json", "-o", "out.json"])
        assert result.exit_code == 0
        assert Path("out.json").exists()


class TestCacheCommands:
    def test_cache_stats(self, catalog_env):
        result = runner.invoke(app, ["cache", "stats"])
        assert result.exit_code == 0
        assert "Total entries" in result.output

    def test_cache_clear(self, catalog_env):
        result = runner.invoke(app, ["cache", "clear"])
        assert result.exit_code == 0
        assert "Cleared" in result.output
