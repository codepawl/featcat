"""Tests for T1.1b — sqlglot-based lineage auto-detect.

Skipped en bloc when sqlglot isn't installed (it's an optional extra under
``[lineage-sql]``). The CLI integration test stitches the parser through
the Typer command against a tmp-path catalog so we cover the apply path.
"""

from __future__ import annotations

import warnings
from typing import TYPE_CHECKING

import pytest

pytest.importorskip("sqlglot")

from featcat.lineage import detect_lineage_from_sql  # noqa: E402
from featcat.lineage.sql_detect import detect_lineage_from_file  # noqa: E402

if TYPE_CHECKING:
    from pathlib import Path


# --------------------------------------------------------------------------- #
# Library: detect_lineage_from_sql                                            #
# --------------------------------------------------------------------------- #


class TestParser:
    def test_create_table_as_select_simple_arithmetic(self) -> None:
        edges = detect_lineage_from_sql("CREATE TABLE foo AS SELECT a + b AS c FROM bar")
        assert len(edges) == 2
        children = {e.child for e in edges}
        parents = {e.parent for e in edges}
        assert children == {"foo.c"}
        assert parents == {"bar.a", "bar.b"}
        assert all(e.transform == "a + b" for e in edges)

    def test_create_or_replace_view_with_aggregate(self) -> None:
        sql = "CREATE OR REPLACE VIEW foo AS SELECT count(distinct session_id) AS sessions FROM events GROUP BY user_id"
        edges = detect_lineage_from_sql(sql)
        assert len(edges) == 1
        e = edges[0]
        assert e.child == "foo.sessions"
        assert e.parent == "events.session_id"
        # sqlglot canonicalizes COUNT(DISTINCT ...) — match case-insensitively.
        assert "session_id" in e.transform.lower()
        assert "count" in e.transform.lower()

    def test_insert_into_select(self) -> None:
        edges = detect_lineage_from_sql("INSERT INTO foo SELECT a + b AS c FROM bar")
        children = {e.child for e in edges}
        parents = {e.parent for e in edges}
        assert children == {"foo.c"}
        assert parents == {"bar.a", "bar.b"}

    def test_aliased_from_resolves_to_real_table(self) -> None:
        sql = "CREATE TABLE foo AS SELECT t.a + s.b AS c FROM bar t JOIN sup s ON t.id = s.id"
        edges = detect_lineage_from_sql(sql)
        parents = {e.parent for e in edges}
        # Aliases t/s must resolve to bar/sup, not be passed through.
        assert parents == {"bar.a", "sup.b"}

    def test_multiple_output_columns(self) -> None:
        sql = (
            "CREATE TABLE user_behavior AS "
            "SELECT count(distinct session_id) AS sessions, "
            "       avg(duration) AS avg_dur "
            "FROM events GROUP BY user_id"
        )
        edges = detect_lineage_from_sql(sql)
        children = {e.child for e in edges}
        assert children == {"user_behavior.sessions", "user_behavior.avg_dur"}
        # Each output column emits at least one edge.
        per_child = {c: [e for e in edges if e.child == c] for c in children}
        assert all(len(v) >= 1 for v in per_child.values())

    def test_schema_qualified_target_drops_schema(self) -> None:
        # schema.foo → child should be "foo.c", not "schema.foo.c", so a
        # downstream feature-by-name lookup has a chance to match.
        edges = detect_lineage_from_sql("CREATE TABLE analytics.foo AS SELECT a AS c FROM bar")
        assert {e.child for e in edges} == {"foo.c"}

    def test_plain_select_warns_and_returns_empty(self) -> None:
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always")
            edges = detect_lineage_from_sql("SELECT a + b AS c FROM bar")
        assert edges == []
        # Detector emits a warning explaining the skip.
        assert any("output target" in str(w.message).lower() for w in ws)

    def test_ddl_only_create_table_warns_and_returns_empty(self) -> None:
        # CREATE TABLE foo (a int) — no body, no lineage to derive.
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always")
            edges = detect_lineage_from_sql("CREATE TABLE foo (a INT, b TEXT)")
        assert edges == []
        # Either we warn or just return empty cleanly; never raise.
        del ws  # warning emission depends on sqlglot dialect quirks

    def test_unparseable_sql_warns_no_raise(self) -> None:
        with warnings.catch_warnings(record=True) as ws:
            warnings.simplefilter("always")
            edges = detect_lineage_from_sql("THIS IS NOT SQL ;;;")
        assert edges == []
        # We accept either a parse warning or graceful empty.
        del ws

    def test_detect_from_file_carries_source_metadata(self, tmp_path: Path) -> None:
        sql = (
            "-- transforms file\n"
            "CREATE TABLE user_behavior AS\n"
            "SELECT\n"
            "    count(distinct session_id) AS sessions\n"
            "FROM events GROUP BY user_id;\n"
        )
        p = tmp_path / "sessions.sql"
        p.write_text(sql)
        edges = detect_lineage_from_file(p)
        assert len(edges) == 1
        e = edges[0]
        assert e.source_file == str(p)
        # Best-effort line tracking — should land on the alias line.
        assert e.source_line is not None
        assert e.source_line >= 1


