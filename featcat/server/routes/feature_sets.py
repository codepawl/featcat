"""Feature set registry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ...catalog.models import FeatureSet  # noqa: TC001
from ..deps import get_db

router = APIRouter()


@router.get("")
def list_feature_sets(target_entity: str | None = None, owner: str | None = None, db=Depends(get_db)):  # noqa: B008
    return [item.model_dump(mode="json") for item in db.list_feature_sets(target_entity=target_entity, owner=owner)]


@router.get("/by-name")
def get_feature_set_by_name(name: str = Query(...), db=Depends(get_db)):  # noqa: B008
    item = db.get_feature_set_by_name(name)
    if item is None:
        raise HTTPException(status_code=404, detail=f"Feature set not found: {name}")
    return item.model_dump(mode="json")


@router.post("")
def upsert_feature_set(body: FeatureSet, db=Depends(get_db)):  # noqa: B008
    try:
        return db.upsert_feature_set(body).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
