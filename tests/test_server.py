"""Tests for the featcat API server."""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from fastapi import HTTPException

from featcat.config import load_settings
from featcat.server.routes.ai import AskRequest, DiscoverRequest, ask, discover
from featcat.server.routes.docs import doc_stats, get_doc_by_name
from featcat.server.routes.features import get_feature_by_name, health_summary, list_features
from featcat.server.routes.health import health
from featcat.server.routes.monitor import compute_baseline, monitoring_report, run_check
from featcat.server.routes.sources import SourceCreate, add_source, get_source, list_sources


class FakeCatalog:
    def __init__(self) -> None:
        self.sources: dict[str, object] = {}

    def get_catalog_stats(self):
        return {"sources": len(self.sources), "features": 0}

    def add_source(self, source):
        self.sources[source.name] = source
        return source

    def list_sources(self):
        return list(self.sources.values())

    def get_source_by_name(self, name: str):
        return self.sources.get(name)

    def list_features(self, **kwargs):
        return []

    def get_feature_by_name(self, name: str):
        return None

    def get_all_feature_docs(self):
        return {}

    def get_doc_stats(self):
        return {"documented": 0, "undocumented": 0}


class FakeMonitoringPlugin:
    def execute(self, db, llm, **kwargs):
        action = kwargs.get("action", "check")
        if action == "baseline":
            return SimpleNamespace(data={"baselines_saved": 0, "total_features": 0})
        return SimpleNamespace(
            data={
                "timestamp": "2026-01-01T00:00:00Z",
                "total_features": 0,
                "checked": 0,
                "healthy": 0,
                "warnings": 0,
                "critical": 0,
                "unknown": 0,
                "details": [],
            }
        )


class FakeNLQueryPlugin:
    def execute(self, db, llm, **kwargs):
        return SimpleNamespace(data={"results": [], "interpretation": "fallback", "method": "fallback"})


@pytest.fixture()
def db(tmp_path: Path) -> FakeCatalog:
    return FakeCatalog()


@pytest.fixture(autouse=True)
def _stubs(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("featcat.server.routes.sources.cache_get", lambda *args, **kwargs: None)
    monkeypatch.setattr("featcat.server.routes.sources.cache_set", lambda *args, **kwargs: None)
    monkeypatch.setattr("featcat.server.routes.sources.invalidate", lambda *args, **kwargs: None)
    monkeypatch.setattr("featcat.server.routes.monitor.cache_get", lambda *args, **kwargs: None)
    monkeypatch.setattr("featcat.server.routes.monitor.cache_set", lambda *args, **kwargs: None)
    monkeypatch.setattr("featcat.server.routes.monitor.invalidate", lambda *args, **kwargs: None)
    monkeypatch.setattr("featcat.server.routes.docs.get_glossary", lambda: {"ok": True})
    monkeypatch.setattr("featcat.plugins.autodoc.get_doc", lambda db, name: None)
    monkeypatch.setattr("featcat.plugins.monitoring.MonitoringPlugin", FakeMonitoringPlugin)
    monkeypatch.setattr("featcat.plugins.nl_query.NLQueryPlugin", FakeNLQueryPlugin)

    async def _run_in_threadpool(fn, *args, **kwargs):
        return fn(*args, **kwargs)

    monkeypatch.setattr("featcat.server.routes.monitor.run_in_threadpool", _run_in_threadpool)
    monkeypatch.setattr("featcat.server.routes.ai.run_in_threadpool", _run_in_threadpool)
    monkeypatch.setattr("featcat.server.routes.docs.run_in_threadpool", _run_in_threadpool)


def _settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", str(tmp_path / "test.db"))
    monkeypatch.setenv("FEATCAT_LLM_BACKEND", "disabled")
    monkeypatch.setenv("FEATCAT_SCHEDULER_ENABLED", "false")
    return load_settings()


def test_health(db: FakeCatalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path, monkeypatch)

    def _run_group(name: str, **kwargs):
        from featcat.diagnostics.models import CheckResult, CheckStatus, GroupReport

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

    payload = health(db=db, llm=None, settings=settings)
    assert payload["status"] in ("ok", "degraded")
    assert payload["db"] is True
    assert "checks" in payload


def test_stats(db: FakeCatalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(tmp_path, monkeypatch)
    assert doc_stats(db=db) == {"documented": 0, "undocumented": 0}


def test_list_sources_empty(db: FakeCatalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(tmp_path, monkeypatch)
    assert list_sources(db=db) == []


def test_add_and_get_source(db: FakeCatalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(tmp_path, monkeypatch)
    source_path = tmp_path / "data.parquet"
    source_path.write_text("", encoding="utf-8")
    resp = add_source(
        SourceCreate(name="test-src", path=str(source_path), storage_type="local", format="parquet"),
        db=db,
    )
    assert resp["name"] == "test-src"
    assert list_sources(db=db)[0]["name"] == "test-src"
    got = get_source("test-src", db=db)
    assert got["name"] == "test-src"


def test_get_missing_source(db: FakeCatalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(tmp_path, monkeypatch)
    with pytest.raises(HTTPException) as exc:
        get_source("nonexistent", db=db)
    assert exc.value.status_code == 404


def test_list_features_empty(db: FakeCatalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(tmp_path, monkeypatch)
    assert list_features(db=db, limit=None) == []


def test_get_missing_feature(db: FakeCatalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(tmp_path, monkeypatch)
    with pytest.raises(HTTPException) as exc:
        get_feature_by_name(name="nonexistent", db=db)
    assert exc.value.status_code == 404


def test_health_summary_empty(db: FakeCatalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(tmp_path, monkeypatch)
    payload = health_summary(db=db)
    assert payload["grade_distribution"] == {"A": 0, "B": 0, "C": 0, "D": 0}
    assert payload["average_score"] == 0
    assert payload["lowest_scored"] == []
    assert payload["improvement_opportunities"] == []


def test_docs_missing_doc(db: FakeCatalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(tmp_path, monkeypatch)
    assert get_doc_by_name(name="nonexistent", db=db) is None


def test_monitor_endpoints(db: FakeCatalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _settings(tmp_path, monkeypatch)

    baseline = asyncio.run(compute_baseline(db=db))
    assert baseline == {"baselines_saved": 0, "total_features": 0}

    report = asyncio.run(monitoring_report(db=db))
    assert report["total_features"] == 0

    check = asyncio.run(run_check(db=db, llm=None))
    assert check["checked"] == 0


def test_ai_endpoints(db: FakeCatalog, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = _settings(tmp_path, monkeypatch)
    ask_result = asyncio.run(ask(AskRequest(query="test"), db=db, llm=None))
    assert ask_result["method"] == "fallback"

    with pytest.raises(HTTPException) as exc:
        asyncio.run(discover(DiscoverRequest(use_case="churn prediction"), db=db, llm=None, settings=settings))
    assert exc.value.status_code == 503
