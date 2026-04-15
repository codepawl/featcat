"""Monitoring endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from starlette.concurrency import run_in_threadpool

from ..deps import get_db, get_llm

router = APIRouter()


@router.post("/baseline")
async def compute_baseline(db=Depends(get_db)):
    """Compute and save baseline statistics for all features."""
    from ...plugins.monitoring import MonitoringPlugin

    plugin = MonitoringPlugin()
    result = await run_in_threadpool(plugin.execute, db, None, action="baseline")
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
