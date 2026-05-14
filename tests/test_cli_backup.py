"""End-to-end CLI tests for `featcat backup`, `featcat backup list`, and `featcat restore`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path


def _seed(db_path: str) -> None:
    db = LocalBackend(db_path)
    db.init_db()
    src = db.add_source(DataSource(name="src", path="/data/src.parquet"))
    db.upsert_feature(Feature(name="src.col", data_source_id=src.id, column_name="col", dtype="float64"))
    db.close()


def test_backup_creates_tarball(monkeypatch, tmp_path: Path) -> None:
    db_path = str(tmp_path / "catalog.db")
    _seed(db_path)
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)

    archive = tmp_path / "backup.tar.gz"
    runner = CliRunner()
    result = runner.invoke(app, ["backup", "--output", str(archive)])
    assert result.exit_code == 0, result.output
    assert archive.exists()
    assert archive.stat().st_size > 0


def test_backup_restore_round_trip(monkeypatch, tmp_path: Path) -> None:
    src_path = str(tmp_path / "src.db")
    dst_path = str(tmp_path / "dst.db")
    _seed(src_path)
    LocalBackend(dst_path).init_db()

    archive = tmp_path / "backup.tar.gz"

    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", src_path)
    runner = CliRunner()
    result = runner.invoke(app, ["backup", "--output", str(archive)])
    assert result.exit_code == 0, result.output

    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", dst_path)
    result = runner.invoke(app, ["restore", "--input", str(archive), "--force", "--yes"])
    assert result.exit_code == 0, result.output

    db = LocalBackend(dst_path)
    try:
        assert db.get_feature_by_name("src.col") is not None
    finally:
        db.close()


def test_backup_list_shows_archives(monkeypatch, tmp_path: Path) -> None:
    db_path = str(tmp_path / "catalog.db")
    _seed(db_path)
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)

    out_dir = tmp_path / "out"
    out_dir.mkdir()
    runner = CliRunner()
    runner.invoke(app, ["backup", "--output", str(out_dir / "a.tar.gz")])
    runner.invoke(app, ["backup", "--output", str(out_dir / "b.tar.gz")])

    result = runner.invoke(app, ["backup", "list", "--dir", str(out_dir)])
    assert result.exit_code == 0
    assert "a.tar.gz" in result.output
    assert "b.tar.gz" in result.output


def test_restore_refuses_nonempty_target_without_force(monkeypatch, tmp_path: Path) -> None:
    src_path = str(tmp_path / "src.db")
    dst_path = str(tmp_path / "dst.db")
    _seed(src_path)
    _seed(dst_path)  # Make dst non-empty.

    archive = tmp_path / "backup.tar.gz"
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", src_path)
    runner = CliRunner()
    runner.invoke(app, ["backup", "--output", str(archive)])

    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", dst_path)
    result = runner.invoke(app, ["restore", "--input", str(archive)], input="n\n")
    assert result.exit_code == 0
    assert "Aborted" in result.output
