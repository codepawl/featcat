"""Tests for group aggregation endpoints (health, monitoring, regenerate-docs)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature, FeatureGroup
from featcat.server import create_app

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def client_with_group(tmp_path: Path, monkeypatch):
    db_path = str(tmp_path / "ag.db")
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)

    seed = CatalogDB(db_path)
    seed.init_db()
    src = DataSource(name="src", path="/data/x.parquet")
    seed.add_source(src)

    feat_a = Feature(name="src.a", data_source_id=src.id, column_name="a", dtype="int64")
    feat_b = Feature(name="src.b", data_source_id=src.id, column_name="b", dtype="float64")
    feat_c = Feature(name="src.c", data_source_id=src.id, column_name="c", dtype="float64")
    for f in (feat_a, feat_b, feat_c):
        seed.upsert_feature(f)

    group = FeatureGroup(name="metrics", description="Test group")
    seed.create_group(group)
    seed.add_group_members(group.id, [feat_a.id, feat_b.id, feat_c.id])

    seed.save_monitoring_result(feat_a.id, feat_a.name, psi=0.05, severity="healthy")
    seed.save_monitoring_result(feat_b.id, feat_b.name, psi=0.4, severity="critical")
    seed.close()

    app = create_app()
    with TestClient(app) as c:
        # Force LLM None on app state so the regenerate-docs endpoint returns 503
        # instead of trying to call a non-existent llamacpp.
        app.state.llm = None
        yield c


class TestGroupHealth:
    def test_returns_aggregate(self, client_with_group: TestClient) -> None:
        resp = client_with_group.get("/api/groups/metrics/health")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["group"] == "metrics"
        assert data["member_count"] == 3
        assert "grade_distribution" in data
        assert "members" in data
        assert "lowest_scored" in data

    def test_unknown_group(self, client_with_group: TestClient) -> None:
        resp = client_with_group.get("/api/groups/no-such/health")
        assert resp.status_code == 404


class TestGroupMonitoring:
    def test_severity_aggregation(self, client_with_group: TestClient) -> None:
        resp = client_with_group.get("/api/groups/metrics/monitoring")
        assert resp.status_code == 200, resp.text
        data = resp.json()
        assert data["member_count"] == 3
        sc = data["severity_counts"]
        assert sc.get("healthy", 0) >= 1
        assert sc.get("critical", 0) >= 1
        assert sc.get("unknown", 0) >= 1
        with_drift = data["members_with_drift"]
        assert any(m["spec"] == "src.b" for m in with_drift)

    def test_psi_average(self, client_with_group: TestClient) -> None:
        resp = client_with_group.get("/api/groups/metrics/monitoring")
        psi_avg = resp.json()["psi_average"]
        assert psi_avg is not None
        assert abs(psi_avg - 0.225) < 1e-6


class TestGroupRegenerateDocs:
    def test_no_llm_returns_503(self, client_with_group: TestClient) -> None:
        resp = client_with_group.post(
            "/api/groups/metrics/regenerate-docs",
            json={"regenerate_existing": True, "global_hint": None},
        )
        assert resp.status_code == 503

    def test_unknown_group(self, client_with_group: TestClient) -> None:
        resp = client_with_group.post(
            "/api/groups/no-such/regenerate-docs",
            json={"regenerate_existing": False},
        )
        assert resp.status_code in (404, 503)
