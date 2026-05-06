"""Bulk feature operations (T1.3a).

Three endpoints, all under ``/api/features/bulk``:

- ``POST /tags`` — add/remove/replace tags on N features
- ``POST /groups`` — add_to / remove_from a group for N features
- ``POST /delete`` — delete N features (requires ``confirm: true``)

Validation is all-or-nothing per spec: if any feature_id is unknown the
endpoint returns 400 with the list of invalid IDs and does NOT
partial-execute. Bulk export and bulk doc-regen already exist via
``/api/export/*`` and ``/api/docs/generate-batch`` respectively.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from ..deps import get_db

router = APIRouter()

BULK_MAX_IDS = 1000  # mirrors LocalBackend.BULK_MAX_IDS — single source of truth


def _enforce_size(feature_ids: list[str]) -> None:
    if len(feature_ids) > BULK_MAX_IDS:
        raise HTTPException(
            status_code=400,
            detail=f"Too many feature_ids: {len(feature_ids)} (max {BULK_MAX_IDS}).",
        )


def _validate_or_400(db, feature_ids: list[str]) -> None:
    _enforce_size(feature_ids)
    _, invalid = db._validate_feature_ids(feature_ids)
    if invalid:
        raise HTTPException(
            status_code=400,
            detail={"message": "Some feature_ids do not exist.", "invalid_ids": invalid},
        )


class BulkTagsRequest(BaseModel):
    feature_ids: list[str] = Field(..., min_length=1)
    action: str = Field(..., description="add | remove | replace")
    tags: list[str] = Field(default_factory=list)


@router.post("/tags")
def bulk_tags(body: BulkTagsRequest, db=Depends(get_db)):  # noqa: B008
    if body.action not in {"add", "remove", "replace"}:
        raise HTTPException(status_code=400, detail="action must be one of add/remove/replace")
    _validate_or_400(db, body.feature_ids)
    updated = db.bulk_update_tags(body.feature_ids, body.action, body.tags)
    return {"updated": updated, "requested": len(body.feature_ids)}


class BulkGroupsRequest(BaseModel):
    feature_ids: list[str] = Field(..., min_length=1)
    action: str = Field(..., description="add_to | remove_from")
    group_id: str


@router.post("/groups")
def bulk_groups(body: BulkGroupsRequest, db=Depends(get_db)):  # noqa: B008
    if body.action not in {"add_to", "remove_from"}:
        raise HTTPException(status_code=400, detail="action must be add_to or remove_from")
    _validate_or_400(db, body.feature_ids)
    changed = db.bulk_group_action(body.group_id, body.feature_ids, body.action)
    return {"changed": changed, "requested": len(body.feature_ids)}


class BulkDeleteRequest(BaseModel):
    feature_ids: list[str] = Field(..., min_length=1)
    confirm: bool = Field(False, description="Must be true to actually delete")


@router.post("/delete")
def bulk_delete(body: BulkDeleteRequest, db=Depends(get_db)):  # noqa: B008
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Bulk delete requires `confirm: true` to prevent accidental destruction.",
        )
    _validate_or_400(db, body.feature_ids)
    deleted = db.bulk_delete_features(body.feature_ids)
    return {"deleted": deleted, "requested": len(body.feature_ids)}
