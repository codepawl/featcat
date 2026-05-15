"""Tests for `featcat feature rm` and `featcat feature update`."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import text
from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature, FeatureGroup
from featcat.cli import app

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

runner = CliRunner()


def _seed(tmp_path: Path) -> LocalBackend:
    """Seed a catalog with one source and two features under it.

    The first feature also gets a doc + a group membership so we can
    verify the cascade contract on delete.
    """
    db = LocalBackend(str(tmp_path / "catalog.db"))
    db.init_db()
    src = DataSource(name="test_src", path=str(tmp_path / "data.parquet"))
    db.add_source(src)
    feat_a = Feature(name="test_src.col_a", data_source_id=src.id, column_name="col_a", dtype="int64")
    feat_b = Feature(name="test_src.col_b", data_source_id=src.id, column_name="col_b", dtype="int64")
    db.upsert_feature(feat_a)
    db.upsert_feature(feat_b)
    db.save_feature_doc(feat_a.id, {"short_description": "doc a"})
    grp = FeatureGroup(name="grp1")
    db.create_group(grp)
    db.add_group_members(grp.id, [feat_a.id])
    return db


class TestFeatureRm:
    def test_happy_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["feature", "rm", "test_src.col_b", "--yes"])
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert db.get_feature_by_name("test_src.col_b") is None
        # The other feature is untouched.
        assert db.get_feature_by_name("test_src.col_a") is not None
        db.close()

    def test_cascade_removes_doc_and_group_membership(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Doc + group_member rows for the deleted feature must be gone."""
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        feat_a = db.get_feature_by_name("test_src.col_a")
        assert feat_a is not None
        feat_id = feat_a.id
        grp = db.get_group_by_name("grp1")
        assert grp is not None
        grp_id = grp.id
        db.close()

        result = runner.invoke(app, ["feature", "rm", "test_src.col_a", "--yes"])
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert db.get_feature_by_name("test_src.col_a") is None
        assert db.get_feature_doc(feat_id) is None
        assert db.count_group_members(grp_id) == 0
        # Lineage / version FKs cascade automatically — sanity-check the version table.
        with db.session() as s:
            count = int(
                s.execute(
                    text("SELECT COUNT(*) FROM feature_versions WHERE feature_id = :fid"),
                    {"fid": feat_id},
                ).scalar()
                or 0
            )
        assert count == 0
        db.close()

    def test_missing_feature_exits_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        db.close()

        result = runner.invoke(app, ["feature", "rm", "ghost.col", "--yes"])
        assert result.exit_code == 1
        assert "ghost.col" in result.output

    def test_decline_prompt_keeps_feature(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["feature", "rm", "test_src.col_a"], input="n\n")
        assert result.exit_code == 0

        db = LocalBackend(str(tmp_path / "catalog.db"))
        assert db.get_feature_by_name("test_src.col_a") is not None
        db.close()


class TestFeatureUpdate:
    def test_update_owner(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["feature", "update", "test_src.col_a", "--owner", "alice@example.com"])
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        f = db.get_feature_by_name("test_src.col_a")
        assert f is not None
        assert f.owner == "alice@example.com"
        db.close()

    def test_update_description(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["feature", "update", "test_src.col_a", "--description", "the col"])
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        f = db.get_feature_by_name("test_src.col_a")
        assert f is not None
        assert f.description == "the col"
        db.close()

    def test_no_fields_exits_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = _seed(tmp_path)
        db.close()

        result = runner.invoke(app, ["feature", "update", "test_src.col_a"])
        assert result.exit_code == 1
        assert "Nothing to update" in result.output

    def test_missing_feature_exits_one(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.chdir(tmp_path)
        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        db.close()

        result = runner.invoke(app, ["feature", "update", "ghost.col", "--owner", "x"])
        assert result.exit_code == 1
        assert "ghost.col" in result.output


class TestFeatureDiff:
    """Regression for drift bug #1 in docs/BACKLOG.md (UAT scenario g.3):
    ``featcat feature diff`` reported ``(no differences)`` between consecutive
    versions even when only the ``definition`` field had changed, because the
    diff comparator only inspected five fields and ignored the rest of the
    snapshot.
    """

    def test_definition_change_is_reported(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.chdir(tmp_path)
        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        src = DataSource(name="src", path=str(tmp_path / "data.parquet"))
        db.add_source(src)
        feat = Feature(
            name="src.churn_flag",
            data_source_id=src.id,
            column_name="churn_flag",
            dtype="int64",
        )
        db.upsert_feature(feat)
        persisted = db.get_feature_by_name("src.churn_flag")
        assert persisted is not None
        # v1 -> v2 (initial definition).
        db.set_feature_definition(
            persisted.id,
            "SELECT 1 FROM device_logs WHERE complaint_count > 5",
            "sql",
        )
        # v2 -> v3 (modified definition).
        db.set_feature_definition(
            persisted.id,
            "SELECT 1 FROM device_logs WHERE error_rate > 0.1",
            "sql",
        )
        db.close()

        result_12 = runner.invoke(app, ["feature", "diff", "src.churn_flag", "--v1", "1", "--v2", "2"])
        assert result_12.exit_code == 0, result_12.output
        assert "(no differences)" not in result_12.output
        assert "definition:" in result_12.output
        assert "complaint_count > 5" in result_12.output

        result_23 = runner.invoke(app, ["feature", "diff", "src.churn_flag", "--v1", "2", "--v2", "3"])
        assert result_23.exit_code == 0, result_23.output
        assert "(no differences)" not in result_23.output
        assert "complaint_count > 5" in result_23.output
        assert "error_rate > 0.1" in result_23.output

    def test_no_changes_reports_no_differences(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Sanity: identical-on-the-diff-fields versions still report
        ``(no differences)`` so the fix only widens what counts as a
        difference, it doesn't false-positive on snapshot churn (timestamps,
        stats, embeddings) that the comparator intentionally ignores."""
        monkeypatch.chdir(tmp_path)
        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        src = DataSource(name="src", path=str(tmp_path / "data.parquet"))
        db.add_source(src)
        feat = Feature(
            name="src.unchanged",
            data_source_id=src.id,
            column_name="unchanged",
            dtype="int64",
        )
        db.upsert_feature(feat)
        persisted = db.get_feature_by_name("src.unchanged")
        assert persisted is not None
        # save_feature_doc snapshots a v2 that copies v1's user-editable
        # fields unchanged (only the doc rows change; doc bodies are not part
        # of the diff field list, intentionally).
        db.save_feature_doc(persisted.id, {"short_description": "x"})
        db.close()

        result = runner.invoke(app, ["feature", "diff", "src.unchanged", "--v1", "1", "--v2", "2"])
        assert result.exit_code == 0, result.output
        assert "(no differences)" in result.output
