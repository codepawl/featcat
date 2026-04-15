"""Feature group endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...catalog.models import FeatureGroup
from ..deps import get_db

router = APIRouter()


class GroupCreate(BaseModel):
    name: str
    description: str = ""
    project: str = ""
    owner: str = ""


class GroupUpdate(BaseModel):
    description: str | None = None
    project: str | None = None
    owner: str | None = None


class MembersAdd(BaseModel):
    feature_specs: list[str]


@router.get("")
def list_groups(project: str | None = None, db=Depends(get_db)):  # noqa: B008
    """List all feature groups."""
    groups = db.list_groups(project=project)
    result = []
    for g in groups:
        d = g.model_dump(mode="json")
        d["member_count"] = db.count_group_members(g.id)
        result.append(d)
    return result


@router.post("")
def create_group(body: GroupCreate, db=Depends(get_db)):  # noqa: B008
    """Create a new feature group."""
    group = FeatureGroup(name=body.name, description=body.description, project=body.project, owner=body.owner)
    try:
        db.create_group(group)
    except Exception as e:
        raise HTTPException(status_code=409, detail=f"Group already exists: {body.name}") from e
    return group.model_dump(mode="json")


@router.get("/{name}")
def get_group(name: str, db=Depends(get_db)):  # noqa: B008
    """Get group detail with member features."""
    group = db.get_group_by_name(name)
    if group is None:
        raise HTTPException(status_code=404, detail=f"Group not found: {name}")
    members = db.list_group_members(group.id)
    result = group.model_dump(mode="json")
    result["member_count"] = len(members)
    result["members"] = [f.model_dump(mode="json") for f in members]
    return result


@router.patch("/{name}")
def update_group(name: str, body: GroupUpdate, db=Depends(get_db)):  # noqa: B008
    """Update group metadata."""
    group = db.get_group_by_name(name)
    if group is None:
        raise HTTPException(status_code=404, detail=f"Group not found: {name}")
    updates = body.model_dump(exclude_none=True)
    if updates:
        db.update_group(group.id, **updates)
    return {"updated": name}


@router.delete("/{name}")
def delete_group(name: str, db=Depends(get_db)):  # noqa: B008
    """Delete a feature group."""
    group = db.get_group_by_name(name)
    if group is None:
        raise HTTPException(status_code=404, detail=f"Group not found: {name}")
    db.delete_group(group.id)
    return {"deleted": name}


@router.post("/{name}/members")
def add_members(name: str, body: MembersAdd, db=Depends(get_db)):  # noqa: B008
    """Add features to a group by their specs (e.g. source.column)."""
    group = db.get_group_by_name(name)
    if group is None:
        raise HTTPException(status_code=404, detail=f"Group not found: {name}")

    feature_ids = []
    not_found = []
    for spec in body.feature_specs:
        feature = db.get_feature_by_name(spec)
        if feature is None:
            not_found.append(spec)
        else:
            feature_ids.append(feature.id)

    added = db.add_group_members(group.id, feature_ids) if feature_ids else 0
    result = {"added": added, "total_members": db.count_group_members(group.id)}
    if not_found:
        result["not_found"] = not_found
    return result


@router.delete("/{name}/members")
def remove_member(name: str, spec: str = Query(..., description="Feature spec to remove"), db=Depends(get_db)):  # noqa: B008
    """Remove a feature from a group."""
    group = db.get_group_by_name(name)
    if group is None:
        raise HTTPException(status_code=404, detail=f"Group not found: {name}")
    feature = db.get_feature_by_name(spec)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {spec}")
    db.remove_group_member(group.id, feature.id)
    return {"removed": spec}
