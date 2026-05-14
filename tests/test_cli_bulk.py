"""Tests for `featcat feature bulk-tag` and `featcat feature bulk-delete`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


def _seed(tmp_path: Path, count: int = 3) -> LocalBackend:
    """Seed a catalog with one source and ``count`` features under it."""
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    src = DataSource(name="src", path=str(tmp_path / "data.parquet"))
    db.add_source(src)
    for i in range(count):
        db.upsert_feature(Feature(name=f"src.col{i}", data_source_id=src.id, column_name=f"col{i}", dtype="int64"))
    return db


def _write_specs(tmp_path: Path, specs: list[str]) -> Path:
    p = tmp_path / "specs.txt"
    p.write_text("\n".join(specs) + "\n", encoding="utf-8")
    return p


class TestBulkTag:
    def test_add_action(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path, count=3)
        db.close()
        specs_file = _write_specs(tmp_path, ["src.col0", "src.col1"])

        result = runner.invoke(
            app,
            ["feature", "bulk-tag", "--action", "add", "--tags", "a,b", "--file", str(specs_file)],
        )
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        for name in ("src.col0", "src.col1"):
            f = db.get_feature_by_name(name)
            assert f is not None
            assert set(f.tags) == {"a", "b"}
        # Third feature untouched.
        f2 = db.get_feature_by_name("src.col2")
        assert f2 is not None
        assert f2.tags == []
        db.close()

    def test_all_or_nothing_on_unknown_spec(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """If any spec is unknown, exit 1 and do not write any tags."""
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path, count=2)
        db.close()
        specs_file = _write_specs(tmp_path, ["src.col0", "src.ghost"])

        result = runner.invoke(
            app,
            ["feature", "bulk-tag", "--action", "add", "--tags", "a", "--file", str(specs_file)],
        )
        assert result.exit_code == 1
        assert "src.ghost" in result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        f = db.get_feature_by_name("src.col0")
        assert f is not None
        assert f.tags == []
        db.close()

    def test_replace_prompts_when_not_yes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Replace must prompt by default; declining aborts with no write."""
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path, count=2)
        db.update_feature_metadata(db.get_feature_by_name("src.col0").id, tags=["existing"])  # type: ignore[union-attr]
        db.close()
        specs_file = _write_specs(tmp_path, ["src.col0", "src.col1"])

        result = runner.invoke(
            app,
            ["feature", "bulk-tag", "--action", "replace", "--tags", "new", "--file", str(specs_file)],
            input="n\n",
        )
        assert result.exit_code == 0
        assert "Aborted" in result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        f = db.get_feature_by_name("src.col0")
        assert f is not None
        assert f.tags == ["existing"]
        db.close()

    def test_invalid_action_exits_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()
        specs_file = _write_specs(tmp_path, ["src.col0"])

        result = runner.invoke(
            app,
            ["feature", "bulk-tag", "--action", "frobnicate", "--tags", "a", "--file", str(specs_file)],
        )
        assert result.exit_code == 1
        assert "add|remove|replace" in result.output


class TestBulkDelete:
    def test_happy_path_small(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """<=10 specs uses a single y/n prompt; --yes skips."""
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path, count=3)
        db.close()
        specs_file = _write_specs(tmp_path, ["src.col0", "src.col1"])

        result = runner.invoke(
            app,
            ["feature", "bulk-delete", "--file", str(specs_file), "--yes"],
        )
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert db.get_feature_by_name("src.col0") is None
        assert db.get_feature_by_name("src.col1") is None
        # Third feature untouched.
        assert db.get_feature_by_name("src.col2") is not None
        db.close()

    def test_type_to_confirm_above_threshold(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """>10 specs: must type DELETE back to confirm. Wrong input aborts."""
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path, count=12)
        db.close()
        specs_file = _write_specs(tmp_path, [f"src.col{i}" for i in range(11)])

        result = runner.invoke(app, ["feature", "bulk-delete", "--file", str(specs_file)], input="wrong\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        for i in range(11):
            assert db.get_feature_by_name(f"src.col{i}") is not None
        db.close()

    def test_type_to_confirm_succeeds_when_matched(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path, count=12)
        db.close()
        specs_file = _write_specs(tmp_path, [f"src.col{i}" for i in range(11)])

        result = runner.invoke(app, ["feature", "bulk-delete", "--file", str(specs_file)], input="DELETE\n")
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        for i in range(11):
            assert db.get_feature_by_name(f"src.col{i}") is None
        # Untouched feature stays.
        assert db.get_feature_by_name("src.col11") is not None
        db.close()

    def test_all_or_nothing_on_unknown_spec(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path, count=2)
        db.close()
        specs_file = _write_specs(tmp_path, ["src.col0", "src.ghost"])

        result = runner.invoke(app, ["feature", "bulk-delete", "--file", str(specs_file), "--yes"])
        assert result.exit_code == 1
        assert "src.ghost" in result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert db.get_feature_by_name("src.col0") is not None
        db.close()

    def test_comments_and_blanks_ignored(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Specs file: blank lines and '#' comments must be skipped."""
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path, count=2)
        db.close()
        specs_file = tmp_path / "specs.txt"
        specs_file.write_text("# a comment\n\nsrc.col0\n# another\nsrc.col1\n", encoding="utf-8")

        result = runner.invoke(app, ["feature", "bulk-delete", "--file", str(specs_file), "--yes"])
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert db.get_feature_by_name("src.col0") is None
        assert db.get_feature_by_name("src.col1") is None
        db.close()
