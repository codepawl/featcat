"""Monitoring tasks (T1.5a + T1.5b).

Two tasks live here:

- ``monitor_check`` — drift detection across the catalog (T1.5a).
- ``baseline_refresh`` — recompute baseline statistics so ``monitor_check``
  has fresh comparison data (T1.5b).

Both reuse ``MonitoringPlugin.execute(...)`` so business logic stays in
one place; the in-process APScheduler path in ``server/scheduler.py``
calls the same plugin entrypoints. That means switching
``FEATCAT_TASKS_BACKEND`` between ``apscheduler`` and ``celery`` doesn't
change behaviour, only the worker pool.

Retry policy: transient infrastructure errors (LLM unreachable, brief DB
hiccup) bounce up to 3 times with 60s delay; ValueErrors and other
domain-level failures terminate immediately so they don't pile retries
on top of malformed inputs.
"""

from __future__ import annotations

import logging
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded

from .app import app

log = logging.getLogger(__name__)


@app.task(
    bind=True,
    name="featcat.tasks.monitoring.monitor_check",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
)
def monitor_check(self: Any) -> dict:
    """Run drift checks across the catalog.

    Reuses ``MonitoringPlugin.execute(..., action="check")`` so this task
    is a thin Celery wrapper, not a re-implementation. Returns the
    plugin's ``data`` dict so Flower / job_logs (T1.5b) can show the
    summary directly.
    """
    # Imports are deferred to runtime so importing the tasks module
    # doesn't pull in the LLM stack on the API server.
    from ..catalog.factory import get_backend
    from ..llm import create_llm
    from ..plugins.monitoring import MonitoringPlugin

    log.info("monitor_check starting (task_id=%s, retry=%s)", self.request.id, self.request.retries)
    backend = get_backend()
    try:
        # LLM is optional — monitoring runs without it; baseline-only mode
        # still produces useful drift reports.
        try:
            llm = create_llm()
        except Exception as exc:  # noqa: BLE001
            log.warning("LLM unavailable for monitor_check, continuing without: %s", exc)
            llm = None
        try:
            result = MonitoringPlugin().execute(backend, llm, action="check")
        except SoftTimeLimitExceeded:
            log.warning("monitor_check soft-time-limit reached; returning partial result")
            return {"status": "timeout", "task_id": self.request.id}
        return {"status": result.status, "data": result.data, "task_id": self.request.id}
    finally:
        backend.close()


@app.task(
    bind=True,
    name="featcat.tasks.monitoring.baseline_refresh",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
)
def baseline_refresh(self: Any) -> dict:
    """Recompute monitoring baselines for every feature with stats.

    Thin wrapper around ``MonitoringPlugin.execute(..., action="baseline")``.
    Idempotent — re-running just overwrites the same baseline rows with
    the same numbers, so Celery retries are safe.
    """
    from ..catalog.factory import get_backend
    from ..plugins.monitoring import MonitoringPlugin

    log.info("baseline_refresh starting (task_id=%s, retry=%s)", self.request.id, self.request.retries)
    backend = get_backend()
    try:
        try:
            result = MonitoringPlugin().execute(backend, None, action="baseline")
        except SoftTimeLimitExceeded:
            log.warning("baseline_refresh soft-time-limit reached; returning partial result")
            return {"status": "timeout", "task_id": self.request.id}
        return {"status": result.status, "data": result.data, "task_id": self.request.id}
    finally:
        backend.close()


__all__ = ["baseline_refresh", "monitor_check"]
