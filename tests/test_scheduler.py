"""Tests for the job scheduler."""

from __future__ import annotations

from datetime import datetime

import pytest

pytest.importorskip("apscheduler")

from featcat.catalog.local import LocalBackend
from featcat.config import load_settings


@pytest.fixture
def backend(tmp_path):
    db = LocalBackend(str(tmp_path / "test.db"))
    db.init_db()
    return db


@pytest.fixture
def scheduler(backend):
    from featcat.server.scheduler import FeatcatScheduler

    settings = load_settings()
    s = FeatcatScheduler(backend=backend, llm=None, settings=settings)
    return s


class TestSchedulerSetup:
    def test_setup_seeds_default_jobs(self, scheduler, backend):
        scheduler.setup_default_jobs()
        schedules = scheduler.get_schedules()
        names = [s["job_name"] for s in schedules]
        assert "monitor_check" in names
        assert "doc_generate" in names
        assert "source_scan" in names
        assert "baseline_refresh" in names

    def test_setup_does_not_duplicate_on_second_call(self, scheduler, backend):
        scheduler.setup_default_jobs()
        scheduler.setup_default_jobs()
        schedules = scheduler.get_schedules()
        assert len(schedules) == 4

    def test_get_schedules_returns_dicts(self, scheduler):
        scheduler.setup_default_jobs()
        schedules = scheduler.get_schedules()
        assert isinstance(schedules[0], dict)
        assert "job_name" in schedules[0]
        assert "cron_expression" in schedules[0]
        assert "enabled" in schedules[0]


class TestSchedulerUpdate:
    def test_update_cron(self, scheduler):
        scheduler.setup_default_jobs()
        scheduler.update_schedule("monitor_check", cron="0 */2 * * *", enabled=None)
        schedules = scheduler.get_schedules()
        mc = next(s for s in schedules if s["job_name"] == "monitor_check")
        assert mc["cron_expression"] == "0 */2 * * *"

    def test_disable_job(self, scheduler):
        scheduler.setup_default_jobs()
        scheduler.update_schedule("monitor_check", cron=None, enabled=False)
        schedules = scheduler.get_schedules()
        mc = next(s for s in schedules if s["job_name"] == "monitor_check")
        assert mc["enabled"] == 0


class TestJobExecution:
    @pytest.mark.asyncio
    async def test_run_job_creates_log(self, scheduler):
        scheduler.setup_default_jobs()
        result = await scheduler.run_job("baseline_refresh", triggered_by="manual")
        assert result["status"] in ("success", "warning")
        assert result["job_name"] == "baseline_refresh"

        logs = scheduler.get_logs(job_name="baseline_refresh")
        assert len(logs) == 1
        assert logs[0]["triggered_by"] == "manual"
        assert logs[0]["status"] in ("success", "warning")
        assert logs[0]["duration_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_run_invalid_job(self, scheduler):
        scheduler.setup_default_jobs()
        result = await scheduler.run_job("nonexistent", triggered_by="manual")
        assert result["status"] == "failed"
        assert "Unknown job" in result["error_message"]


class TestLogRetention:
    @pytest.mark.asyncio
    async def test_purge_old_logs(self, scheduler, backend):
        scheduler.setup_default_jobs()
        await scheduler.run_job("baseline_refresh", triggered_by="manual")
        logs = scheduler.get_logs()
        assert len(logs) == 1

        # Artificially age the log using Python adapter for consistent datetime format
        from datetime import timedelta, timezone

        old_ts = (datetime.now(timezone.utc) - timedelta(days=60)).isoformat()
        backend.conn.execute("UPDATE job_logs SET started_at = ?", (old_ts,))
        backend.conn.commit()

        # Set short retention
        backend.conn.execute("UPDATE job_schedules SET max_log_retention_days = 1 WHERE job_name = 'baseline_refresh'")
        backend.conn.commit()

        scheduler.purge_old_logs("baseline_refresh")
        logs = scheduler.get_logs()
        assert len(logs) == 0


class TestJobStats:
    @pytest.mark.asyncio
    async def test_get_stats(self, scheduler):
        scheduler.setup_default_jobs()
        await scheduler.run_job("baseline_refresh", triggered_by="manual")
        stats = scheduler.get_stats()
        assert "jobs" in stats
        assert "baseline_refresh" in stats["jobs"]
        br = stats["jobs"]["baseline_refresh"]
        assert br["total_runs"] == 1
        assert "sparkline" in br
        assert len(br["sparkline"]) == 7
