"""Tests for `featcat source rm` and `featcat source update`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature, FeatureGroup
from featcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


def _seed(tmp_path: Path, *, feature_count: int = 0, in_groups: int = 0) -> LocalBackend:
    """Seed a fresh catalog at ``tmp_path/catalog.db`` with one source.

    ``feature_count`` features are upserted under ``test_src``; the first
    ``in_groups`` features additionally become members of distinct groups.
    Returns the open backend (caller should close).
    """
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    src = DataSource(name="test_src", path=str(tmp_path / "data.parquet"))
    db.add_source(src)
    feats = []
    for i in range(feature_count):
        f = Feature(name=f"test_src.col{i}", data_source_id=src.id, column_name=f"col{i}", dtype="int64")
        db.upsert_feature(f)
        feats.append(f)
    for i in range(min(in_groups, feature_count)):
        g = FeatureGroup(name=f"grp{i}")
        db.create_group(g)
        db.add_group_members(g.id, [feats[i].id])
    return db


class TestSourceRm:
    def test_happy_path_no_features(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Empty source: --yes deletes without prompting; cascade removes the row."""
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["source", "rm", "test_src", "--yes"])
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert db.get_source_by_name("test_src") is None
        db.close()

    def test_missing_source_exits_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Unknown source: exit 1 with a clear message — no prompt."""
        monkeypatch.chdir(tmp_path)
        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        db.close()

        result = runner.invoke(app, ["source", "rm", "ghost", "--yes"])
        assert result.exit_code == 1
        assert "ghost" in result.output

    def test_cascades_features_and_group_memberships(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Verify the audit's cascade contract: features removed, group memberships cleared."""
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path, feature_count=3, in_groups=2)
        db.close()

        result = runner.invoke(app, ["source", "rm", "test_src", "--yes"])
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert db.list_features(source_name="test_src") == []
        # Groups still exist but have no members from the deleted source.
        for i in range(2):
            grp = db.get_group_by_name(f"grp{i}")
            assert grp is not None
            assert db.count_group_members(grp.id) == 0
        db.close()

    def test_type_to_confirm_triggers_above_threshold(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """>10 features: typing the wrong name must abort with no DB change."""
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path, feature_count=11)
        db.close()

        result = runner.invoke(app, ["source", "rm", "test_src"], input="wrong\n")
        assert result.exit_code == 0
        assert "Aborted" in result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert db.get_source_by_name("test_src") is not None
        assert len(db.list_features(source_name="test_src")) == 11
        db.close()

    def test_type_to_confirm_succeeds_when_matched(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """>10 features: typing the source name back deletes everything."""
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path, feature_count=11)
        db.close()

        result = runner.invoke(app, ["source", "rm", "test_src"], input="test_src\n")
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert db.get_source_by_name("test_src") is None
        db.close()

    def test_standard_confirm_below_threshold(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """<=10 features: typer.confirm (y/n) gate, no type-to-confirm."""
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path, feature_count=3)
        db.close()

        # Decline.
        result = runner.invoke(app, ["source", "rm", "test_src"], input="n\n")
        assert result.exit_code == 0
        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert db.get_source_by_name("test_src") is not None
        db.close()

        # Accept.
        result = runner.invoke(app, ["source", "rm", "test_src"], input="y\n")
        assert result.exit_code == 0, result.output
        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert db.get_source_by_name("test_src") is None
        db.close()


class TestSourceUpdate:
    def test_update_description(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["source", "update", "test_src", "--description", "new desc"])
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        src = db.get_source_by_name("test_src")
        assert src is not None
        assert src.description == "new desc"
        db.close()

    def test_update_format(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["source", "update", "test_src", "--format", "csv"])
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        src = db.get_source_by_name("test_src")
        assert src is not None
        assert src.format == "csv"
        db.close()

    def test_update_join_metadata(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(
            app,
            [
                "source",
                "update",
                "test_src",
                "--entity-key",
                "user_id",
                "--event-timestamp-column",
                "event_ts",
                "--created-timestamp-column",
                "created_ts",
            ],
        )
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        src = db.get_source_by_name("test_src")
        assert src is not None
        assert src.entity_key == "user_id"
        assert src.event_timestamp_column == "event_ts"
        assert src.created_timestamp_column == "created_ts"
        db.close()

    def test_no_fields_exits_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Calling update with no fields is an error, not a silent no-op."""
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["source", "update", "test_src"])
        assert result.exit_code == 1
        assert "Nothing to update" in result.output

    def test_missing_source_exits_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        db.close()

        result = runner.invoke(app, ["source", "update", "ghost", "--description", "x"])
        assert result.exit_code == 1
        assert "ghost" in result.output


class TestSourceListJson:
    def test_json_output_is_valid(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """`source list --json` must emit parseable JSON with the documented schema."""
        import json as _json

        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["source", "list", "--json"])
        assert result.exit_code == 0, result.output
        payload = _json.loads(result.stdout)
        assert isinstance(payload, list) and len(payload) == 1
        row = payload[0]
        assert {
            "name",
            "path",
            "storage_type",
            "format",
            "description",
            "entity_key",
            "event_timestamp_column",
            "created_timestamp_column",
        } <= set(row)
        assert row["name"] == "test_src"

    def test_json_output_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        import json as _json

        monkeypatch.chdir(tmp_path)
        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        db.close()

        result = runner.invoke(app, ["source", "list", "--json"])
        assert result.exit_code == 0
        assert _json.loads(result.stdout) == []
