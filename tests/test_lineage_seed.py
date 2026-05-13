"""Tests for `featcat lineage seed` and `featcat lineage clear --demo-only`."""

from __future__ import annotations

import json
from pathlib import Path

from sqlalchemy import text
from typer.testing import CliRunner

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature
from featcat.cli import DEMO_DETECTED_METHOD, DEMO_FEATURE_TAG, app

runner = CliRunner()

FIXTURE_PATH = Path(__file__).parent / "fixtures" / "lineage-demo.json"


def _count_edges(db: LocalBackend) -> int:
    with db.session() as s:
        return int(s.execute(text("SELECT COUNT(*) FROM feature_lineage")).scalar() or 0)


def _count_demo_edges(db: LocalBackend) -> int:
    with db.session() as s:
        return int(
            s.execute(
                text("SELECT COUNT(*) FROM feature_lineage WHERE detected_method = :m"),
                {"m": DEMO_DETECTED_METHOD},
            ).scalar()
            or 0
        )


class TestSeedFromFixture:
    """Seeding from the canonical demo fixture against an empty catalog."""

    def test_creates_sources_features_and_edges(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["init"])
        assert result.exit_code == 0

        result = runner.invoke(app, ["lineage", "seed", str(FIXTURE_PATH)])
        assert result.exit_code == 0, result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        # Three sources from the fixture (device_logs, client_logs, demand_v2).
        sources = {s.name for s in db.list_sources()}
        assert sources == {"device_logs", "client_logs", "demand_v2"}
        # 15 features auto-created — every node referenced by the fixture.
        demo_features = db.list_features(tag=DEMO_FEATURE_TAG)
        assert len(demo_features) == 15
        # 13 edges, all tagged `demo`.
        assert _count_demo_edges(db) == 13

    def test_dry_run_makes_no_changes(self, tmp_path: Path, monkeypatch) -> None:
        """Dry-run must print the plan but not write a single row.

        This is the contract that lets users preview against a real
        catalog without polluting it.
        """
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        result = runner.invoke(app, ["lineage", "seed", str(FIXTURE_PATH), "--dry-run"])
        assert result.exit_code == 0
        assert "Dry run" in result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        assert db.list_sources() == []
        assert db.list_features() == []
        assert _count_edges(db) == 0

    def test_second_seed_skips_duplicates(self, tmp_path: Path, monkeypatch) -> None:
        """Re-running seed must be idempotent — same edge count, no errors."""
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["lineage", "seed", str(FIXTURE_PATH)])

        result = runner.invoke(app, ["lineage", "seed", str(FIXTURE_PATH)])
        assert result.exit_code == 0
        assert "Skipped 13 duplicate" in result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        assert _count_demo_edges(db) == 13

    def test_force_replaces_existing_edges(self, tmp_path: Path, monkeypatch) -> None:
        """`--force` updates the transform string by remove+add."""
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["lineage", "seed", str(FIXTURE_PATH)])

        # Mutate the fixture's first edge's transformation, write to a temp
        # copy, and re-seed with --force.
        modified = json.loads(FIXTURE_PATH.read_text())
        modified["edges"][0]["transformation"] = "REPLACED"
        out = tmp_path / "modified.json"
        out.write_text(json.dumps(modified))

        result = runner.invoke(app, ["lineage", "seed", str(out), "--force"])
        assert result.exit_code == 0
        assert "Replaced 13 existing edge" in result.output

        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        # The mutated edge now has the new transform; count is unchanged.
        assert _count_demo_edges(db) == 13
        with db.session() as s:
            row = (
                s.execute(
                    text(
                        "SELECT fl.transform FROM feature_lineage fl "
                        "JOIN features fc ON fl.child_feature_id = fc.id "
                        "JOIN features fp ON fl.parent_feature_id = fp.id "
                        "WHERE fc.name = :child AND fp.name = :parent"
                    ),
                    {
                        "child": "device_logs.cpu_usage_30d_avg",
                        "parent": "device_logs.cpu_usage_raw",
                    },
                )
                .mappings()
                .first()
            )
        assert row is not None and row["transform"] == "REPLACED"


