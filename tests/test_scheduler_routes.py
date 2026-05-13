"""Tests for the unified job-status API at /api/scheduler/* (T1.5c).

Two layers covered here:

1. APScheduler-only (default backend) — list/detail/runs/trigger flow with
   the in-process scheduler. No celery dependency required at runtime,
   though the celery client is imported indirectly via the trigger path
   for the celery-backend test below.
2. Celery dispatch — gated with ``pytest.importorskip('celery')`` so the
   suite still runs (and skips these) when the ``[tasks]`` extra isn't
   installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest import mock

import pytest
from fastapi.testclient import TestClient

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture()
def client(tmp_path: Path, monkeypatch):
    """Build a TestClient against the real app + a tmp SQLite db.

    The scheduler is started by the lifespan, but its APScheduler thread
    isn't given a chance to fire — TestClient drives the lifespan, then
    every request is served on the same event loop.
    """
    db_path = str(tmp_path / "sched.db")
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)
    monkeypatch.setenv("FEATCAT_TASKS_BACKEND", "apscheduler")

    from featcat.server import create_app

    app = create_app()
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# Listing + detail
# ---------------------------------------------------------------------------


class TestListJobs:
    def test_returns_four_default_jobs_with_no_runs(self, client: TestClient) -> None:
        resp = client.get("/api/scheduler/jobs")
        assert resp.status_code == 200
        body = resp.json()
        names = sorted(j["name"] for j in body)
        assert names == ["baseline_refresh", "doc_generate", "monitor_check", "source_scan"]
        for j in body:
            assert j["backend"] == "apscheduler"
            assert j["enabled"] is True
            assert j["last_status"] is None
            assert j["last_run_at"] is None

    def test_backend_field_reflects_settings(self, client: TestClient, monkeypatch) -> None:
        # Mutate the live settings on the app — simpler than rebuilding.
        client.app.state.settings.tasks_backend = "celery"  # type: ignore[attr-defined]
        try:
            resp = client.get("/api/scheduler/jobs")
            assert resp.status_code == 200
            for j in resp.json():
                assert j["backend"] == "celery"
        finally:
            client.app.state.settings.tasks_backend = "apscheduler"  # type: ignore[attr-defined]


class TestJobDetail:
    def test_includes_recent_runs(self, client: TestClient) -> None:
        # Seed a single run via the scheduler so detail has history.
        scheduler = client.app.state.scheduler  # type: ignore[attr-defined]
        import asyncio

        asyncio.new_event_loop().run_until_complete(scheduler.run_job("baseline_refresh", triggered_by="manual"))

        resp = client.get("/api/scheduler/jobs/baseline_refresh")
        assert resp.status_code == 200
        body = resp.json()
        assert body["name"] == "baseline_refresh"
        assert body["backend"] == "apscheduler"
        assert body["last_status"] in ("success", "warning")
        assert body["last_run_at"] is not None
        assert isinstance(body["recent_runs"], list)
        assert len(body["recent_runs"]) == 1
        assert body["recent_runs"][0]["job_name"] == "baseline_refresh"
        # APScheduler path should never report Celery task ids.
        assert body["active_celery_task_ids"] == []

    def test_404_for_unknown_job(self, client: TestClient) -> None:
        resp = client.get("/api/scheduler/jobs/totally_made_up")
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Trigger
# ---------------------------------------------------------------------------


class TestTriggerApscheduler:
    def test_creates_job_log_row_and_returns_handle(self, client: TestClient) -> None:
        resp = client.post("/api/scheduler/jobs/baseline_refresh/run", json={})
        assert resp.status_code == 200
        body = resp.json()
        assert body["status"] == "running"
        assert body["celery_task_id"] is None
        assert body["job_log_id"]

        # The log row must be visible via /runs immediately, even before
        # the background task finishes.
        runs = client.get("/api/scheduler/runs?job=baseline_refresh").json()
        ids = [r["id"] for r in runs]
        assert body["job_log_id"] in ids

    def test_404_for_unknown_job(self, client: TestClient) -> None:
        resp = client.post("/api/scheduler/jobs/no_such/run", json={})
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Runs (history) endpoint
# ---------------------------------------------------------------------------


class TestRunsHistory:
    def test_filters_by_job_and_limit(self, client: TestClient) -> None:
        scheduler = client.app.state.scheduler  # type: ignore[attr-defined]
        import asyncio

        loop = asyncio.new_event_loop()
        loop.run_until_complete(scheduler.run_job("baseline_refresh", triggered_by="manual"))
        loop.run_until_complete(scheduler.run_job("baseline_refresh", triggered_by="manual"))
        loop.close()

        all_runs = client.get("/api/scheduler/runs?limit=10").json()
        assert len(all_runs) >= 2

        filtered = client.get("/api/scheduler/runs?job=baseline_refresh&limit=1").json()
        assert len(filtered) == 1
        assert filtered[0]["job_name"] == "baseline_refresh"

    def test_filters_by_since_timestamp(self, client: TestClient) -> None:
        from datetime import datetime, timedelta, timezone

        scheduler = client.app.state.scheduler  # type: ignore[attr-defined]
        import asyncio

        asyncio.new_event_loop().run_until_complete(scheduler.run_job("baseline_refresh", triggered_by="manual"))
        future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
        # Use params= so the '+' inside the timezone offset is URL-encoded
        # rather than collapsed to a space by the query-string parser.
        runs = client.get("/api/scheduler/runs", params={"since": future}).json()
        assert runs == []


# ---------------------------------------------------------------------------
# Celery branch — gated.
# ---------------------------------------------------------------------------


celery = pytest.importorskip("celery")


class TestTriggerCelery:
    """When tasks_backend=celery, /run must call send_task and return the
    Celery task id alongside the job_log id.
    """

    def test_dispatches_via_send_task(self, client: TestClient) -> None:
        client.app.state.settings.tasks_backend = "celery"  # type: ignore[attr-defined]
        try:
            from featcat.tasks.app import app as celery_app

            # Patch send_task so we don't need a live broker.
            fake_async_result = mock.Mock(id="celery-task-abc")
            with mock.patch.object(celery_app, "send_task", return_value=fake_async_result) as send:
                resp = client.post(
                    "/api/scheduler/jobs/monitor_check/run",
                    json={"kwargs": {"foo": "bar"}},
                )
                assert resp.status_code == 200
                body = resp.json()
                assert body["status"] == "queued"
                assert body["celery_task_id"] == "celery-task-abc"
                send.assert_called_once_with(
                    "featcat.tasks.monitoring.monitor_check",
                    kwargs={"foo": "bar"},
                )
        finally:
            client.app.state.settings.tasks_backend = "apscheduler"  # type: ignore[attr-defined]

    def test_active_task_ids_degrades_when_redis_unreachable(self, client: TestClient) -> None:
        """The detail endpoint must not blow up when inspect() raises —
        Redis-down should look like 'no active tasks', not a 500.
        """
        client.app.state.settings.tasks_backend = "celery"  # type: ignore[attr-defined]
        try:
            from featcat.tasks.app import app as celery_app

            # Make inspect().active() blow up like a broken broker would.
            broken_inspector = mock.Mock()
            broken_inspector.active.side_effect = ConnectionRefusedError("redis down")
            broken_inspector.reserved.side_effect = ConnectionRefusedError("redis down")
            with mock.patch.object(celery_app.control, "inspect", return_value=broken_inspector):
                resp = client.get("/api/scheduler/jobs/monitor_check")
            assert resp.status_code == 200
            assert resp.json()["active_celery_task_ids"] == []
        finally:
            client.app.state.settings.tasks_backend = "apscheduler"  # type: ignore[attr-defined]
