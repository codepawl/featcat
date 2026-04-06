"""Tests for the featcat API server."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from featcat.server.app import build_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    """Create a test app with a temporary database."""
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)
    return build_app()


@pytest.fixture
def client(app):
    """Create a test client."""
    with TestClient(app) as c:
        yield c


class TestHealth:
    def test_health(self, client):
        resp = client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("ok", "degraded")
        assert "db" in data

    def test_stats(self, client):
        resp = client.get("/api/stats")
        assert resp.status_code == 200


class TestSources:
    def test_list_empty(self, client):
        resp = client.get("/api/sources")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_add_and_get(self, client, tmp_path):
        # Create a dummy parquet file for the source path
        source_path = str(tmp_path / "data.parquet")
        resp = client.post("/api/sources", json={
            "name": "test-src",
            "path": source_path,
            "storage_type": "local",
            "format": "parquet",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "test-src"

        # List
        resp = client.get("/api/sources")
        assert len(resp.json()) == 1

        # Get by name
        resp = client.get("/api/sources/test-src")
        assert resp.status_code == 200
        assert resp.json()["name"] == "test-src"

    def test_get_missing(self, client):
        resp = client.get("/api/sources/nonexistent")
        assert resp.status_code == 404


class TestFeatures:
    def test_list_empty(self, client):
        resp = client.get("/api/features")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_get_missing(self, client):
        resp = client.get("/api/features/nonexistent")
        assert resp.status_code == 404


class TestDocs:
    def test_stats(self, client):
        resp = client.get("/api/docs/stats")
        assert resp.status_code == 200

    def test_get_missing_doc(self, client):
        resp = client.get("/api/docs/nonexistent")
        assert resp.status_code == 404


class TestMonitor:
    def test_check(self, client):
        resp = client.get("/api/monitor/check")
        assert resp.status_code == 200

    def test_report(self, client):
        resp = client.get("/api/monitor/report")
        assert resp.status_code == 200

    def test_baseline(self, client):
        resp = client.post("/api/monitor/baseline")
        assert resp.status_code == 200


class TestAI:
    def test_ask_without_llm(self, client):
        resp = client.post("/api/ai/ask", json={"query": "test"})
        assert resp.status_code == 200

    def test_discover_without_llm(self, client):
        resp = client.post("/api/ai/discover", json={"use_case": "churn prediction"})
        assert resp.status_code in (500, 503)  # LLM not available
