"""Tests for bulk inventory scanning (Feature 1)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path
from typer.testing import CliRunner

from featcat.catalog.db import CatalogDB
from featcat.catalog.scanner import discover_parquet_files
from featcat.cli import app

runner = CliRunner()


class TestDiscoverParquetFiles:
    def test_flat(self, sample_parquet_dir: Path) -> None:
        files = discover_parquet_files(str(sample_parquet_dir), recursive=False)
        names = [f.name for f in files]
        assert "items.parquet" in names
        assert "users.parquet" in names
        # Nested file should NOT appear in flat mode
        assert "events.parquet" not in names

    def test_recursive(self, sample_parquet_dir: Path) -> None:
        files = discover_parquet_files(str(sample_parquet_dir), recursive=True)
        names = [f.name for f in files]
        assert "items.parquet" in names
        assert "users.parquet" in names
        assert "events.parquet" in names

    def test_not_a_directory(self, tmp_path: Path) -> None:
        f = tmp_path / "file.txt"
        f.write_text("hello")
        with pytest.raises(NotADirectoryError):
            discover_parquet_files(str(f))

    def test_empty_directory(self, tmp_path: Path) -> None:
        d = tmp_path / "empty"
        d.mkdir()
        files = discover_parquet_files(str(d))
        assert files == []


class TestScanBulkCLI:
    def test_registers_sources_and_features(self, tmp_path: Path, sample_parquet_dir: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        result = runner.invoke(app, ["scan-bulk", str(sample_parquet_dir)])
        assert result.exit_code == 0
        assert "registered" in result.output.lower() or "OK" in result.output

        # Verify DB has sources and features
        db = CatalogDB(str(tmp_path / "catalog.db"))
        db.init_db()
        sources = db.list_sources()
        features = db.list_features()
        db.close()
        assert len(sources) == 2  # flat: users, items
        assert len(features) >= 4  # users has 2 cols, items has 2 cols

    def test_recursive(self, tmp_path: Path, sample_parquet_dir: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        result = runner.invoke(app, ["scan-bulk", str(sample_parquet_dir), "--recursive"])
        assert result.exit_code == 0

        db = CatalogDB(str(tmp_path / "catalog.db"))
        db.init_db()
        sources = db.list_sources()
        db.close()
        assert len(sources) == 3  # users, items, events

    def test_dry_run(self, tmp_path: Path, sample_parquet_dir: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        result = runner.invoke(app, ["scan-bulk", str(sample_parquet_dir), "--dry-run"])
        assert result.exit_code == 0
        assert "would register" in result.output.lower() or "Dry run" in result.output

        # DB should be empty
        db = CatalogDB(str(tmp_path / "catalog.db"))
        db.init_db()
        sources = db.list_sources()
        db.close()
        assert len(sources) == 0

    def test_idempotent(self, tmp_path: Path, sample_parquet_dir: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["scan-bulk", str(sample_parquet_dir)])
        result = runner.invoke(app, ["scan-bulk", str(sample_parquet_dir)])
        assert result.exit_code == 0
        assert "skipped" in result.output.lower() or "Skipped" in result.output

    def test_with_tags_and_owner(self, tmp_path: Path, sample_parquet_dir: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["scan-bulk", str(sample_parquet_dir), "--owner", "alice", "--tag", "test"])

        db = CatalogDB(str(tmp_path / "catalog.db"))
        db.init_db()
        features = db.list_features()
        db.close()
        for f in features:
            assert f.owner == "alice"
            assert "test" in f.tags
