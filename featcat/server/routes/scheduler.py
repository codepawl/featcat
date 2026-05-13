"""Unified job-status API (T1.5c).

These endpoints abstract over the two execution backends configured by
``FEATCAT_TASKS_BACKEND``:

* ``apscheduler`` (default) — in-process APScheduler dispatches each job
  on its cron and writes results straight to ``job_logs``.
* ``celery`` — APScheduler still owns the cron triggers, but the actual
  work is shipped to a Celery worker pool. Job results still land in
  ``job_logs`` via the scheduler's wrapper.

Consumers (web UI, CLI) use these endpoints to render history, view a
single job's state, and trigger ad-hoc runs without caring which backend
is active. The legacy ``/api/jobs/*`` endpoints stay in place — they are
the read+write surface for cron edits and the existing Settings page;
this router is purely additive.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text

from ..deps import get_scheduler, get_settings

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Response models — typed per the api.md rule. Kept lean (Optional fields are
# either ``None`` or absent depending on whether the job has ever run).
# ---------------------------------------------------------------------------


class JobSummary(BaseModel):
    name: str
    cron: str
    enabled: bool
    next_run_at: datetime | None = None
    last_status: str | None = None
    last_run_at: datetime | None = None
    last_duration_ms: int | None = None
    last_error: str | None = None
    backend: str  # "apscheduler" | "celery"


class JobRun(BaseModel):
    id: str
    job_name: str
    status: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    result_summary: dict[str, Any] = {}
    error_message: str | None = None
    triggered_by: str


class JobDetail(JobSummary):
    description: str = ""
    recent_runs: list[JobRun] = []
    active_celery_task_ids: list[str] = []


class TriggerRequest(BaseModel):
    kwargs: dict[str, Any] | None = None


class TriggerResponse(BaseModel):
    job_log_id: str
    celery_task_id: str | None = None
    status: str  # "queued" | "running"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_run(row: dict[str, Any]) -> JobRun:
    summary = row.get("result_summary") or {}
    if isinstance(summary, str):
        try:
            summary = json.loads(summary)
        except json.JSONDecodeError:
            summary = {}
    return JobRun(
        id=row["id"],
        job_name=row["job_name"],
        status=row["status"],
        started_at=row["started_at"],
        finished_at=row.get("finished_at"),
        duration_seconds=row.get("duration_seconds"),
        result_summary=summary if isinstance(summary, dict) else {},
        error_message=row.get("error_message"),
        triggered_by=row["triggered_by"],
    )


def _next_run_at(scheduler: Any, job_name: str) -> datetime | None:
    """Pull next-fire time directly from the live APScheduler instance.

    Falls back to ``None`` when:
      * APScheduler isn't running (e.g. multi-worker deploy without master),
      * the job is disabled and therefore not registered, or
      * APScheduler hasn't computed a next fire yet.
    """
    aps = getattr(scheduler, "_apscheduler", None)
    if aps is None:
        return None
    try:
        job = aps.get_job(job_name)
    except Exception:  # noqa: BLE001
        return None
    if job is None:
        return None
    return getattr(job, "next_run_time", None)


def _last_run_for(scheduler: Any, job_name: str) -> dict[str, Any] | None:
    """Return the most recent non-running job_logs row for a job, or None."""
    with scheduler.backend.session() as s:
        row = (
            s.execute(
                text(
                    "SELECT id, status, started_at, finished_at, duration_seconds, "
                    "  error_message, result_summary "
                    "FROM job_logs "
                    "WHERE job_name = :name AND status != 'running' "
                    "ORDER BY started_at DESC LIMIT 1"
                ),
                {"name": job_name},
            )
            .mappings()
            .first()
        )
    return dict(row) if row else None


def _build_summary(scheduler: Any, schedule: dict[str, Any], backend_name: str) -> JobSummary:
    name = schedule["job_name"]
    last = _last_run_for(scheduler, name)
    duration_ms: int | None = None
    if last and last.get("duration_seconds") is not None:
        duration_ms = int(round(float(last["duration_seconds"]) * 1000))
    return JobSummary(
        name=name,
        cron=schedule["cron_expression"],
        enabled=bool(schedule["enabled"]),
        next_run_at=_next_run_at(scheduler, name),
        last_status=(last or {}).get("status"),
        last_run_at=(last or {}).get("finished_at") or (last or {}).get("started_at"),
        last_duration_ms=duration_ms,
        last_error=(last or {}).get("error_message"),
        backend=backend_name,
    )


def _active_celery_task_ids(job_name: str) -> list[str]:
    """Best-effort query of Celery's broker for in-flight tasks.

    Celery's ``inspect`` round-trips to every worker through Redis; if the
    broker is unreachable or no workers are connected the call hangs the
    request thread for the default 1s socket timeout, then raises. We catch
    everything and return ``[]`` so the detail endpoint stays snappy even
    when the Redis broker is down.
    """
    try:
        from ...tasks.app import app as celery_app  # type: ignore[import-not-found]
    except ImportError:
        return []

    task_name_map = {
        "monitor_check": "featcat.tasks.monitoring.monitor_check",
        "doc_generate": "featcat.tasks.docs.doc_generate",
        "source_scan": "featcat.tasks.sources.source_scan",
        "baseline_refresh": "featcat.tasks.monitoring.baseline_refresh",
    }
    expected = task_name_map.get(job_name)
    if not expected:
        return []

    try:
        inspector = celery_app.control.inspect(timeout=0.5)
        ids: list[str] = []
        for getter in (inspector.active, inspector.reserved):
            data = getter() or {}
            for tasks in data.values():
                for task in tasks:
                    if task.get("name") == expected and task.get("id"):
                        ids.append(task["id"])
        return ids
    except Exception as exc:  # noqa: BLE001
        # Redis unreachable or workers offline — degrade gracefully.
        logger.debug("Celery inspect failed for %s: %s", job_name, exc)
        return []


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/jobs", response_model=list[JobSummary])
def list_jobs(
    scheduler=Depends(get_scheduler),  # noqa: B008
    settings=Depends(get_settings),  # noqa: B008
):
    """List all jobs with last-run summary and the current backend."""
    if scheduler is None:
        return []
    backend_name = getattr(settings, "tasks_backend", "apscheduler")
    schedules = scheduler.get_schedules()
    return [_build_summary(scheduler, s, backend_name) for s in schedules]


@router.get("/jobs/{name}", response_model=JobDetail)
def get_job_detail(
    name: str,
    scheduler=Depends(get_scheduler),  # noqa: B008
    settings=Depends(get_settings),  # noqa: B008
):
    """Detailed view of a single job: schedule + last 20 runs + active task ids."""
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    schedules = scheduler.get_schedules()
    schedule = next((s for s in schedules if s["job_name"] == name), None)
    if schedule is None:
        raise HTTPException(status_code=404, detail=f"Job not found: {name}")

    backend_name = getattr(settings, "tasks_backend", "apscheduler")
    summary = _build_summary(scheduler, schedule, backend_name)
    recent = [_row_to_run(r) for r in scheduler.get_logs(job_name=name, limit=20)]
    task_ids = _active_celery_task_ids(name) if backend_name == "celery" else []

    return JobDetail(
        **summary.model_dump(),
        description=schedule.get("description") or "",
        recent_runs=recent,
        active_celery_task_ids=task_ids,
    )


@router.post("/jobs/{name}/run", response_model=TriggerResponse)
async def trigger_job(
    name: str,
    body: TriggerRequest | None = None,
    scheduler=Depends(get_scheduler),  # noqa: B008
    settings=Depends(get_settings),  # noqa: B008
):
    """Trigger a job immediately and return a tracking handle.

    Both backends create a ``job_logs`` row in ``running`` state up-front
    so the caller can poll ``GET /jobs/{name}`` and see the run flowing
    through history right away. Execution is dispatched in the background:
    ``asyncio.create_task`` for APScheduler, ``send_task`` for Celery.
    """
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")

    schedules = scheduler.get_schedules()
    if name not in {s["job_name"] for s in schedules}:
        raise HTTPException(status_code=404, detail=f"Job not found: {name}")

    backend_name = getattr(settings, "tasks_backend", "apscheduler")
    log_id = str(uuid.uuid4())
    started_at = datetime.now(timezone.utc)

    # Up-front "running" row so the trigger handle is observable immediately.
    with scheduler.backend.session() as s:
        s.execute(
            text(
                "INSERT INTO job_logs (id, job_name, status, started_at, triggered_by) "
                "VALUES (:id, :name, 'running', :started, :by)"
            ),
            {"id": log_id, "name": name, "started": started_at, "by": "api"},
        )
        s.commit()

    celery_task_id: str | None = None

    if backend_name == "celery":
        try:
            from ...tasks.app import app as celery_app  # type: ignore[import-not-found]
        except ImportError as exc:
            _mark_failed(scheduler, log_id, f"[tasks] extra not installed: {exc}")
            raise HTTPException(status_code=503, detail="Celery backend not available") from exc
        task_name_map = {
            "monitor_check": "featcat.tasks.monitoring.monitor_check",
            "doc_generate": "featcat.tasks.docs.doc_generate",
            "source_scan": "featcat.tasks.sources.source_scan",
            "baseline_refresh": "featcat.tasks.monitoring.baseline_refresh",
        }
        task_name = task_name_map.get(name)
        if task_name is None:
            _mark_failed(scheduler, log_id, f"Unknown job: {name}")
            raise HTTPException(status_code=400, detail=f"Unknown job: {name}")
        try:
            async_result = celery_app.send_task(task_name, kwargs=(body.kwargs if body else None) or {})
            celery_task_id = async_result.id
        except Exception as exc:  # noqa: BLE001
            _mark_failed(scheduler, log_id, f"Celery dispatch failed: {exc}")
            raise HTTPException(status_code=502, detail=f"Celery dispatch failed: {exc}") from exc
        return TriggerResponse(job_log_id=log_id, celery_task_id=celery_task_id, status="queued")

    # APScheduler in-process path: hand off to the running event loop so
    # the HTTP request returns immediately. We wrap run_job so it updates
    # the existing log_id row instead of creating a fresh one.
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError as exc:
        _mark_failed(scheduler, log_id, f"No event loop available: {exc}")
        raise HTTPException(status_code=500, detail="No event loop available") from exc

    loop.create_task(_run_and_finalize(scheduler, name, log_id, started_at))
    return TriggerResponse(job_log_id=log_id, celery_task_id=None, status="running")


@router.get("/runs", response_model=list[JobRun])
def list_runs(
    job: str | None = Query(None, description="Filter by job name"),
    limit: int = Query(50, ge=1, le=500),
    since: datetime | None = Query(None, description="Filter to runs started at or after this ISO timestamp"),
    scheduler=Depends(get_scheduler),  # noqa: B008
):
    """Paginated job_logs view used for the UI history table."""
    if scheduler is None:
        return []
    clauses: list[str] = ["1=1"]
    params: dict[str, Any] = {"lim": limit}
    if job:
        clauses.append("job_name = :name")
        params["name"] = job
    if since is not None:
        clauses.append("started_at >= :since")
        params["since"] = since
    sql = (
        f"SELECT id, job_name, status, started_at, finished_at, duration_seconds, "  # noqa: S608
        f"       result_summary, error_message, triggered_by "
        f"FROM job_logs WHERE {' AND '.join(clauses)} "
        f"ORDER BY started_at DESC LIMIT :lim"
    )
    with scheduler.backend.session() as s:
        rows = s.execute(text(sql), params).mappings().all()
    return [_row_to_run(dict(r)) for r in rows]


# ---------------------------------------------------------------------------
# Internal helpers used by the trigger endpoint
# ---------------------------------------------------------------------------


def _mark_failed(scheduler: Any, log_id: str, error: str) -> None:
    """Promote a queued log row to 'failed' when dispatch never made it out."""
    finished = datetime.now(timezone.utc)
    with scheduler.backend.session() as s:
        s.execute(
            text(
                "UPDATE job_logs SET status = 'failed', finished_at = :f, "
                "  duration_seconds = 0, error_message = :err WHERE id = :id"
            ),
            {"f": finished, "err": error, "id": log_id},
        )
        s.commit()


async def _run_and_finalize(scheduler: Any, job_name: str, log_id: str, started_at: datetime) -> None:
    """Execute a job in the APScheduler in-process path and update the
    pre-created job_logs row.

    We call the same plugin entry-points as ``FeatcatScheduler.run_job`` so
    behaviour matches; we just own the row lifecycle ourselves so the
    trigger endpoint can return early with a known ``log_id``.
    """
    import time

    start = time.monotonic()
    try:
        result_summary = await scheduler._execute(job_name)
        status = "success"
        error_message: str | None = None
    except ValueError as exc:
        status = "failed"
        result_summary = {}
        error_message = str(exc)
    except Exception as exc:  # noqa: BLE001
        status = "failed"
        result_summary = {}
        error_message = f"{type(exc).__name__}: {exc}"

    duration = time.monotonic() - start
    finished_at = datetime.now(timezone.utc)
    with scheduler.backend.session() as s:
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
    try:
        scheduler.purge_old_logs(job_name)
    except Exception as exc:  # noqa: BLE001
        logger.debug("purge_old_logs failed after manual trigger: %s", exc)
