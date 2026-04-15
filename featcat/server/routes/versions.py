"""Version history endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..deps import get_db

router = APIRouter()


@router.get("/recent")
def recent_versions(
    limit: int = Query(20, ge=1, le=100),
    days: int = Query(7, ge=1, le=365),
    change_type: str | None = None,
    changed_by: str | None = None,
    db=Depends(get_db),  # noqa: B008
):
    """Return recent version changes across all features for audit log."""
    versions = db.get_recent_versions(limit=limit, days=days)

    if change_type:
        versions = [v for v in versions if v.get("change_type") == change_type]
    if changed_by:
        versions = [v for v in versions if v.get("changed_by") == changed_by]

    return versions
