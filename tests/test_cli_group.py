"""Tests for `featcat group update`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import FeatureGroup
from featcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


def _seed(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    db.create_group(FeatureGroup(name="grp1", description="old desc"))
    return db


class TestGroupUpdate:
    def test_update_description(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["group", "update", "grp1", "--description", "new desc"])
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        grp = db.get_group_by_name("grp1")
        assert grp is not None
        assert grp.description == "new desc"
        db.close()

    def test_update_project_and_owner(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(
            app,
            ["group", "update", "grp1", "--project", "platform", "--owner", "alice@example.com"],
        )
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        grp = db.get_group_by_name("grp1")
        assert grp is not None
        assert grp.project == "platform"
        assert grp.owner == "alice@example.com"
        db.close()

    def test_no_fields_exits_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["group", "update", "grp1"])
        assert result.exit_code == 1
        assert "Nothing to update" in result.output

    def test_missing_group_exits_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        db.close()

        result = runner.invoke(app, ["group", "update", "ghost", "--description", "x"])
        assert result.exit_code == 1
        assert "ghost" in result.output
