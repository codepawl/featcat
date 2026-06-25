"""Tests for feature health score computation and API integration."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.health import compute_health_score
from featcat.catalog.local import LocalBackend
from featcat.config import load_settings


class TestComputeHealthScore:
    def test_perfect_score(self):
        result = compute_health_score(
            has_doc=True,
            has_hints=True,
            drift_status="healthy",
            views_30d=10,
            queries_30d=5,
        )
        assert result["score"] == 100
        assert result["grade"] == "A"
        assert result["breakdown"] == {"documentation": 40, "drift": 40, "usage": 20}

    def test_zero_score(self):
        result = compute_health_score(
            has_doc=False,
            has_hints=False,
            drift_status="critical",
            views_30d=0,
            queries_30d=0,
        )
        assert result["score"] == 0
        assert result["grade"] == "D"

    def test_grade_boundaries(self):
        # Grade A: >= 80
        r = compute_health_score(has_doc=True, has_hints=True, drift_status="healthy", views_30d=0, queries_30d=0)
        assert r["score"] == 80
        assert r["grade"] == "A"

        # Grade B: >= 60, < 80
        r = compute_health_score(has_doc=True, has_hints=False, drift_status="healthy", views_30d=0, queries_30d=0)
        assert r["score"] == 65
        assert r["grade"] == "B"

        # Grade C: >= 40, < 60
        r = compute_health_score(has_doc=True, has_hints=False, drift_status="warning", views_30d=0, queries_30d=0)
        assert r["score"] == 45
        assert r["grade"] == "C"

        # Grade D: < 40
        r = compute_health_score(has_doc=False, has_hints=False, drift_status="critical", views_30d=1, queries_30d=0)
        assert r["score"] == 5
        assert r["grade"] == "D"

    def test_no_doc_means_zero_doc_score(self):
        r = compute_health_score(has_doc=False, has_hints=False, drift_status="healthy", views_30d=10, queries_30d=5)
        assert r["breakdown"]["documentation"] == 0

    def test_critical_drift_means_zero_drift_score(self):
        r = compute_health_score(has_doc=True, has_hints=True, drift_status="critical", views_30d=10, queries_30d=5)
        assert r["breakdown"]["drift"] == 0

    def test_unknown_drift_gets_30(self):
        r = compute_health_score(has_doc=False, has_hints=False, drift_status=None, views_30d=0, queries_30d=0)
        assert r["breakdown"]["drift"] == 30

    def test_explicit_unknown_string_matches_none(self):
        """A monitoring row with severity='unknown' must score the same 30 pts
        as a feature that has no monitoring row at all — single source of
        truth, no silent divergence between the two 'no signal' paths."""
        from_none = compute_health_score(has_doc=False, has_hints=False, drift_status=None, views_30d=0, queries_30d=0)
        from_unknown = compute_health_score(
            has_doc=False, has_hints=False, drift_status="unknown", views_30d=0, queries_30d=0
        )
        assert from_none["breakdown"]["drift"] == from_unknown["breakdown"]["drift"] == 30
        assert from_none["score"] == from_unknown["score"]
        assert from_none["grade"] == from_unknown["grade"]

    def test_warning_drift_gets_20(self):
        r = compute_health_score(has_doc=False, has_hints=False, drift_status="warning", views_30d=0, queries_30d=0)
        assert r["breakdown"]["drift"] == 20

    def test_usage_scoring(self):
        # No usage
        r = compute_health_score(has_doc=False, has_hints=False, drift_status="critical", views_30d=0, queries_30d=0)
        assert r["breakdown"]["usage"] == 0

        # Only queries
        r = compute_health_score(has_doc=False, has_hints=False, drift_status="critical", views_30d=0, queries_30d=1)
        assert r["breakdown"]["usage"] == 10

        # Views < 5
        r = compute_health_score(has_doc=False, has_hints=False, drift_status="critical", views_30d=3, queries_30d=0)
        assert r["breakdown"]["usage"] == 5

        # Views >= 5
        r = compute_health_score(has_doc=False, has_hints=False, drift_status="critical", views_30d=5, queries_30d=0)
        assert r["breakdown"]["usage"] == 10

        # All usage
        r = compute_health_score(has_doc=False, has_hints=False, drift_status="critical", views_30d=10, queries_30d=5)
        assert r["breakdown"]["usage"] == 20

    def test_doc_only(self):
        r = compute_health_score(has_doc=True, has_hints=False, drift_status="critical", views_30d=0, queries_30d=0)
        assert r["breakdown"]["documentation"] == 25

    def test_hints_only(self):
        r = compute_health_score(has_doc=False, has_hints=True, drift_status="critical", views_30d=0, queries_30d=0)
        assert r["breakdown"]["documentation"] == 15

    def test_breakdown_sums_to_score(self):
        r = compute_health_score(has_doc=True, has_hints=False, drift_status="warning", views_30d=3, queries_30d=1)
        assert r["score"] == sum(r["breakdown"].values())


class TestHealthAPI:
    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        from featcat.diagnostics.models import CheckResult, CheckStatus, GroupReport
        from featcat.server.app import build_app

        db_path = str(tmp_path / "test_health.db")
        monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)
        monkeypatch.setenv("FEATCAT_LLM_BACKEND", "disabled")
        monkeypatch.setenv("FEATCAT_SCHEDULER_ENABLED", "false")

        def _run_group(name: str, **kwargs):
            if name == "db":
                return GroupReport(
                    group="db",
                    checks=[
                        CheckResult(name="db_reachable", status=CheckStatus.PASS),
                        CheckResult(name="db_backend", status=CheckStatus.PASS),
                    ],
                )
            return GroupReport(group=name, checks=[])

        monkeypatch.setattr("featcat.diagnostics.run_group", _run_group)

        app = build_app(use_lifespan=False)
        settings = load_settings()
        backend = LocalBackend(settings.catalog_db_path)
        backend.init_db()
        app.state.backend = backend
        app.state.settings = settings
        app.state.llm = None
        app.state.scheduler = None
        with TestClient(app) as c:
            yield c
        backend.close()

    def test_list_features_includes_health(self, client):
        resp = client.get("/api/features")
        assert resp.status_code == 200
        # Empty catalog returns empty list; health fields would be present on items if any
        data = resp.json()
        assert isinstance(data, list)

    def test_api_health_includes_checks(self, client):
        """`/api/health` keeps the legacy shape and exposes the structured checks array."""
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        # Legacy fields (back-compat).
        assert {"status", "db", "llm", "model"} <= set(data)
        # New structured surface.
        assert "checks" in data
        assert isinstance(data["checks"], list)
        # The db group has at least the reachable + backend checks even on an empty catalog.
        names = {c["name"] for c in data["checks"]}
        assert "db_reachable" in names
        assert "db_backend" in names

    def test_health_summary_empty(self, client):
        resp = client.get("/api/features/health-summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["grade_distribution"] == {"A": 0, "B": 0, "C": 0, "D": 0}
        assert data["average_score"] == 0
        assert data["lowest_scored"] == []
        assert data["improvement_opportunities"] == []

    def test_health_summary_with_features(self, client, tmp_path):
        """Add a source and features, then check health-summary includes them."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        # Create a parquet file and add as source
        table = pa.table({"col_a": pa.array([1, 2, 3]), "col_b": pa.array([4.0, 5.0, 6.0])})
        path = tmp_path / "test.parquet"
        pq.write_table(table, path)

        client.post("/api/sources", json={"path": str(path), "name": "test_src"})
        client.post("/api/sources/test_src/scan")

        resp = client.get("/api/features/health-summary")
        assert resp.status_code == 200
        data = resp.json()
        total = sum(data["grade_distribution"].values())
        assert total == 2  # col_a and col_b
        assert data["average_score"] > 0

    def test_feature_detail_includes_health(self, client, tmp_path):
        """Check that GET /features/by-name includes health fields."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table({"score": pa.array([1.0, 2.0])})
        path = tmp_path / "test2.parquet"
        pq.write_table(table, path)

        client.post("/api/sources", json={"path": str(path), "name": "src2"})
        client.post("/api/sources/src2/scan")

        resp = client.get("/api/features/by-name", params={"name": "src2.score"})
        assert resp.status_code == 200
        data = resp.json()
        assert "health_score" in data
        assert "health_grade" in data
        assert "health_breakdown" in data
        assert data["health_score"] >= 0
        assert data["health_grade"] in ("A", "B", "C", "D")

    def test_paginated_health_grade_filter_is_applied(self, client, tmp_path, monkeypatch):
        """Health-grade filters require enrichment even on paginated responses."""
        import pyarrow as pa
        import pyarrow.parquet as pq

        table = pa.table({"a": pa.array([1, 2]), "b": pa.array([3, 4])})
        path = tmp_path / "grades.parquet"
        pq.write_table(table, path)
        client.post("/api/sources", json={"path": str(path), "name": "grade_src"})
        client.post("/api/sources/grade_src/scan")

        features = client.app.state.backend.list_features(source_name="grade_src")
        feature_by_col = {f.column_name: f for f in features}

        def _fake_health_data(_db):
            return (
                {feature_by_col["a"].id: {"short_description": "documented"}},
                {feature_by_col["a"].id: "healthy", feature_by_col["b"].id: "critical"},
                {
                    feature_by_col["a"].id: {"views": 5, "queries": 1},
                    feature_by_col["b"].id: {"views": 0, "queries": 0},
                },
            )

        monkeypatch.setattr("featcat.server.routes.features._bulk_health_data", _fake_health_data)

        resp = client.get("/api/features", params={"source": "grade_src", "limit": 10, "health_grade": "A"})

        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert [item["name"] for item in data["items"]] == ["grade_src.a"]
