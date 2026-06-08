"""Entity relationship registry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ...catalog.models import EntityRelationship  # noqa: TC001
from ..deps import get_db

router = APIRouter()


@router.get("")
def list_entity_relationships(
    left_entity: str | None = None,
    right_entity: str | None = None,
    relation_type: str | None = None,
    db=Depends(get_db),  # noqa: B008
):
    """List entity relationships with optional filters."""
    relationships = db.list_entity_relationships(
        left_entity=left_entity,
        right_entity=right_entity,
        relation_type=relation_type,
    )
    return [relationship.model_dump(mode="json") for relationship in relationships]


@router.get("/by-name")
def get_entity_relationship_by_name(name: str = Query(...), db=Depends(get_db)):  # noqa: B008
    """Look up a relationship by name."""
    relationship = db.get_entity_relationship_by_name(name)
    if relationship is None:
        raise HTTPException(status_code=404, detail=f"Entity relationship not found: {name}")
    return relationship.model_dump(mode="json")


@router.post("", response_model=dict)
def upsert_entity_relationship(body: EntityRelationship, db=Depends(get_db)):  # noqa: B008
    """Insert or update an entity relationship definition."""
    try:
        return db.upsert_entity_relationship(body).model_dump(mode="json")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
