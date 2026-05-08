"""Source-rescan tasks (T1.5b).

``source_scan`` walks every ``data_sources`` row with ``auto_refresh=1``,
re-runs the parquet scanner, and upserts the resulting columns as
features. There's no dedicated plugin for this (the in-process scheduler
inlines it), so the Celery wrapper imports the scanner + backend
directly. The actual scan work is identical to
``FeatcatScheduler._run_source_scan`` — kept duplicated rather than
shared so this module's celery import doesn't leak into the API
server's import graph (the API process must work without the [tasks]
extra installed).

Idempotency: ``upsert_feature`` is, well, an upsert — re-running the
scan just rewrites the same column metadata with the same values. Safe
to retry.
"""

from __future__ import annotations

import logging
from typing import Any

from celery.exceptions import SoftTimeLimitExceeded
from sqlalchemy import text

from .app import app

log = logging.getLogger(__name__)


def _run_source_scan(backend: Any) -> dict:
    """Implementation used by the Celery task. Mirrors
    ``FeatcatScheduler._run_source_scan`` exactly — keep both in sync."""
    from ..catalog.models import Feature
    from ..catalog.scanner import scan_source

    sources = backend.list_sources()
    total_features = 0
    scanned = 0
    with backend.session() as s:
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
                backend.upsert_feature(feature)
                total_features += 1
            scanned += 1
    return {"sources_scanned": scanned, "features_updated": total_features}


@app.task(
    bind=True,
    name="featcat.tasks.sources.source_scan",
    max_retries=3,
    default_retry_delay=60,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
)
def source_scan(self: Any) -> dict:
    """Re-scan every auto_refresh=1 data source and upsert columns as features."""
    from ..catalog.factory import get_backend

    log.info("source_scan starting (task_id=%s, retry=%s)", self.request.id, self.request.retries)
    backend = get_backend()
    try:
        try:
            data = _run_source_scan(backend)
        except SoftTimeLimitExceeded:
            log.warning("source_scan soft-time-limit reached; returning partial result")
            return {"status": "timeout", "task_id": self.request.id}
        return {"status": "success", "data": data, "task_id": self.request.id}
    finally:
        backend.close()


__all__ = ["_run_source_scan", "source_scan"]
