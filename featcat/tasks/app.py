"""Celery application + beat schedule + queue routes (T1.5a).

Single source of truth for the Celery app. Workers and beat are launched
against this module:

    celery -A featcat.tasks.app worker --queues=monitoring,docs,sources,default
    celery -A featcat.tasks.app beat
    celery -A featcat.tasks.app flower

Queues:
- ``monitoring`` — drift checks, baseline refresh
- ``docs`` — autodoc generation (LLM-bound, slowest)
- ``sources`` — source rescans
- ``default`` — anything unrouted

Queue routing per task module keeps slow doc-generation jobs from blocking
fast monitoring checks at the worker level — operators can run a dedicated
``--queues=monitoring`` worker pool for snappy drift detection.

Beat schedule mirrors the four APScheduler defaults from
``featcat/server/scheduler.py``. During the parallel-run migration window
(T1.5b/c) APScheduler stays in place; once Celery beat has run reliably for
a week the in-process scheduler is removed.
"""

from __future__ import annotations

import os

from celery import Celery
from celery.schedules import crontab

REDIS_URL = os.environ.get("FEATCAT_REDIS_URL", "redis://localhost:6379/0")

app = Celery(
    "featcat",
    broker=REDIS_URL,
    backend=REDIS_URL,
    include=[
        "featcat.tasks.monitoring",
        # ``docs`` and ``sources`` modules land in T1.5b — registering the
        # paths now would cause Celery to fail loading them. Add when the
        # tasks are written.
    ],
)

app.conf.task_routes = {
    "featcat.tasks.monitoring.*": {"queue": "monitoring"},
    "featcat.tasks.docs.*": {"queue": "docs"},
    "featcat.tasks.sources.*": {"queue": "sources"},
}
app.conf.task_default_queue = "default"
app.conf.task_default_priority = 5
app.conf.task_acks_late = True  # don't ack until task completes — survives worker crash
app.conf.worker_prefetch_multiplier = 1  # fair dispatch for long-running tasks
app.conf.task_time_limit = 30 * 60  # 30 min hard ceiling per task
app.conf.task_soft_time_limit = 25 * 60  # raises SoftTimeLimitExceeded for graceful shutdown

# Beat schedule. crontab(...) accepts the same patterns as APScheduler's
# CronTrigger.from_crontab; the human-readable defaults below match the
# current scheduler.DEFAULT_JOBS settings.
app.conf.beat_schedule = {
    "monitor-check-every-6h": {
        "task": "featcat.tasks.monitoring.monitor_check",
        "schedule": crontab(minute=0, hour="*/6"),
    },
    # docs / sources / baseline_refresh land in T1.5b alongside the task
    # implementations. Empty schedule keys here would error at beat startup,
    # so they're commented until then.
    # "doc-generate-daily": {
    #     "task": "featcat.tasks.docs.generate_missing",
    #     "schedule": crontab(hour=2, minute=0),
    # },
    # "source-scan-daily": {
    #     "task": "featcat.tasks.sources.scan_all",
    #     "schedule": crontab(hour=1, minute=0),
    # },
    # "baseline-refresh-weekly": {
    #     "task": "featcat.tasks.monitoring.baseline_refresh",
    #     "schedule": crontab(day_of_week=0, hour=3, minute=0),
    # },
}

__all__ = ["REDIS_URL", "app"]
