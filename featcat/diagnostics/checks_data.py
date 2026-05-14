"""Data checks for ``featcat doctor data``.

These are catalog-side health checks: are sources discoverable, are features
well-formed, is the doc/drift/lineage coverage acceptable. They run pure
backend queries — no LLM, no network beyond the local catalog DB.
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text

from .models import CheckResult, CheckStatus
from .runner import register

if TYPE_CHECKING:
    from featcat.config import Settings


# Coverage thresholds — match the user-facing copy in `featcat doctor data` resolutions.
_DOC_PASS_PCT = 80.0
_DOC_WARN_PCT = 40.0
_LINEAGE_PASS_PCT = 50.0
_LINEAGE_WARN_PCT = 20.0
_DRIFT_PASS_DAYS = 7
_DRIFT_WARN_DAYS = 30


def _get_backend():  # noqa: ANN202 — CatalogBackend's abstract type is private; caller treats it as duck-typed
    """Open a backend handle. Caller closes."""
    from featcat.catalog.factory import get_backend

    return get_backend()


@register("data")
def data_sources_registered(_settings: Settings) -> CheckResult:
    """Catalog has at least one registered source."""
    try:
        db = _get_backend()
        try:
            sources = db.list_sources()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="data_sources_registered",
            status=CheckStatus.FAIL,
            detail=f"list_sources failed: {exc}",
        )
    if not sources:
        return CheckResult(
            name="data_sources_registered",
            status=CheckStatus.WARN,
            detail="no sources registered",
            resolution="featcat source add <name> <path>",
        )
    return CheckResult(
        name="data_sources_registered",
        status=CheckStatus.PASS,
        detail=f"{len(sources)} source(s)",
        metadata={"count": len(sources)},
    )


@register("data")
def data_sources_scannable(_settings: Settings) -> CheckResult:
    """Every local-storage source points to a readable path.

    S3 sources are not probed — that's an opt-in network check under
    ``doctor network``.
    """
    try:
        db = _get_backend()
        try:
            sources = db.list_sources()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="data_sources_scannable",
            status=CheckStatus.FAIL,
            detail=f"list_sources failed: {exc}",
        )
    if not sources:
        return CheckResult(
            name="data_sources_scannable",
            status=CheckStatus.SKIP,
            detail="no sources registered",
        )
    missing: list[str] = []
    skipped: list[str] = []
    for src in sources:
        if src.storage_type != "local":
            skipped.append(src.name)
            continue
        if not Path(src.path).exists():
            missing.append(src.name)
    local_count = len(sources) - len(skipped)
    if not missing:
        return CheckResult(
            name="data_sources_scannable",
            status=CheckStatus.PASS,
            detail=f"{local_count} local source(s) readable; {len(skipped)} non-local skipped",
            metadata={"local": local_count, "non_local": len(skipped)},
        )
    status = CheckStatus.FAIL if len(missing) == local_count else CheckStatus.WARN
    return CheckResult(
        name="data_sources_scannable",
        status=status,
        detail=f"{len(missing)} source(s) unreachable: {', '.join(missing[:5])}",
        resolution="Update the source path, remount the volume, or remove via `featcat source rm`",
        metadata={"missing": missing},
    )


@register("data")
def data_stats_coverage(_settings: Settings) -> CheckResult:
    """Every feature should have at least minimal stats. Missing-stats is rare and usually means a broken scan."""
    try:
        db = _get_backend()
        try:
            features = db.list_features()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="data_stats_coverage",
            status=CheckStatus.FAIL,
            detail=f"list_features failed: {exc}",
        )
    if not features:
        return CheckResult(
            name="data_stats_coverage",
            status=CheckStatus.SKIP,
            detail="no features",
        )
    missing = [f.name for f in features if not f.stats]
    if not missing:
        return CheckResult(
            name="data_stats_coverage",
            status=CheckStatus.PASS,
            detail=f"100% coverage ({len(features)} features)",
            metadata={"total": len(features)},
        )
    pct = (len(features) - len(missing)) / len(features) * 100
    status = CheckStatus.FAIL if pct < 50 else CheckStatus.WARN
    return CheckResult(
        name="data_stats_coverage",
        status=status,
        detail=f"{len(missing)}/{len(features)} feature(s) missing stats ({pct:.0f}% coverage)",
        resolution="Re-run `featcat source scan <name>` on the affected sources",
        metadata={"missing_count": len(missing), "total": len(features), "coverage_pct": pct},
    )


@register("data")
def data_doc_coverage(_settings: Settings) -> CheckResult:
    """Use the same doc-stats helper that ``/api/health`` consumes."""
    try:
        db = _get_backend()
        try:
            stats = db.get_doc_stats()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="data_doc_coverage",
            status=CheckStatus.FAIL,
            detail=f"get_doc_stats failed: {exc}",
        )
    documented = int(stats.get("documented", 0))
    total = int(stats.get("total_features", 0))
    coverage = float(stats.get("coverage", 0.0))
    if total == 0:
        return CheckResult(
            name="data_doc_coverage",
            status=CheckStatus.SKIP,
            detail="no features",
        )
    if coverage >= _DOC_PASS_PCT:
        status = CheckStatus.PASS
        resolution = None
    elif coverage >= _DOC_WARN_PCT:
        status = CheckStatus.WARN
        resolution = "Run `featcat doc generate` to backfill documentation"
    else:
        status = CheckStatus.FAIL
        resolution = "Run `featcat doc generate` to backfill documentation"
    return CheckResult(
        name="data_doc_coverage",
        status=status,
        detail=f"{documented}/{total} features documented ({coverage:.0f}%)",
        resolution=resolution,
        metadata={"documented": documented, "total": total, "coverage_pct": coverage},
    )


@register("data")
def data_drift_recency(_settings: Settings) -> CheckResult:
    """How recently were drift baselines/checks run?"""
    try:
        db = _get_backend()
        try:
            with db.session() as s:
                row = s.execute(text("SELECT MAX(checked_at) FROM monitoring_checks")).scalar()
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="data_drift_recency",
            status=CheckStatus.FAIL,
            detail=f"drift query failed: {exc}",
        )
    if row is None:
        return CheckResult(
            name="data_drift_recency",
            status=CheckStatus.FAIL,
            detail="no drift checks ever recorded",
            resolution="Run `featcat monitor check`",
        )
    last_run = row if isinstance(row, datetime) else datetime.fromisoformat(str(row))
    if last_run.tzinfo is None:
        last_run = last_run.replace(tzinfo=timezone.utc)
    age_days = (datetime.now(timezone.utc) - last_run).days
    if age_days <= _DRIFT_PASS_DAYS:
        status = CheckStatus.PASS
        resolution = None
    elif age_days <= _DRIFT_WARN_DAYS:
        status = CheckStatus.WARN
        resolution = "Run `featcat monitor check` to refresh drift data"
    else:
        status = CheckStatus.FAIL
        resolution = "Run `featcat monitor check` — drift data is stale"
    return CheckResult(
        name="data_drift_recency",
        status=status,
        detail=f"last drift check {age_days} day(s) ago",
        resolution=resolution,
        metadata={"age_days": age_days, "last_checked_at": last_run.isoformat()},
    )


@register("data")
def data_lineage_coverage(_settings: Settings) -> CheckResult:
    """Share of features that have at least one inbound lineage edge.

    Per spec this is informational — < 20% is a ``WARN``, never a ``FAIL``.
    """
    try:
        db = _get_backend()
        try:
            with db.session() as s:
                total = int(s.execute(text("SELECT COUNT(*) FROM features")).scalar() or 0)
                with_edges = int(
                    s.execute(text("SELECT COUNT(DISTINCT child_feature_id) FROM feature_lineage")).scalar() or 0
                )
        finally:
            db.close()
    except Exception as exc:  # noqa: BLE001
        return CheckResult(
            name="data_lineage_coverage",
            status=CheckStatus.FAIL,
            detail=f"lineage query failed: {exc}",
        )
    if total == 0:
        return CheckResult(
            name="data_lineage_coverage",
            status=CheckStatus.SKIP,
            detail="no features",
        )
    pct = with_edges / total * 100
    if pct >= _LINEAGE_PASS_PCT:
        status = CheckStatus.PASS
        resolution = None
    elif pct >= _LINEAGE_WARN_PCT:
        status = CheckStatus.WARN
        resolution = "Run `featcat lineage detect` against your SQL definitions"
    else:
        # Per spec: low lineage coverage is informational, not a blocker.
        status = CheckStatus.WARN
        resolution = "Run `featcat lineage detect` or `featcat lineage edge add` to backfill"
    return CheckResult(
        name="data_lineage_coverage",
        status=status,
        detail=f"{with_edges}/{total} feature(s) have lineage ({pct:.0f}%)",
        resolution=resolution,
        metadata={"with_edges": with_edges, "total": total, "coverage_pct": pct},
    )
