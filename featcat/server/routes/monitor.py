"""Monitoring endpoints."""

from __future__ import annotations

import asyncio
from datetime import date, datetime  # noqa: TC003 — Pydantic resolves at runtime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from ..cache import cache_get, cache_set, invalidate
from ..deps import get_db, get_llm

router = APIRouter()


class MetricSeriesPoint(BaseModel):
    """One data point in the per-feature metric timeline."""

    checked_at: datetime
    psi: float | None
    severity: str
    null_ratio: float | None = None
    mean_z_score: float | None = None
    sample_size: int | None = None


class DriftRatePoint(BaseModel):
    """One day in the catalog-wide drift-rate trend."""

    date: date
    critical_pct: float
    warning_pct: float
    total_features: int


class DriftRateResponse(BaseModel):
    """Catalog drift-rate series with the date range driving the X axis."""

    date_range: list[date]
    series: list[DriftRatePoint]


@router.post("/baseline")
async def compute_baseline(db=Depends(get_db)):
    """Compute and save baseline statistics for all features."""
    from ...plugins.monitoring import MonitoringPlugin

    plugin = MonitoringPlugin()
    result = await run_in_threadpool(plugin.execute, db, None, action="baseline")
    # Drift trend + per-feature timelines depend on baseline-derived metrics
    # the next check will produce — invalidate so dashboards reflect the reset.
    invalidate("monitor:")
    invalidate("groups:drift_matrix:")
    return result.data


@router.get("/check")
async def run_check(feature_name: str | None = None, use_llm: bool = False, db=Depends(get_db), llm=Depends(get_llm)):
    """Run quality checks on features. LLM analysis is opt-in via use_llm=true."""
    from ...plugins.monitoring import MonitoringPlugin

    plugin = MonitoringPlugin()
    actual_llm = llm if use_llm else None

    if use_llm and llm is not None:
        try:
            result = await asyncio.wait_for(
                run_in_threadpool(
                    plugin.execute,
                    db,
                    actual_llm,
                    action="check",
                    feature_name=feature_name,
                    use_llm=True,
                ),
                timeout=180,
            )
        except asyncio.TimeoutError:
            # Fall back to non-LLM check
            result = await run_in_threadpool(
                plugin.execute,
                db,
                None,
                action="check",
                feature_name=feature_name,
            )
    else:
        result = await run_in_threadpool(
            plugin.execute,
            db,
            None,
            action="check",
            feature_name=feature_name,
        )

    # Each check writes new monitoring_checks rows; chart caches must drop.
    invalidate("monitor:")
    invalidate("groups:drift_matrix:")
    return result.data


@router.get("/report")
async def monitoring_report(db=Depends(get_db)):
    """Get monitoring report data (no LLM, always fast)."""
    from ...plugins.monitoring import MonitoringPlugin

    plugin = MonitoringPlugin()
    result = await run_in_threadpool(plugin.execute, db, None, action="check")
    return result.data


@router.get("/history/{feature_spec:path}")
def monitoring_history(
    feature_spec: str,
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),  # noqa: B008
):
    """Get PSI check history for a feature."""
    return db.get_monitoring_history(feature_spec, days=days)


@router.get("/baseline/{feature_spec:path}")
def get_baseline(
    feature_spec: str,
    db=Depends(get_db),  # noqa: B008
):
    """Get baseline statistics for a feature by name."""
    result = db.get_baseline_for_feature(feature_spec)
    if result is None:
        raise HTTPException(status_code=404, detail="No baseline found for this feature")
    return result


@router.get("/metrics/{feature_spec:path}", response_model=list[MetricSeriesPoint])
def metric_history(
    feature_spec: str,
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),  # noqa: B008
) -> list[MetricSeriesPoint]:
    """Per-check metric history for the multi-metric feature chart.

    Superset of ``/history``: same PSI + severity, plus null_ratio,
    mean_z_score, sample_size for checks performed after the schema
    migration. Legacy rows return NULL for the new fields.
    """
    cache_key = f"monitor:metrics:{feature_spec}:{days}"
    cached = cache_get(cache_key)
    if cached is not None:
        return [MetricSeriesPoint.model_validate(r) for r in cached]
    rows = db.get_feature_metric_history(feature_spec, days=days)
    cache_set(cache_key, rows)
    return [MetricSeriesPoint.model_validate(r) for r in rows]


@router.get("/drift-rate", response_model=DriftRateResponse)
def drift_rate(
    days: int = Query(90, ge=7, le=365),
    db=Depends(get_db),  # noqa: B008
) -> DriftRateResponse:
    """Per-day catalog-wide drift-rate trend for the dashboard chart."""
    cache_key = f"monitor:drift_rate:{days}"
    cached = cache_get(cache_key)
    if cached is not None:
        return DriftRateResponse.model_validate(cached)
    series = db.get_catalog_drift_trend(days=days)
    response = DriftRateResponse(
        date_range=[r["date"] for r in series],
        series=[DriftRatePoint.model_validate(r) for r in series],
    )
    cache_set(cache_key, response.model_dump(mode="json"))
    return response
