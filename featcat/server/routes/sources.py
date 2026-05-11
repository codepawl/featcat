"""Source management endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ...catalog.models import DataSource
from ...catalog.scanner import scan_source
from ...catalog.storage import validate_path_input
from ..cache import cache_get, cache_set, invalidate
from ..deps import get_db

router = APIRouter()


class SourceCreate(BaseModel):
    name: str
    path: str
    storage_type: str | None = None  # auto-derived from path if unset
    format: str = "parquet"
    description: str = ""


@router.post("")
def add_source(body: SourceCreate, db=Depends(get_db)):
    """Register a new data source."""
    try:
        validated_path = validate_path_input(body.path)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
    payload = body.model_dump()
    payload["path"] = validated_path
    try:
        source = DataSource(**payload)
    except ValueError as e:
        # DataSource's storage_type validator (Phase 5.3) raises on mismatch.
        raise HTTPException(status_code=422, detail=str(e)) from e
    try:
        db.add_source(source)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    # Source list + dashboard counters change — drop their cache entries.
    invalidate(prefix="sources:")
    invalidate(prefix="dashboard:")
    return source.model_dump(mode="json")


@router.get("")
def list_sources(db=Depends(get_db)):
    """List all registered data sources. Cached in-process for 600s."""
    cached = cache_get("sources:list")
    if cached is not None:
        return cached
    sources = db.list_sources()
    payload = [s.model_dump(mode="json") for s in sources]
    cache_set("sources:list", payload)
    return payload


@router.get("/{name}")
def get_source(name: str, db=Depends(get_db)):
    """Get a data source by name."""
    source = db.get_source_by_name(name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {name}")
    return source.model_dump(mode="json")


@router.post("/{name}/scan")
def scan(name: str, db=Depends(get_db)):
    """Scan a data source and register features."""
    from ...catalog.models import Feature

    source = db.get_source_by_name(name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {name}")

    try:
        columns = scan_source(source.path)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Scan failed: {e}") from e

    registered = 0
    for col in columns:
        feature_name = f"{source.name}.{col.column_name}"
        feature = Feature(
            name=feature_name,
            data_source_id=source.id,
            column_name=col.column_name,
            dtype=col.dtype,
            stats=col.stats,
        )
        db.upsert_feature(feature)
        registered += 1

    return {"source": name, "features_registered": registered}


@router.delete("/{name}")
def delete_source(name: str, db=Depends(get_db)):
    """Delete a data source (features are not deleted)."""
    source = db.get_source_by_name(name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {name}")
    invalidate(prefix="sources:")
    invalidate(prefix="dashboard:")
    # LocalBackend doesn't have delete_source yet, so we return a simple message
    return {"deleted": name}
