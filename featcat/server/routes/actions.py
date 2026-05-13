"""Action item endpoints — closes the lifecycle loop (recommendation → outcome)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ..deps import get_db

router = APIRouter()

VALID_STATUS = {"pending", "applied", "dismissed", "snoozed"}
VALID_SOURCE = {"drift_alert", "chat", "autodoc", "manual"}


class ActionCreate(BaseModel):
    feature_id: str | None = None
    feature_name: str | None = None
    source: str
    title: str
    recommendation: str
    context: dict = Field(default_factory=dict)
    created_by: str = ""


class ActionUpdate(BaseModel):
    status: str
    applied_by: str = ""
    change_summary: str = ""


@router.get("")
def list_actions(
    feature_id: str | None = None,
    feature_name: str | None = None,
    status: str | None = None,
    source: str | None = None,
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),  # noqa: B008
):
    """List action items with optional filters."""
    if feature_name and not feature_id:
        feat = db.get_feature_by_name(feature_name)
        if feat is None:
            return []
        feature_id = feat.id
    if status and status not in VALID_STATUS:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {sorted(VALID_STATUS)}")
    return db.list_action_items(feature_id=feature_id, status=status, source=source, limit=limit, offset=offset)


@router.get("/count")
def count_actions(status: str | None = None, db=Depends(get_db)):  # noqa: B008
    """Count action items, optionally filtered by status."""
    if status and status not in VALID_STATUS:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {sorted(VALID_STATUS)}")
    return {"count": db.count_action_items(status=status)}


@router.post("")
def create_action(body: ActionCreate, db=Depends(get_db)):  # noqa: B008
    """Create a new action item. Either feature_id or feature_name is required."""
    if body.source not in VALID_SOURCE:
        raise HTTPException(status_code=400, detail=f"Invalid source. Must be one of {sorted(VALID_SOURCE)}")

    fid = body.feature_id
    if not fid:
        if not body.feature_name:
            raise HTTPException(status_code=400, detail="feature_id or feature_name is required")
        feat = db.get_feature_by_name(body.feature_name)
        if feat is None:
            raise HTTPException(status_code=404, detail=f"Feature not found: {body.feature_name}")
        fid = feat.id

    item_id = db.create_action_item(
        feature_id=fid,
        source=body.source,
        title=body.title,
        recommendation=body.recommendation,
        context=body.context,
        created_by=body.created_by,
    )
    return db.get_action_item(item_id)


@router.get("/{item_id}")
def get_action(item_id: str, db=Depends(get_db)):  # noqa: B008
    """Fetch a single action item."""
    item = db.get_action_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Action item not found: {item_id}")
    return item


@router.patch("/{item_id}")
def update_action(item_id: str, body: ActionUpdate, db=Depends(get_db)):  # noqa: B008
    """Update an action item's status (apply/dismiss/snooze/reopen)."""
    if body.status not in VALID_STATUS:
        raise HTTPException(status_code=400, detail=f"Invalid status. Must be one of {sorted(VALID_STATUS)}")
    if db.get_action_item(item_id) is None:
        raise HTTPException(status_code=404, detail=f"Action item not found: {item_id}")
    db.update_action_item_status(
        item_id,
        status=body.status,
        applied_by=body.applied_by,
        change_summary=body.change_summary,
    )
    return db.get_action_item(item_id)
