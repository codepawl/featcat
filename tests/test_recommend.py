"""Tests for ``recommend_by_text`` + ``POST /api/features/recommend``.

Covers the LLM-first / TF-IDF-fallback recommend endpoint introduced in the
Similarity refactor. The server owns the LLM-vs-TF-IDF decision; clients
never retry. These tests exercise all four fallback-trigger paths
(no-LLM, exception, empty result, opt-out) plus the happy LLM path and
basic validation.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import pytest
from fastapi.testclient import TestClient

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def db_with_features(tmp_path: Path) -> LocalBackend:
    db = LocalBackend(str(tmp_path / "rec.db"))
    db.init_db()
    src = db.add_source(DataSource(name="src", path="/x.parquet"))
    db.upsert_feature(
        Feature(
            name="src.user_churn_score",
            data_source_id=src.id,
            column_name="user_churn_score",
            dtype="float64",
            tags=["churn", "user"],
            description="probability the user will churn within 30 days",
        )
    )
    db.upsert_feature(
        Feature(
            name="src.user_session_count",
            data_source_id=src.id,
            column_name="user_session_count",
            dtype="int64",
            tags=["user", "session"],
            description="count of user sessions in the last 30 days",
        )
    )
    db.upsert_feature(
        Feature(
            name="src.weather_temp",
            data_source_id=src.id,
            column_name="weather_temp",
            dtype="float64",
            tags=["weather"],
            description="ambient temperature in celsius",
        )
    )
    return db


class _StubLLM:
    """Used only as a sentinel; recommend route reaches into DiscoveryPlugin."""


class _MockDiscoveryPlugin:
    """Replaces DiscoveryPlugin during tests via monkey-patch.

    ``mode`` controls behavior:
      - ``"ok"``: returns the pre-canned ``existing_features``.
      - ``"empty"``: returns ``existing_features=[]`` (forces TF-IDF fallback).
      - ``"raise"``: raises an exception (forces TF-IDF fallback).
      - ``"slow"``: sleeps 10s (forces 8s timeout → TF-IDF fallback).
    """

    def __init__(self, mode: str = "ok", existing: list[dict] | None = None) -> None:
        self.mode = mode
        self.existing = existing or []

    def execute(self, db: Any, llm: Any, **kwargs: Any) -> Any:
        from featcat.plugins.base import PluginResult

        if self.mode == "raise":
            raise RuntimeError("simulated LLM error")
        if self.mode == "slow":
            time.sleep(10)
        if self.mode == "empty":
            return PluginResult(status="success", data={"existing_features": [], "summary": "no matches"})
        return PluginResult(
            status="success",
            data={"existing_features": self.existing, "summary": "mocked LLM summary"},
        )


def _client(db: LocalBackend, llm: Any = None) -> TestClient:
    from featcat.server import create_app
    from featcat.server.cache import invalidate
    from featcat.server.deps import get_db, get_llm

    invalidate("recommend:")
    app = create_app()
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[get_llm] = lambda: llm
    return TestClient(app)


# ---------------------------------------------------------------------------
# Backend method tests
# ---------------------------------------------------------------------------


class TestRecommendByText:
    def test_returns_empty_on_empty_catalog(self, tmp_path: Path) -> None:
        db = LocalBackend(str(tmp_path / "empty.db"))
        db.init_db()
        assert db.recommend_by_text("anything", top_k=5) == []

    def test_top_k_caps_results(self, db_with_features: LocalBackend) -> None:
        results = db_with_features.recommend_by_text("user behavior", top_k=1)
        assert len(results) <= 1

    def test_ranks_relevant_features_first(self, db_with_features: LocalBackend) -> None:
        results = db_with_features.recommend_by_text("churn prediction", top_k=3)
        if results:
            assert results[0][0].name == "src.user_churn_score"


# ---------------------------------------------------------------------------
# Route-level tests
# ---------------------------------------------------------------------------


class TestRecommendEndpoint:
    def test_validation_use_case_too_short(self, db_with_features: LocalBackend) -> None:
        resp = _client(db_with_features).post("/api/features/recommend", json={"use_case": "xy"})
        assert resp.status_code == 422

    def test_tfidf_fallback_when_llm_none(self, db_with_features: LocalBackend) -> None:
        resp = _client(db_with_features, llm=None).post(
            "/api/features/recommend", json={"use_case": "churn prediction"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["method"] == "tfidf"
        assert "LLM unavailable" in (body["summary"] or "")

    def test_force_use_llm_false_skips_llm(
        self, db_with_features: LocalBackend, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # LLM is available but the caller opted out.
        plugin = _MockDiscoveryPlugin(mode="ok", existing=[{"name": "src.user_churn_score"}])
        monkeypatch.setattr("featcat.plugins.discovery.DiscoveryPlugin", lambda: plugin)
        resp = _client(db_with_features, llm=_StubLLM()).post(
            "/api/features/recommend", json={"use_case": "churn prediction", "use_llm": False}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["method"] == "tfidf"
        assert "bypassed" in (body["summary"] or "").lower()

    def test_llm_path_uses_discovery_when_available(
        self, db_with_features: LocalBackend, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plugin = _MockDiscoveryPlugin(
            mode="ok",
            existing=[{"name": "src.user_churn_score", "relevance": 0.95, "reason": "directly relevant"}],
        )
        monkeypatch.setattr("featcat.plugins.discovery.DiscoveryPlugin", lambda: plugin)
        resp = _client(db_with_features, llm=_StubLLM()).post(
            "/api/features/recommend", json={"use_case": "churn prediction"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["method"] == "llm"
        assert body["matches"]
        assert body["matches"][0]["feature"]["name"] == "src.user_churn_score"

    def test_llm_empty_result_falls_back_to_tfidf(
        self, db_with_features: LocalBackend, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plugin = _MockDiscoveryPlugin(mode="empty")
        monkeypatch.setattr("featcat.plugins.discovery.DiscoveryPlugin", lambda: plugin)
        resp = _client(db_with_features, llm=_StubLLM()).post(
            "/api/features/recommend", json={"use_case": "churn prediction"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["method"] == "tfidf"
        assert "no matches" in (body["summary"] or "").lower()

    def test_llm_exception_falls_back_to_tfidf(
        self, db_with_features: LocalBackend, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        plugin = _MockDiscoveryPlugin(mode="raise")
        monkeypatch.setattr("featcat.plugins.discovery.DiscoveryPlugin", lambda: plugin)
        resp = _client(db_with_features, llm=_StubLLM()).post(
            "/api/features/recommend", json={"use_case": "churn prediction"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["method"] == "tfidf"
        assert "LLM error" in (body["summary"] or "")

    def test_exclude_ids_drops_matches_and_refills_top_k(self, db_with_features: LocalBackend) -> None:
        # Find the id of the most relevant match without exclusion.
        baseline = _client(db_with_features, llm=None).post(
            "/api/features/recommend", json={"use_case": "user behavior", "top_k": 2}
        )
        assert baseline.status_code == 200
        baseline_matches = baseline.json()["matches"]
        assert baseline_matches, "TF-IDF should return at least one match"
        excluded_id = baseline_matches[0]["feature"]["id"]
        excluded_name = baseline_matches[0]["feature"]["name"]

        # Re-issue with exclude_ids — top match must change, top_k still respected.
        resp = _client(db_with_features, llm=None).post(
            "/api/features/recommend",
            json={"use_case": "user behavior", "top_k": 2, "exclude_ids": [excluded_id]},
        )
        assert resp.status_code == 200
        body = resp.json()
        names = [m["feature"]["name"] for m in body["matches"]]
        assert excluded_name not in names
        # We seeded 3 features; excluding one should still allow up to 2 matches when relevant.
        assert len(body["matches"]) <= 2

    def test_exclude_ids_changes_cache_key(
        self, db_with_features: LocalBackend, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        # Two different exclude_ids sets should return different responses (no cross-pollination).
        plugin = _MockDiscoveryPlugin(
            mode="ok",
            existing=[
                {"name": "src.user_churn_score", "relevance": 0.9},
                {"name": "src.user_session_count", "relevance": 0.8},
            ],
        )
        monkeypatch.setattr("featcat.plugins.discovery.DiscoveryPlugin", lambda: plugin)
        client = _client(db_with_features, llm=_StubLLM())

        # First request: no exclusion. Cache populated with both matches.
        first = client.post("/api/features/recommend", json={"use_case": "user behavior"})
        assert first.status_code == 200
        first_names = {m["feature"]["name"] for m in first.json()["matches"]}
        assert "src.user_churn_score" in first_names

        # Second request: exclude churn — must miss the previous cache entry and drop churn.
        churn_id = db_with_features.get_feature_by_name("src.user_churn_score").id  # type: ignore[union-attr]
        second = client.post(
            "/api/features/recommend",
            json={"use_case": "user behavior", "exclude_ids": [churn_id]},
        )
        assert second.status_code == 200
        second_names = {m["feature"]["name"] for m in second.json()["matches"]}
        assert "src.user_churn_score" not in second_names

    @pytest.mark.timeout(20)
    def test_llm_timeout_falls_back_to_tfidf(
        self,
        db_with_features: LocalBackend,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        # Drop the 8s internal timeout to 0.1s so we don't actually sleep 8s.
        monkeypatch.setattr("featcat.server.routes.features._RECOMMEND_LLM_TIMEOUT_S", 0.1, raising=False)
        plugin = _MockDiscoveryPlugin(mode="slow")
        monkeypatch.setattr("featcat.plugins.discovery.DiscoveryPlugin", lambda: plugin)
        resp = _client(db_with_features, llm=_StubLLM()).post(
            "/api/features/recommend", json={"use_case": "churn prediction"}
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["method"] == "tfidf"
        assert "timed out" in (body["summary"] or "").lower()
