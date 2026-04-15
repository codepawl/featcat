"""Usage tracking endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..deps import get_db

router = APIRouter()


@router.get("/top")
def usage_top(
    limit: int = Query(10, ge=1, le=100),
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),  # noqa: B008
):
    """Get most-used features by action counts."""
    return db.get_top_features(limit=limit, days=days)


@router.get("/orphaned")
def usage_orphaned(
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),  # noqa: B008
):
    """Get features with zero usage in the given period."""
    return db.get_orphaned_features(days=days)


@router.get("/activity")
def usage_activity(
    days: int = Query(7, ge=1, le=365),
    db=Depends(get_db),  # noqa: B008
):
    """Get per-day usage activity summary."""
    return db.get_usage_activity(days=days)


@router.get("/feature")
def feature_usage(
    name: str = Query(..., description="Feature name (e.g. source.column)"),
    days: int = Query(30, ge=1, le=365),
    db=Depends(get_db),  # noqa: B008
):
    """Get usage summary for a single feature."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        return {"views": 0, "queries": 0, "total": 0, "last_seen": None, "daily": []}
    return db.get_feature_usage(feature.id, days=days)
