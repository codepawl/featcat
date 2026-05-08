"""Documentation generation tasks (T1.5b).

Houses ``doc_generate``, the Celery port of the autodoc scheduler job.
This is the slowest of the four scheduled jobs (LLM-bound — typically
5-10s per feature on CPU), which is why the ``docs`` queue exists as a
dedicated routing target: operators can pin a single high-CPU /
GPU-equipped worker pool to ``--queues=docs`` and let snappy
``monitoring`` checks run on a separate, smaller pool.

Like the other tasks, this is a thin wrapper around the underlying
``AutodocPlugin`` so the in-process APScheduler path and the Celery
path execute the same code.

Retry policy mirrors ``monitoring.monitor_check``: transient network /
LLM errors retry with backoff, domain errors fail fast.
"""

from __future__ import annotations

import logging
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded

from .app import app

log = logging.getLogger(__name__)


@app.task(
    bind=True,
    name="featcat.tasks.docs.doc_generate",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
)
def doc_generate(self: Any) -> dict:
    """Generate docs for any undocumented features in the catalog.

    Reuses ``AutodocPlugin.execute(...)`` for batched documentation. If
    the LLM is unavailable, returns an explicit "skipped" payload rather
    than failing — the next run picks up where this one left off.
    """
    from ..catalog.factory import get_backend
    from ..llm import create_llm
    from ..plugins.autodoc import AutodocPlugin

    log.info("doc_generate starting (task_id=%s, retry=%s)", self.request.id, self.request.retries)
    backend = get_backend()
    try:
        try:
            llm = create_llm()
        except Exception as exc:  # noqa: BLE001
            log.warning("LLM unavailable for doc_generate, skipping: %s", exc)
            return {
                "status": "skipped",
                "data": {"documented": 0, "message": "LLM not available, skipped"},
                "task_id": self.request.id,
            }
        try:
            result = AutodocPlugin().execute(backend, llm)
        except SoftTimeLimitExceeded:
            log.warning("doc_generate soft-time-limit reached; returning partial result")
            return {"status": "timeout", "task_id": self.request.id}
        return {"status": result.status, "data": result.data, "task_id": self.request.id}
    finally:
        backend.close()


__all__ = ["doc_generate"]
