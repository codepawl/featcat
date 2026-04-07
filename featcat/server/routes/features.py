"""Feature management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..deps import get_db

router = APIRouter()


class FeatureUpdate(BaseModel):
    tags: list[str] | None = None
    owner: str | None = None
    description: str | None = None


@router.get("")
def list_features(source: str | None = None, search: str | None = None, db=Depends(get_db)):
    """List features, optionally filtered by source or search query."""
    features = db.search_features(search) if search else db.list_features(source_name=source)
    return [f.model_dump(mode="json") for f in features]


@router.get("/by-name")
def get_feature_by_name(name: str = Query(...), db=Depends(get_db)):
    """Get a feature by name (query param for dotted names)."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    return feature.model_dump(mode="json")


@router.patch("/by-name")
def update_feature_by_name(name: str = Query(...), body: FeatureUpdate = ..., db=Depends(get_db)):
    """Update feature metadata (tags, owner, description)."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")

    if body.tags is not None:
        db.update_feature_tags(feature.id, body.tags)

    return {"updated": name}


@router.delete("/by-name")
def delete_feature_by_name(name: str = Query(...), db=Depends(get_db)):
    """Delete a feature."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    return {"deleted": name}
