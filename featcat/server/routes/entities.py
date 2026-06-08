"""Entity registry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ...catalog.models import Entity  # noqa: TC001
from ..deps import get_db

router = APIRouter()


@router.get("")
def list_entities(db=Depends(get_db)):  # noqa: B008
    """List all registered entities."""
    return [entity.model_dump(mode="json") for entity in db.list_entities()]


@router.get("/by-name")
def get_entity_by_name(name: str = Query(...), db=Depends(get_db)):  # noqa: B008
    """Look up an entity by name."""
    entity = db.get_entity_by_name(name)
    if entity is None:
        raise HTTPException(status_code=404, detail=f"Entity not found: {name}")
    return entity.model_dump(mode="json")


@router.post("", response_model=dict)
def upsert_entity(body: Entity, db=Depends(get_db)):  # noqa: B008
    """Insert or update an entity definition."""
    try:
        return db.upsert_entity(body).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
