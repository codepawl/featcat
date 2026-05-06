"""Internal job scheduler for the featcat server.

Phase 3 of the SQLite → PostgreSQL migration: this module previously used
``backend.conn.execute("…?", (…))`` against the raw sqlite3 connection. All
22 callsites are now ported to ``backend.session()`` + ``text("…:name")`` so
the scheduler runs identically against either backend.
"""

from __future__ import annotations

import contextlib
import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

if TYPE_CHECKING:
    from ..catalog.local import LocalBackend
    from ..config import Settings

DEFAULT_JOBS = [
    {"job_name": "monitor_check", "description": "Check all features for drift", "max_log_retention_days": 30},
    {
        "job_name": "doc_generate",
        "description": "Generate docs for undocumented features",
        "max_log_retention_days": 30,
    },
    {"job_name": "source_scan", "description": "Re-scan auto_refresh sources", "max_log_retention_days": 30},
    {"job_name": "baseline_refresh", "description": "Refresh monitoring baselines", "max_log_retention_days": 60},
]

_CRON_CONFIG_MAP = {
    "monitor_check": "job_monitor_check_cron",
    "doc_generate": "job_doc_generate_cron",
    "source_scan": "job_source_scan_cron",
    "baseline_refresh": "job_baseline_refresh_cron",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FeatcatScheduler:
    """Manages scheduled jobs, execution, and logging."""

    def __init__(self, backend: LocalBackend, llm: Any, settings: Settings) -> None:
        self.backend = backend
        self.llm = llm
        self.settings = settings
        self._apscheduler = None

    def setup_default_jobs(self) -> None:
        """Seed job_schedules with defaults if table is empty."""
        with self.backend.session() as s:
            count = s.execute(text("SELECT COUNT(*) FROM job_schedules")).scalar() or 0
            if count > 0:
                return
            for job in DEFAULT_JOBS:
                cron_field = _CRON_CONFIG_MAP[job["job_name"]]
                cron = getattr(self.settings, cron_field)
                s.execute(
                    text(
                        "INSERT INTO job_schedules "
                        "(job_name, cron_expression, enabled, description, max_log_retention_days) "
                        "VALUES (:name, :cron, 1, :desc, :ret)"
                    ),
                    {
                        "name": job["job_name"],
                        "cron": cron,
                        "desc": job["description"],
                        "ret": job["max_log_retention_days"],
                    },
                )
            s.commit()

    def start(self) -> None:
        """Start the APScheduler with registered jobs."""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        self._apscheduler = AsyncIOScheduler()
        for schedule in self.get_schedules():
            if not schedule["enabled"]:
                continue
            trigger = CronTrigger.from_crontab(schedule["cron_expression"])
            self._apscheduler.add_job(
                self.run_job,
                trigger=trigger,
                args=[schedule["job_name"]],
                kwargs={"triggered_by": "scheduler"},
                id=schedule["job_name"],
                replace_existing=True,
            )
        self._apscheduler.start()

    def stop(self) -> None:
        if self._apscheduler:
            self._apscheduler.shutdown(wait=False)

    def get_schedules(self) -> list[dict]:
        with self.backend.session() as s:
            rows = s.execute(text("SELECT * FROM job_schedules ORDER BY job_name")).mappings().all()
            return [dict(row) for row in rows]

    def update_schedule(self, job_name: str, cron: str | None, enabled: bool | None) -> None:
        with self.backend.session() as s:
            if cron is not None:
                s.execute(
                    text("UPDATE job_schedules SET cron_expression = :cron WHERE job_name = :name"),
                    {"cron": cron, "name": job_name},
                )
            if enabled is not None:
                s.execute(
                    text("UPDATE job_schedules SET enabled = :enabled WHERE job_name = :name"),
                    {"enabled": 1 if enabled else 0, "name": job_name},
                )
            s.commit()

        # Sync live APScheduler with updated state. Re-fetch via Session so
        # we observe the just-committed values.
        if self._apscheduler is not None:
            from apscheduler.triggers.cron import CronTrigger

            if enabled is False:
                with contextlib.suppress(Exception):
                    self._apscheduler.remove_job(job_name)
            elif enabled is True:
                with self.backend.session() as s:
                    row = s.execute(
                        text("SELECT cron_expression FROM job_schedules WHERE job_name = :name"),
                        {"name": job_name},
                    ).first()
                if row:
                    trigger = CronTrigger.from_crontab(row[0])
                    self._apscheduler.add_job(
                        self.run_job,
                        trigger=trigger,
                        args=[job_name],
                        kwargs={"triggered_by": "scheduler"},
                        id=job_name,
                        replace_existing=True,
                    )
            elif cron is not None:
                with contextlib.suppress(Exception):
                    self._apscheduler.remove_job(job_name)
                with self.backend.session() as s:
                    row = s.execute(
                        text("SELECT enabled FROM job_schedules WHERE job_name = :name"),
                        {"name": job_name},
                    ).first()
                if row and row[0]:
                    trigger = CronTrigger.from_crontab(cron)
                    self._apscheduler.add_job(
                        self.run_job,
                        trigger=trigger,
                        args=[job_name],
                        kwargs={"triggered_by": "scheduler"},
                        id=job_name,
                        replace_existing=True,
                    )

    async def run_job(self, job_name: str, triggered_by: str = "scheduler") -> dict:
        """Execute a job by name, logging start/finish to job_logs."""
        # Skip disabled jobs when triggered by scheduler (manual/API runs always execute)
        if triggered_by == "scheduler":
            with self.backend.session() as s:
                row = s.execute(
                    text("SELECT enabled FROM job_schedules WHERE job_name = :name"),
                    {"name": job_name},
                ).first()
            if row and not row[0]:
                return {"job_name": job_name, "status": "skipped", "reason": "Job is disabled"}

        log_id = str(uuid.uuid4())
        started_at = _utcnow()
        with self.backend.session() as s:
            s.execute(
                text(
                    "INSERT INTO job_logs (id, job_name, status, started_at, triggered_by) "
                    "VALUES (:id, :name, 'running', :started, :by)"
                ),
                {"id": log_id, "name": job_name, "started": started_at, "by": triggered_by},
            )
            s.commit()

        start_time = time.monotonic()
        try:
            result_summary = await self._execute(job_name)
            status = "success"
            error_message = None
        except ValueError as exc:
            status = "failed"
            result_summary = {}
            error_message = str(exc)
        except Exception as exc:
            status = "failed"
            result_summary = {}
            error_message = f"{type(exc).__name__}: {exc}"

        duration = time.monotonic() - start_time
        finished_at = _utcnow()
        with self.backend.session() as s:
            s.execute(
                text(
                    "UPDATE job_logs SET status = :status, finished_at = :finished, "
                    "  duration_seconds = :duration, result_summary = :summary, "
                    "  error_message = :err WHERE id = :id"
                ),
                {
                    "status": status,
                    "finished": finished_at,
                    "duration": round(duration, 2),
                    "summary": json.dumps(result_summary),
                    "err": error_message,
                    "id": log_id,
                },
            )
            s.execute(
                text("UPDATE job_schedules SET last_run_at = :finished WHERE job_name = :name"),
                {"finished": finished_at, "name": job_name},
            )
            s.commit()
        self.purge_old_logs(job_name)

        return {
            "id": log_id,
            "job_name": job_name,
            "status": status,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": round(duration, 2),
            "result_summary": result_summary,
            "error_message": error_message,
            "triggered_by": triggered_by,
        }

    async def _execute(self, job_name: str) -> dict:
        from starlette.concurrency import run_in_threadpool

        if job_name == "monitor_check":
            return await run_in_threadpool(self._run_monitor_check)
        if job_name == "doc_generate":
            return await run_in_threadpool(self._run_doc_generate)
        if job_name == "source_scan":
            return await run_in_threadpool(self._run_source_scan)
        if job_name == "baseline_refresh":
            return await run_in_threadpool(self._run_baseline_refresh)
        raise ValueError(f"Unknown job: {job_name}")

    def _run_monitor_check(self) -> dict:
        from ..plugins.monitoring import MonitoringPlugin

        plugin = MonitoringPlugin()
        result = plugin.execute(self.backend, self.llm, action="check")
        return result.data

    def _run_doc_generate(self) -> dict:
        if self.llm is None:
            return {"documented": 0, "message": "LLM not available, skipped"}
        from ..plugins.autodoc import AutodocPlugin

        plugin = AutodocPlugin()
        result = plugin.execute(self.backend, self.llm)
        return result.data

    def _run_source_scan(self) -> dict:
        from ..catalog.models import Feature
        from ..catalog.scanner import scan_source

        sources = self.backend.list_sources()
        total_features = 0
        scanned = 0
        with self.backend.session() as s:
            for source in sources:
                row = s.execute(
                    text("SELECT auto_refresh FROM data_sources WHERE id = :id"),
                    {"id": source.id},
                ).first()
                if not row or not row[0]:
                    continue
                columns = scan_source(source.path)
                for col in columns:
                    feature = Feature(
                        name=f"{source.name}.{col.column_name}",
                        data_source_id=source.id,
                        column_name=col.column_name,
                        dtype=col.dtype,
                        stats=col.stats,
                    )
                    self.backend.upsert_feature(feature)
                    total_features += 1
                scanned += 1
        return {"sources_scanned": scanned, "features_updated": total_features}

    def _run_baseline_refresh(self) -> dict:
        from ..plugins.monitoring import MonitoringPlugin

        plugin = MonitoringPlugin()
        result = plugin.execute(self.backend, None, action="baseline")
        return result.data

    def get_logs(
        self,
        job_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses: list[str] = ["1=1"]
        params: dict[str, Any] = {"lim": limit, "off": offset}
        if job_name:
            clauses.append("job_name = :name")
            params["name"] = job_name
        if status:
            clauses.append("status = :status")
            params["status"] = status
        sql = (
            f"SELECT * FROM job_logs WHERE {' AND '.join(clauses)} "  # noqa: S608
            f"ORDER BY started_at DESC LIMIT :lim OFFSET :off"
        )
        with self.backend.session() as s:
            rows = s.execute(text(sql), params).mappings().all()
        result = []
        for row in rows:
            d = dict(row)
            if isinstance(d.get("result_summary"), str):
                d["result_summary"] = json.loads(d["result_summary"])
            result.append(d)
        return result

    def get_log(self, log_id: str) -> dict | None:
        with self.backend.session() as s:
            row = s.execute(text("SELECT * FROM job_logs WHERE id = :id"), {"id": log_id}).mappings().first()
        if row is None:
            return None
        d = dict(row)
        if isinstance(d.get("result_summary"), str):
            d["result_summary"] = json.loads(d["result_summary"])
        return d

    def purge_old_logs(self, job_name: str) -> int:
        with self.backend.session() as s:
            row = s.execute(
                text("SELECT max_log_retention_days FROM job_schedules WHERE job_name = :name"),
                {"name": job_name},
            ).first()
            if row is None:
                return 0
            cutoff = _utcnow() - timedelta(days=row[0])
            result = s.execute(
                text("DELETE FROM job_logs WHERE job_name = :name AND started_at < :cutoff"),
                {"name": job_name, "cutoff": cutoff},
            )
            s.commit()
            return result.rowcount  # type: ignore[attr-defined]

    def get_stats(self) -> dict:
        schedules = self.get_schedules()
        result: dict[str, Any] = {"jobs": {}}
        with self.backend.session() as s:
            for sched in schedules:
                name = sched["job_name"]
                total = (
                    s.execute(
                        text("SELECT COUNT(*) FROM job_logs WHERE job_name = :name AND status != 'running'"),
                        {"name": name},
                    ).scalar()
                    or 0
                )
                successes = (
                    s.execute(
                        text("SELECT COUNT(*) FROM job_logs WHERE job_name = :name AND status = 'success'"),
                        {"name": name},
                    ).scalar()
                    or 0
                )
                avg_dur = s.execute(
                    text("SELECT AVG(duration_seconds) FROM job_logs WHERE job_name = :name AND status != 'running'"),
                    {"name": name},
                ).scalar()
                last_row = s.execute(
                    text(
                        "SELECT status FROM job_logs WHERE job_name = :name AND status != 'running' "
                        "ORDER BY started_at DESC LIMIT 1"
                    ),
                    {"name": name},
                ).first()

                sparkline = []
                today = _utcnow().date()
                for days_ago in range(6, -1, -1):
                    day = today - timedelta(days=days_ago)
                    day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
                    day_end = day_start + timedelta(days=1)
                    counts: dict[str, Any] = {
                        "date": day.isoformat(),
                        "success": 0,
                        "failed": 0,
                        "warning": 0,
                    }
                    rows = (
                        s.execute(
                            text(
                                "SELECT status, COUNT(*) as cnt FROM job_logs "
                                "WHERE job_name = :name AND started_at >= :ds AND started_at < :de "
                                "  AND status != 'running' GROUP BY status"
                            ),
                            {"name": name, "ds": day_start, "de": day_end},
                        )
                        .mappings()
                        .all()
                    )
                    for r in rows:
                        if r["status"] in counts:
                            counts[r["status"]] = r["cnt"]
                    sparkline.append(counts)

                result["jobs"][name] = {
                    "total_runs": total,
                    "success_rate": round(successes / total, 2) if total > 0 else 0.0,
                    "avg_duration_seconds": round(avg_dur, 2) if avg_dur else 0.0,
                    "last_status": last_row[0] if last_row else None,
                    "sparkline": sparkline,
                }
        return result
