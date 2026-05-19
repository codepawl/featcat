"""Source management endpoints."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ...catalog.models import DataSource, ScanLog
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


class SourceUpdate(BaseModel):
    """Mutable fields for ``PATCH /api/sources/{name}``.

    ``name``, ``path`` and ``storage_type`` are intentionally absent — renaming
    a source would invalidate every dependent feature's name prefix, so it's
    deferred (see plan's open-risks section). Description and format are the
    only fields a user can edit safely from the UI.
    """

    description: str | None = None
    format: str | None = None


class SourceImpactGroup(BaseModel):
    name: str
    feature_count: int


class SourceImpactResponse(BaseModel):
    """Pre-delete impact summary the UI shows in its confirm dialog."""

    features_count: int
    groups: list[SourceImpactGroup]


class DeleteResponse(BaseModel):
    deleted: str
    features_removed: int


class BulkDeleteSourcesRequest(BaseModel):
    names: list[str] = Field(..., min_length=1)
    confirm: bool = Field(False, description="Must be true to actually delete")


class BulkDeleteSourcesResponse(BaseModel):
    deleted: list[str]
    features_removed: int
    requested: int


class ScanResponse(BaseModel):
    source: str
    features_registered: int
    features_added: int
    features_updated: int
    scan_log_id: str


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


@router.patch("/{name}")
def update_source(name: str, body: SourceUpdate, db=Depends(get_db)):
    """Update mutable fields on a registered source."""
    try:
        updated = db.update_source(name, description=body.description, format=body.format)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    invalidate(prefix="sources:")
    invalidate(prefix="dashboard:")
    return updated.model_dump(mode="json")


@router.get("/{name}/impact", response_model=SourceImpactResponse)
def source_impact(name: str, db=Depends(get_db)):
    """Pre-delete impact summary: feature count + groups touched.

    Always returns 200 so the UI can render even when the source has
    been deleted in another tab — `features_count=0, groups=[]` then.
    """
    return db.get_source_impact(name)


@router.get("/{name}/scan-logs", response_model=list[ScanLog])
def list_source_scan_logs(name: str, limit: int = Query(10, ge=1, le=100), db=Depends(get_db)):
    """Return the most recent scan attempts for a source, newest first."""
    source = db.get_source_by_name(name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {name}")
    return db.list_scan_logs(source.id, limit=limit)


@router.post("/{name}/scan", response_model=ScanResponse)
def scan(name: str, db=Depends(get_db)):
    """Scan a data source and register its columns as features.

    Records one ``scan_logs`` audit row per attempt (success or failure)
    so the source detail UI's history section stays populated. ``features_added``
    vs ``features_updated`` is computed from the feature-count delta around
    the upsert loop — accurate without changing ``upsert_feature``'s signature.
    """
    from ...catalog.models import Feature

    source = db.get_source_by_name(name)
    if source is None:
        raise HTTPException(status_code=404, detail=f"Source not found: {name}")

    started = datetime.now(timezone.utc)
    perf_start = time.perf_counter()
    before = db.count_features(source_name=source.name)

    try:
        columns = scan_source(source.path)
    except Exception as e:
        finished = datetime.now(timezone.utc)
        db.record_scan_log(
            source.id,
            started_at=started,
            finished_at=finished,
            duration_seconds=time.perf_counter() - perf_start,
            status="failed",
            files_scanned=0,
            error_message=str(e),
            triggered_by="api",
        )
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

    after = db.count_features(source_name=source.name)
    added = max(0, after - before)
    updated = max(0, registered - added)
    finished = datetime.now(timezone.utc)
    log_id = db.record_scan_log(
        source.id,
        started_at=started,
        finished_at=finished,
        duration_seconds=time.perf_counter() - perf_start,
        status="success",
        files_scanned=1,
        features_added=added,
        features_updated=updated,
        triggered_by="api",
    )

    # Features changed — drop the features cache too so the detail UI sees
    # the new column list immediately.
    invalidate(prefix="sources:")
    invalidate(prefix="features:")
    invalidate(prefix="dashboard:")

    return {
        "source": name,
        "features_registered": registered,
        "features_added": added,
        "features_updated": updated,
        "scan_log_id": log_id,
    }


@router.delete("/{name}", response_model=DeleteResponse)
def delete_source(name: str, db=Depends(get_db)):
    """Hard-delete a source and cascade-remove its features.

    See ``LocalBackend.delete_source`` for the cascade contract — every
    dependent row (features + their docs/baselines/monitoring/usage,
    plus group memberships and lineage edges) is cleaned up.
    """
    try:
        removed = db.delete_source(name)
    except KeyError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    invalidate(prefix="sources:")
    invalidate(prefix="features:")
    invalidate(prefix="dashboard:")
    return {"deleted": name, "features_removed": removed}


@router.post("/bulk/delete", response_model=BulkDeleteSourcesResponse)
def bulk_delete_sources(body: BulkDeleteSourcesRequest, db=Depends(get_db)):  # noqa: B008
    """Hard-delete N sources and cascade-remove their features.

    All-or-nothing validation: if any name is unknown the endpoint returns
    400 with the invalid list and performs no deletions. Cascade rules
    match the single-source endpoint (see ``LocalBackend.delete_source``).
    Requires ``confirm: true`` so an accidental empty-confirm POST can't
    wipe sources.
    """
    if not body.confirm:
        raise HTTPException(
            status_code=400,
            detail="Bulk source delete requires `confirm: true` to prevent accidental destruction.",
        )
    invalid = [name for name in body.names if db.get_source_by_name(name) is None]
    if invalid:
        raise HTTPException(
            status_code=400,
            detail={"message": "Some sources do not exist.", "invalid_names": invalid},
        )
    features_removed = 0
    deleted: list[str] = []
    for name in body.names:
        features_removed += db.delete_source(name)
        deleted.append(name)
    invalidate(prefix="sources:")
    invalidate(prefix="features:")
    invalidate(prefix="dashboard:")
    return {
        "deleted": deleted,
        "features_removed": features_removed,
        "requested": len(body.names),
    }
