"""Monitoring tasks (T1.5a).

Currently contains a single task — ``monitor_check`` — to prove the
Celery integration end-to-end. The implementation reuses
``MonitoringPlugin.execute(..., action="check")`` so business logic stays
in one place and the in-process APScheduler path keeps working
identically during the parallel-run migration window.

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


__all__ = ["monitor_check"]
