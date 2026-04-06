"""Internal job scheduler for the featcat server."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

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
        conn = self.backend.conn
        count = conn.execute("SELECT COUNT(*) FROM job_schedules").fetchone()[0]
        if count > 0:
            return
        for job in DEFAULT_JOBS:
            cron_field = _CRON_CONFIG_MAP[job["job_name"]]
            cron = getattr(self.settings, cron_field)
            conn.execute(
                "INSERT INTO job_schedules"
                " (job_name, cron_expression, enabled, description, max_log_retention_days)"
                " VALUES (?, ?, 1, ?, ?)",
                (job["job_name"], cron, job["description"], job["max_log_retention_days"]),
            )
        conn.commit()

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
        """Stop the APScheduler if running."""
        if self._apscheduler:
            self._apscheduler.shutdown(wait=False)

    def get_schedules(self) -> list[dict]:
        """Return all job schedules as a list of dicts."""
        rows = self.backend.conn.execute(
            "SELECT * FROM job_schedules ORDER BY job_name"
        ).fetchall()
        return [dict(row) for row in rows]

    def update_schedule(self, job_name: str, cron: str | None, enabled: bool | None) -> None:
        """Update cron expression and/or enabled flag for a job."""
        conn = self.backend.conn
        if cron is not None:
            conn.execute(
                "UPDATE job_schedules SET cron_expression = ? WHERE job_name = ?",
                (cron, job_name),
            )
        if enabled is not None:
            conn.execute(
                "UPDATE job_schedules SET enabled = ? WHERE job_name = ?",
                (1 if enabled else 0, job_name),
            )
        conn.commit()

    async def run_job(self, job_name: str, triggered_by: str = "scheduler") -> dict:
        """Execute a job by name, logging start/finish to job_logs."""
        log_id = str(uuid.uuid4())
        started_at = _utcnow()
        conn = self.backend.conn
        conn.execute(
            "INSERT INTO job_logs (id, job_name, status, started_at, triggered_by)"
            " VALUES (?, ?, 'running', ?, ?)",
            (log_id, job_name, started_at, triggered_by),
        )
        conn.commit()

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
        conn.execute(
            "UPDATE job_logs SET status = ?, finished_at = ?, duration_seconds = ?,"
            " result_summary = ?, error_message = ? WHERE id = ?",
            (status, finished_at, round(duration, 2), json.dumps(result_summary), error_message, log_id),
        )
        conn.execute(
            "UPDATE job_schedules SET last_run_at = ? WHERE job_name = ?",
            (finished_at, job_name),
        )
        conn.commit()
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
        """Dispatch to the appropriate job handler."""
        if job_name == "monitor_check":
            return self._run_monitor_check()
        if job_name == "doc_generate":
            return self._run_doc_generate()
        if job_name == "source_scan":
            return self._run_source_scan()
        if job_name == "baseline_refresh":
            return self._run_baseline_refresh()
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
        for source in sources:
            row = self.backend.conn.execute(
                "SELECT auto_refresh FROM data_sources WHERE id = ?", (source.id,)
            ).fetchone()
            if not row or not row["auto_refresh"]:
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
        """Query job_logs with optional filters."""
        query = "SELECT * FROM job_logs WHERE 1=1"
        params: list[Any] = []
        if job_name:
            query += " AND job_name = ?"
            params.append(job_name)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])
        rows = self.backend.conn.execute(query, params).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if isinstance(d.get("result_summary"), str):
                d["result_summary"] = json.loads(d["result_summary"])
            result.append(d)
        return result

    def get_log(self, log_id: str) -> dict | None:
        """Return a single job log by id."""
        row = self.backend.conn.execute(
            "SELECT * FROM job_logs WHERE id = ?", (log_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        if isinstance(d.get("result_summary"), str):
            d["result_summary"] = json.loads(d["result_summary"])
        return d

    def purge_old_logs(self, job_name: str) -> int:
        """Delete logs older than the retention period for a given job."""
        row = self.backend.conn.execute(
            "SELECT max_log_retention_days FROM job_schedules WHERE job_name = ?",
            (job_name,),
        ).fetchone()
        if row is None:
            return 0
        cutoff = _utcnow() - timedelta(days=row["max_log_retention_days"])
        cursor = self.backend.conn.execute(
            "DELETE FROM job_logs WHERE job_name = ? AND started_at < ?",
            (job_name, cutoff),
        )
        self.backend.conn.commit()
        return cursor.rowcount

    def get_stats(self) -> dict:
        """Return aggregate statistics for all jobs."""
        conn = self.backend.conn
        schedules = self.get_schedules()
        result: dict[str, Any] = {"jobs": {}}
        for sched in schedules:
            name = sched["job_name"]
            total = conn.execute(
                "SELECT COUNT(*) FROM job_logs WHERE job_name = ? AND status != 'running'",
                (name,),
            ).fetchone()[0]
            successes = conn.execute(
                "SELECT COUNT(*) FROM job_logs WHERE job_name = ? AND status = 'success'",
                (name,),
            ).fetchone()[0]
            avg_dur = conn.execute(
                "SELECT AVG(duration_seconds) FROM job_logs WHERE job_name = ? AND status != 'running'",
                (name,),
            ).fetchone()[0]
            last_row = conn.execute(
                "SELECT status FROM job_logs WHERE job_name = ? AND status != 'running'"
                " ORDER BY started_at DESC LIMIT 1",
                (name,),
            ).fetchone()

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
                rows = conn.execute(
                    "SELECT status, COUNT(*) as cnt FROM job_logs"
                    " WHERE job_name = ? AND started_at >= ? AND started_at < ?"
                    " AND status != 'running' GROUP BY status",
                    (name, day_start, day_end),
                ).fetchall()
                for r in rows:
                    if r["status"] in counts:
                        counts[r["status"]] = r["cnt"]
                sparkline.append(counts)

            result["jobs"][name] = {
                "total_runs": total,
                "success_rate": round(successes / total, 2) if total > 0 else 0.0,
                "avg_duration_seconds": round(avg_dur, 2) if avg_dur else 0.0,
                "last_status": last_row["status"] if last_row else None,
                "sparkline": sparkline,
            }
        return result
