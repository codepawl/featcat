"""Tests for doctor, stats, export, and cache CLI commands."""

from __future__ import annotations

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
    def test_doctor_runs(self, catalog_env):
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "Python" in result.output
        assert "features registered" in result.output

    def test_doctor_no_db(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["doctor"])
        assert result.exit_code == 0
        assert "catalog" in result.output.lower()


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
