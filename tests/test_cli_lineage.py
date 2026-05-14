"""Tests for `featcat lineage edge add` and `featcat lineage edge rm`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text
from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


def _seed(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    src = DataSource(name="src", path=str(tmp_path / "data.parquet"))
    db.add_source(src)
    db.upsert_feature(Feature(name="src.base", data_source_id=src.id, column_name="base", dtype="int64"))
    db.upsert_feature(Feature(name="src.derived", data_source_id=src.id, column_name="derived", dtype="int64"))
    return db


def _count_edges(db: LocalBackend, child_id: str, parent_id: str) -> int:
    with db.session() as s:
        return int(
            s.execute(
                text(
                    "SELECT COUNT(*) FROM feature_lineage "
                    "WHERE child_feature_id = :cid AND parent_feature_id = :pid "
                    "  AND parent_type = 'feature'"
                ),
                {"cid": child_id, "pid": parent_id},
            ).scalar()
            or 0
        )


class TestLineageEdgeAdd:
    def test_happy_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        child = db.get_feature_by_name("src.derived")
        parent = db.get_feature_by_name("src.base")
        assert child is not None and parent is not None
        cid, pid = child.id, parent.id
        db.close()

        result = runner.invoke(
            app,
            ["lineage", "edge", "add", "src.derived", "src.base", "--transform", "SUM(base)"],
        )
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert _count_edges(db, cid, pid) == 1
        db.close()

    def test_missing_child(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["lineage", "edge", "add", "src.ghost", "src.base"])
        assert result.exit_code == 1
        assert "src.ghost" in result.output

    def test_missing_parent(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["lineage", "edge", "add", "src.derived", "src.ghost"])
        assert result.exit_code == 1
        assert "src.ghost" in result.output

    def test_repeated_add_does_not_error(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Calling add twice must not raise — CLI returns 0 either way.

        Note: idempotency in storage depends on the SQLite NULL-handling
        of the parent_source_id/parent_column unique columns and is not
        guaranteed on the SQLite path. The CLI just trusts the backend.
        """
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        runner.invoke(app, ["lineage", "edge", "add", "src.derived", "src.base"])
        result = runner.invoke(app, ["lineage", "edge", "add", "src.derived", "src.base"])
        assert result.exit_code == 0, result.output


class TestLineageEdgeRm:
    def test_happy_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        child = db.get_feature_by_name("src.derived")
        parent = db.get_feature_by_name("src.base")
        assert child is not None and parent is not None
        cid, pid = child.id, parent.id
        db.add_lineage(child_feature_id=cid, parent_feature_id=pid)
        db.close()

        result = runner.invoke(app, ["lineage", "edge", "rm", "src.derived", "src.base", "--yes"])
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert _count_edges(db, cid, pid) == 0
        db.close()

    def test_missing_edge_exits_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """No matching edge → exit 1; don't pretend success."""
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["lineage", "edge", "rm", "src.derived", "src.base", "--yes"])
        assert result.exit_code == 1
        assert "Edge not found" in result.output

    def test_decline_prompt_keeps_edge(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        child = db.get_feature_by_name("src.derived")
        parent = db.get_feature_by_name("src.base")
        assert child is not None and parent is not None
        cid, pid = child.id, parent.id
        db.add_lineage(child_feature_id=cid, parent_feature_id=pid)
        db.close()

        result = runner.invoke(app, ["lineage", "edge", "rm", "src.derived", "src.base"], input="n\n")
        assert result.exit_code == 0

        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert _count_edges(db, cid, pid) == 1
        db.close()
