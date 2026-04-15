"""Tests for TF-IDF ranked search and feature filtering."""

from __future__ import annotations

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from featcat.catalog.search import highlight_matches, search_features

SAMPLE_FEATURES = [
    {
        "name": "user_behavior.session_count", "column_name": "session_count",
        "tags": ["behavior", "30d"], "description": "Number of user sessions",
        "generation_hints": None,
    },
    {
        "name": "user_behavior.churn_label", "column_name": "churn_label",
        "tags": ["churn"], "description": "Binary churn indicator",
        "generation_hints": "1=churned, 0=active",
    },
    {
        "name": "device_performance.cpu_usage", "column_name": "cpu_usage",
        "tags": ["device", "performance"], "description": "CPU utilization percentage",
        "generation_hints": None,
    },
    {
        "name": "device_performance.memory_usage", "column_name": "memory_usage",
        "tags": ["device"], "description": "Memory usage in GB",
        "generation_hints": None,
    },
]


class TestSearchRanking:
    def test_exact_name_scores_highest(self):
        results = search_features("session count", SAMPLE_FEATURES)
        assert len(results) > 0
        # Session count should rank first
        assert results[0][0]["name"] == "user_behavior.session_count"

    def test_relevant_results_ranked_higher(self):
        results = search_features("churn", SAMPLE_FEATURES)
        assert len(results) > 0
        assert results[0][0]["name"] == "user_behavior.churn_label"

    def test_empty_query_returns_all(self):
        results = search_features("", SAMPLE_FEATURES)
        assert len(results) == 4
        assert all(score == 1.0 for _, score in results)

    def test_no_match_returns_empty(self):
        results = search_features("zzzznonexistent", SAMPLE_FEATURES)
        assert len(results) == 0

    def test_single_feature_no_crash(self):
        results = search_features("cpu", [SAMPLE_FEATURES[2]])
        assert len(results) == 1

    def test_scores_are_descending(self):
        results = search_features("device", SAMPLE_FEATURES)
        scores = [s for _, s in results]
        assert scores == sorted(scores, reverse=True)

    def test_tag_search(self):
        results = search_features("performance", SAMPLE_FEATURES)
        assert results[0][0]["name"] == "device_performance.cpu_usage"


class TestHighlights:
    def test_matched_terms(self):
        hl = highlight_matches("session count", SAMPLE_FEATURES[0])
        assert "column_name" in hl
        assert "session" in hl["column_name"]

    def test_no_match_empty(self):
        hl = highlight_matches("zzzzz", SAMPLE_FEATURES[0])
        assert hl == {}

    def test_tag_match(self):
        hl = highlight_matches("churn", SAMPLE_FEATURES[1])
        assert "tags" in hl
        assert "churn" in hl["tags"]

    def test_short_tokens_ignored(self):
        hl = highlight_matches("a b", SAMPLE_FEATURES[0])
        assert hl == {}


class TestSearchAPI:
    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        pytest.importorskip("fastapi")
        from fastapi.testclient import TestClient

        from featcat.server.app import build_app

        db_path = str(tmp_path / "test_search.db")
        monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)

        def _raise(**kwargs):
            raise RuntimeError("no LLM")

        monkeypatch.setattr("featcat.llm.create_llm", _raise)

        app = build_app()
        with TestClient(app) as c:
            # Create source with features
            pq_path = tmp_path / "users.parquet"
            table = pa.table({
                "user_id": pa.array([1, 2, 3]),
                "session_count": pa.array([10, 20, 30]),
                "churn_label": pa.array([0, 1, 0]),
            })
            pq.write_table(table, pq_path)
            c.post("/api/sources", json={"path": str(pq_path), "name": "users"})
            c.post("/api/sources/users/scan")
            yield c

    def test_search_returns_ranked(self, client):
        resp = client.get("/api/features", params={"search": "session"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
        # First result should be session_count
        assert "session" in data[0]["name"]
        # Should have search_score
        assert "search_score" in data[0]

    def test_search_has_highlights(self, client):
        resp = client.get("/api/features", params={"search": "session"})
        data = resp.json()
        first = data[0]
        assert "highlight" in first

    def test_dtype_filter(self, client):
        resp = client.get("/api/features", params={"dtype": "int64"})
        assert resp.status_code == 200
        data = resp.json()
        assert all(d["dtype"] == "int64" for d in data)

    def test_has_doc_filter(self, client):
        resp = client.get("/api/features", params={"has_doc": "false"})
        assert resp.status_code == 200
        data = resp.json()
        assert all(not d["has_doc"] for d in data)

    def test_sort_health_asc(self, client):
        resp = client.get("/api/features", params={"sort": "health", "order": "asc"})
        assert resp.status_code == 200
        data = resp.json()
        if len(data) >= 2:
            assert data[0].get("health_score", 0) <= data[-1].get("health_score", 0)

    def test_combined_filters(self, client):
        resp = client.get("/api/features", params={"source": "users", "dtype": "int64"})
        assert resp.status_code == 200
        data = resp.json()
        for d in data:
            assert d["dtype"] == "int64"
            assert d["name"].startswith("users.")

    def test_search_with_source_filter(self, client):
        resp = client.get("/api/features", params={"search": "session", "source": "users"})
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) > 0
