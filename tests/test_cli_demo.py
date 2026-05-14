"""End-to-end CLI tests for `featcat demo seed` and `featcat demo clear`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path


def _bootstrap(tmp_path: Path) -> str:
    """Init an empty catalog at tmp_path and return its absolute file path."""
    db_path = str(tmp_path / "catalog.db")
    db = LocalBackend(db_path)
    db.init_db()
    db.close()
    return db_path


def test_demo_seed_populates_catalog(monkeypatch, tmp_path: Path) -> None:
    db_path = _bootstrap(tmp_path)
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)

    runner = CliRunner()
    result = runner.invoke(app, ["demo", "seed"])
    assert result.exit_code == 0, result.output
    assert "Seeded demo catalog" in result.output

    db = LocalBackend(db_path)
    try:
        demo_features = db.list_features(tag="demo")
        assert len(demo_features) > 0
    finally:
        db.close()


def test_demo_clear_removes_demo_data(monkeypatch, tmp_path: Path) -> None:
    db_path = _bootstrap(tmp_path)
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)

    runner = CliRunner()
    seed_result = runner.invoke(app, ["demo", "seed"])
    assert seed_result.exit_code == 0
    clear_result = runner.invoke(app, ["demo", "clear", "--yes"])
    assert clear_result.exit_code == 0, clear_result.output
    assert "Cleared demo data" in clear_result.output

    db = LocalBackend(db_path)
    try:
        assert db.list_features(tag="demo") == []
    finally:
        db.close()


def test_demo_clear_requires_confirmation(monkeypatch, tmp_path: Path) -> None:
    db_path = _bootstrap(tmp_path)
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)

    runner = CliRunner()
    runner.invoke(app, ["demo", "seed"])
    # Answering "n" should abort without deleting anything.
    result = runner.invoke(app, ["demo", "clear"], input="n\n")
    assert result.exit_code == 0
    assert "Aborted" in result.output

    db = LocalBackend(db_path)
    try:
        assert db.list_features(tag="demo") != []
    finally:
        db.close()


def test_demo_seed_with_custom_fixture(monkeypatch, tmp_path: Path) -> None:
    db_path = _bootstrap(tmp_path)
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)

    custom = tmp_path / "custom.json"
    custom.write_text(
        '{"description":"x","version":"1.0",'
        '"sources":[{"name":"src","path":"/x.parquet"}],'
        '"features":[{"name":"src.col","column_name":"col","dtype":"int64"}],'
        '"docs":[],"groups":[],"lineage_edges":[]}',
        encoding="utf-8",
    )

    runner = CliRunner()
    result = runner.invoke(app, ["demo", "seed", "--fixture", str(custom)])
    assert result.exit_code == 0, result.output

    db = LocalBackend(db_path)
    try:
        assert db.get_feature_by_name("src.col") is not None
    finally:
        db.close()
