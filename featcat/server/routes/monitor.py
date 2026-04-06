"""Monitoring endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_db, get_llm

router = APIRouter()


@router.post("/baseline")
def compute_baseline(db=Depends(get_db)):
    """Compute and save baseline statistics for all features."""
    from ...plugins.monitoring import MonitoringPlugin

    plugin = MonitoringPlugin()
    result = plugin.execute(db, None, action="baseline")
    return result.data


@router.get("/check")
def run_check(feature_name: str | None = None, use_llm: bool = False, db=Depends(get_db), llm=Depends(get_llm)):
    """Run quality checks on features."""
    from ...plugins.monitoring import MonitoringPlugin

    plugin = MonitoringPlugin()
    actual_llm = llm if use_llm else None
    result = plugin.execute(
        db, actual_llm, action="check", feature_name=feature_name, use_llm=use_llm and llm is not None,
    )
    return result.data


@router.get("/report")
def monitoring_report(db=Depends(get_db)):
    """Get monitoring report data."""
    from ...plugins.monitoring import MonitoringPlugin

    plugin = MonitoringPlugin()
    result = plugin.execute(db, None, action="check")
    return result.data
