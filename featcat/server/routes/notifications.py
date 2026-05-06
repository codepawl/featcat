"""In-app notifications endpoints (T2.1 — in-web only, no external integrations).

Five endpoints under ``/api/notifications``:

- ``GET /``                   — paginated feed (newest first)
- ``GET /?unread_only=true``  — unread-only feed for the bell-icon dropdown
- ``GET /unread-count``       — single-int badge value
- ``POST /{id}/read``         — mark one as read; 404 if id unknown
- ``POST /read-all``          — mark every unread as read; returns count
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_db

router = APIRouter()


@router.get("")
def list_notifications(
    unread_only: bool = Query(False),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),  # noqa: B008
) -> list[dict]:
    return db.list_notifications(unread_only=unread_only, limit=limit, offset=offset)


@router.get("/unread-count")
def unread_count(db=Depends(get_db)) -> dict:  # noqa: B008
    return {"count": db.count_unread_notifications()}


@router.post("/{notification_id}/read")
def mark_read(notification_id: str, db=Depends(get_db)) -> dict:  # noqa: B008
    if not db.mark_notification_read(notification_id):
        raise HTTPException(status_code=404, detail=f"Notification not found: {notification_id}")
    return {"id": notification_id, "read": True}


@router.post("/read-all")
def mark_all_read(db=Depends(get_db)) -> dict:  # noqa: B008
    return {"marked_read": db.mark_all_notifications_read()}