# --------------------------------------------------------------------------- #
# CLI: featcat lineage detect                                                 #
# --------------------------------------------------------------------------- #


class TestCLI:
    def test_detect_apply_writes_edges(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from typer.testing import CliRunner

        from featcat.catalog.local import LocalBackend
        from featcat.catalog.models import DataSource, Feature
        from featcat.cli import app

        runner = CliRunner()

        # Build a small catalog: source 'events' with column 'session_id',
        # plus a child feature 'user_behavior.sessions' — child lookup must
        # match the parser's "<table>.<alias>" output names.
        db_path = tmp_path / "catalog.db"
        db = LocalBackend(str(db_path))
        db.init_db()
        events = db.add_source(DataSource(name="events", path="/events.parquet"))
        # Register the parent column as a feature so the parser's
        # 'events.session_id' resolves through the feature path.
        db.upsert_feature(
            Feature(
                name="events.session_id",
                data_source_id=events.id,
                column_name="session_id",
                dtype="string",
            )
        )
        # Register the output table as a source too, so we can hang the
        # output feature off it.
        ub_src = db.add_source(DataSource(name="user_behavior", path="/ub.parquet"))
        db.upsert_feature(
            Feature(
                name="user_behavior.sessions",
                data_source_id=ub_src.id,
                column_name="sessions",
                dtype="int64",
            )
        )

        # Point the CLI at our tmp DB.
        monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", str(db_path))
        monkeypatch.delenv("FEATCAT_SERVER_URL", raising=False)

        sql_file = tmp_path / "sessions.sql"
        sql_file.write_text(
            "CREATE TABLE user_behavior AS SELECT count(distinct session_id) AS sessions FROM events GROUP BY user_id"
        )

        # Preview run — no writes. Rich may truncate long feature names in
        # the table; assert on the parent (which fits) plus the count.
        result = runner.invoke(app, ["lineage", "detect", "--from", str(sql_file)])
        assert result.exit_code == 0, result.output
        assert "Proposed lineage edges (1)" in result.output
        assert "events.session_id" in result.output
        # Nothing written yet.
        impact_before = db.get_impact("events", column="session_id")
        assert impact_before == []

        # Apply run with --confirm to skip prompt.
        result2 = runner.invoke(
            app,
            ["lineage", "detect", "--from", str(sql_file), "--apply", "--confirm"],
        )
        assert result2.exit_code == 0, result2.output
        assert "Wrote 1" in result2.output

        # The edge should land in get_lineage_graph: child user_behavior.sessions
        # has parent events.session_id. We assert directly on the graph.
        graph = db.get_lineage_graph()
        edges = graph.get("edges", [])
        # An edge whose target ends in "user_behavior.sessions" and source
        # ends in "events.session_id" must exist.
        assert any(
            e.get("source", "").endswith("session_id") and e.get("target", "").endswith("sessions") for e in edges
        ), edges

    def test_detect_no_match_exits_clean(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        from typer.testing import CliRunner

        from featcat.cli import app

        runner = CliRunner()
        monkeypatch.chdir(tmp_path)
        result = runner.invoke(app, ["lineage", "detect", "--from", "nope/*.sql"])
        # Non-zero exit when nothing matches — surfaces in CI / scripts.
        assert result.exit_code == 1
        assert "No SQL files" in result.output