class TestSeedRespectsExistingFeatures:
    """Pre-existing real features must not be replaced or re-tagged."""

    def test_existing_feature_not_re_stubbed(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        # Set up the device_logs source + cpu_usage_raw feature manually,
        # as if it had been registered by a real scan.
        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        src = db.add_source(DataSource(name="device_logs", path="/real/device_logs.parquet"))
        db.upsert_feature(
            Feature(
                name="device_logs.cpu_usage_raw",
                data_source_id=src.id,
                column_name="cpu_usage_raw",
                dtype="float32",
                description="Real feature",
                tags=["production"],
            )
        )

        result = runner.invoke(app, ["lineage", "seed", str(FIXTURE_PATH)])
        assert result.exit_code == 0

        # Real feature preserved — tag and description untouched, dtype not
        # downgraded to the float64 default.
        real = db.get_feature_by_name("device_logs.cpu_usage_raw")
        assert real is not None
        assert real.tags == ["production"]
        assert real.description == "Real feature"
        assert real.dtype == "float32"
        # Source preserved — path stays /real/, not /demo/.
        assert db.get_source_by_name("device_logs").path == "/real/device_logs.parquet"

    def test_clear_demo_only_keeps_real_data(self, tmp_path: Path, monkeypatch) -> None:
        """`clear --demo-only` removes demo rows but not real ones, even
        when a real feature shares a source with demo stubs."""
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        # Real source + feature outside the fixture.
        src = db.add_source(DataSource(name="ml_features", path="/real/ml_features.parquet"))
        db.upsert_feature(
            Feature(
                name="ml_features.user_score",
                data_source_id=src.id,
                column_name="user_score",
                dtype="float64",
                tags=["production"],
            )
        )

        runner.invoke(app, ["lineage", "seed", str(FIXTURE_PATH)])
        result = runner.invoke(app, ["lineage", "clear", "--demo-only", "--yes"])
        assert result.exit_code == 0

        # Real data untouched.
        assert db.get_feature_by_name("ml_features.user_score") is not None
        assert db.get_source_by_name("ml_features") is not None
        # Demo data gone.
        assert db.get_feature_by_name("device_logs.cpu_usage_raw") is None
        assert db.get_source_by_name("device_logs") is None
        assert _count_demo_edges(db) == 0


class TestSeedErrorHandling:
    def test_missing_file_exits_nonzero(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        result = runner.invoke(app, ["lineage", "seed", str(tmp_path / "nope.json")])
        # Typer's `exists=True` on the argument rejects the path before our
        # code runs — exit code 2 (usage error).
        assert result.exit_code != 0

    def test_invalid_json_reports_error(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        bad = tmp_path / "bad.json"
        bad.write_text("{not valid json")

        result = runner.invoke(app, ["lineage", "seed", str(bad)])
        assert result.exit_code == 1
        assert "Invalid JSON" in result.output

    def test_schema_mismatch_reports_error(self, tmp_path: Path, monkeypatch) -> None:
        """Missing required field (`edges`) should fail schema validation,
        not crash with a KeyError later."""
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        bad = tmp_path / "bad.json"
        bad.write_text('{"description": "no edges field", "version": "1.0"}')

        result = runner.invoke(app, ["lineage", "seed", str(bad)])
        assert result.exit_code == 1
        assert "Fixture schema validation failed" in result.output


class TestSeedAgainstLegacySchema:
    """Regression: catalogs created before the T1.1 lineage migration keep
    the old 2-column unique constraint ``UNIQUE(child_feature_id,
    parent_feature_id)``. The seeder bypasses ``add_lineage`` precisely so
    its 5-column ON CONFLICT clause doesn't blow up here — verify that."""

    def test_seed_works_on_legacy_2col_unique_constraint(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])

        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        # Rebuild feature_lineage with the legacy constraint to simulate a
        # pre-T1.1 catalog. The columns themselves are the same as in init_db's
        # ALTER TABLE migrations — only the UNIQUE clause differs.
        with db.session() as s:
            s.execute(text("DROP TABLE IF EXISTS feature_lineage"))
            s.execute(
                text(
                    "CREATE TABLE feature_lineage ("
                    "  id TEXT PRIMARY KEY,"
                    "  child_feature_id TEXT NOT NULL REFERENCES features(id) ON DELETE CASCADE,"
                    "  parent_feature_id TEXT NOT NULL REFERENCES features(id) ON DELETE CASCADE,"
                    "  transform TEXT DEFAULT '',"
                    "  created_at TIMESTAMP NOT NULL,"
                    "  parent_type TEXT NOT NULL DEFAULT 'feature',"
                    "  parent_source_id TEXT,"
                    "  parent_column TEXT,"
                    "  detected_method TEXT NOT NULL DEFAULT 'manual',"
                    "  UNIQUE(child_feature_id, parent_feature_id)"
                    ")"
                )
            )
            s.commit()

        result = runner.invoke(app, ["lineage", "seed", str(FIXTURE_PATH)])
        assert result.exit_code == 0, result.output
        assert _count_demo_edges(db) == 13


class TestClearWithoutDemoOnly:
    """The clear command refuses to run without `--demo-only` — guard against
    accidental mass deletion of real lineage."""

    def test_clear_refuses_without_demo_only(self, tmp_path: Path, monkeypatch) -> None:
        monkeypatch.chdir(tmp_path)
        runner.invoke(app, ["init"])
        runner.invoke(app, ["lineage", "seed", str(FIXTURE_PATH)])

        result = runner.invoke(app, ["lineage", "clear", "--yes"])
        assert result.exit_code == 2
        assert "Refusing to clear without --demo-only" in result.output

        # Data still there.
        db = LocalBackend(str(tmp_path / "catalog.db"))
        db.init_db()
        assert _count_demo_edges(db) == 13
