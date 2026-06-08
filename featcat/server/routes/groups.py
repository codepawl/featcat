"""Feature group endpoints."""

from __future__ import annotations

import contextlib
import csv
import io
import json
from datetime import date, datetime  # noqa: TC003 — Pydantic resolves these at runtime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import text

from ...catalog.health import compute_health_score
from ...catalog.models import FeatureGroup
from ..cache import cache_get, cache_set
from ..deps import get_db, get_llm

router = APIRouter()


class GroupCreate(BaseModel):
    name: str
    description: str = ""
    project: str = ""
    owner: str = ""
    lifecycle_status: str = "draft"


class GroupUpdate(BaseModel):
    description: str | None = None
    project: str | None = None
    owner: str | None = None
    lifecycle_status: str | None = None


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
    group = FeatureGroup(
        name=body.name,
        description=body.description,
        project=body.project,
        owner=body.owner,
        lifecycle_status=body.lifecycle_status,
    )
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


# ---------------------------------------------------------------------------
# Group aggregation: health, monitoring, batch doc regeneration
# ---------------------------------------------------------------------------


def _group_or_404(db, name: str):
    group = db.get_group_by_name(name)
    if group is None:
        raise HTTPException(status_code=404, detail=f"Group not found: {name}")
    return group


@router.get("/{name}/health")
def group_health(name: str, db=Depends(get_db)):  # noqa: B008
    """Aggregate health score and grade distribution for members of this group."""
    from .features import _bulk_health_data

    group = _group_or_404(db, name)
    members = db.list_group_members(group.id)
    if not members:
        return {
            "group": name,
            "member_count": 0,
            "average_score": 0,
            "grade_distribution": {"A": 0, "B": 0, "C": 0, "D": 0},
            "members": [],
            "lowest_scored": [],
        }

    all_docs, drift_map, usage_map = _bulk_health_data(db)
    grades: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    scored: list[dict] = []

    for f in members:
        usage = usage_map.get(f.id, {"views": 0, "queries": 0})
        health = compute_health_score(
            has_doc=f.id in all_docs,
            has_hints=bool(f.generation_hints),
            drift_status=drift_map.get(f.id),
            views_30d=usage["views"],
            queries_30d=usage["queries"],
        )
        grades[health["grade"]] = grades.get(health["grade"], 0) + 1
        scored.append(
            {
                "spec": f.name,
                "score": health["score"],
                "grade": health["grade"],
                "drift_status": drift_map.get(f.id, "unknown"),
                "has_doc": f.id in all_docs,
            }
        )

    scored.sort(key=lambda x: x["score"])
    avg = round(sum(s["score"] for s in scored) / len(scored))
    return {
        "group": name,
        "member_count": len(members),
        "average_score": avg,
        "grade_distribution": grades,
        "members": scored,
        "lowest_scored": scored[:5],
    }


@router.get("/{name}/monitoring")
def group_monitoring(name: str, db=Depends(get_db)):  # noqa: B008
    """Aggregate latest drift/PSI status across group members."""
    group = _group_or_404(db, name)
    members = db.list_group_members(group.id)

    severity_counts: dict[str, int] = {"healthy": 0, "warning": 0, "critical": 0, "unknown": 0}
    members_state: list[dict] = []
    psi_values: list[float] = []
    last_check: str | None = None

    with db.session() as s:
        for f in members:
            latest = None
            with contextlib.suppress(Exception):
                row = (
                    s.execute(
                        text(
                            "SELECT severity, psi, checked_at FROM monitoring_checks "
                            "WHERE feature_id = :fid ORDER BY checked_at DESC LIMIT 1"
                        ),
                        {"fid": f.id},
                    )
                    .mappings()
                    .first()
                )
                if row is not None:
                    latest = dict(row)

            severity = (latest or {}).get("severity") or "unknown"
            severity_counts[severity] = severity_counts.get(severity, 0) + 1
            psi = (latest or {}).get("psi")
            if isinstance(psi, int | float):
                psi_values.append(float(psi))
            checked = (latest or {}).get("checked_at")
            checked_str: str | None
            if checked is None:
                checked_str = None
            elif hasattr(checked, "isoformat"):
                checked_str = checked.isoformat()
            else:
                checked_str = str(checked)
            if checked_str and (last_check is None or checked_str > last_check):
                last_check = checked_str

            members_state.append(
                {
                    "spec": f.name,
                    "severity": severity,
                    "psi": psi,
                    "checked_at": checked_str,
                }
            )

    members_with_drift = [m for m in members_state if m["severity"] in ("warning", "critical")]
    return {
        "group": name,
        "member_count": len(members),
        "severity_counts": severity_counts,
        "psi_average": round(sum(psi_values) / len(psi_values), 4) if psi_values else None,
        "members_with_drift": members_with_drift,
        "members": members_state,
        "last_check_at": last_check,
    }


class GroupRegenerateDocsRequest(BaseModel):
    regenerate_existing: bool = False
    global_hint: str | None = None


@router.post("/{name}/regenerate-docs")
def group_regenerate_docs(
    name: str,
    body: GroupRegenerateDocsRequest,
    background_tasks: BackgroundTasks,
    db=Depends(get_db),  # noqa: B008
    llm=Depends(get_llm),  # noqa: B008
):
    """Kick off batch doc regeneration scoped to this group's members."""
    from .docs import _batch_jobs, _jobs_lock, _run_batch_generation

    if llm is None:
        raise HTTPException(status_code=503, detail="LLM not available. Is LLM server running?")

    group = _group_or_404(db, name)
    members = db.list_group_members(group.id)
    if not members:
        raise HTTPException(status_code=400, detail=f"Group is empty: {name}")

    if body.regenerate_existing:
        specs = [f.name for f in members]
    else:
        documented = db.get_all_feature_docs()
        specs = [f.name for f in members if f.id not in documented]
        if not specs:
            raise HTTPException(
                status_code=400,
                detail="All members already have docs. Pass regenerate_existing=true to overwrite.",
            )

    import uuid as _uuid

    job_id = str(_uuid.uuid4())
    with _jobs_lock:
        _batch_jobs[job_id] = {
            "job_id": job_id,
            "total": len(specs),
            "completed": 0,
            "failed": 0,
            "status": "running",
            "group": name,
        }

    background_tasks.add_task(
        _run_batch_generation,
        job_id=job_id,
        feature_specs=specs,
        global_hint=body.global_hint,
        db=db,
        llm=llm,
    )
    return {"job_id": job_id, "total": len(specs), "group": name}


# ---------------------------------------------------------------------------
# Group versioning: freeze, list, get, export
# ---------------------------------------------------------------------------


class FreezeRequest(BaseModel):
    note: str = ""
    frozen_by: str = ""


class FreezeResponse(BaseModel):
    group: str
    version_number: int
    frozen_at: datetime
    frozen_by: str
    note: str
    member_count: int
    warnings: list[str] = []


class VersionSummary(BaseModel):
    version_number: int
    frozen_at: datetime
    frozen_by: str
    note: str
    member_count: int


class VersionDetail(BaseModel):
    version_number: int
    frozen_at: datetime
    frozen_by: str
    note: str
    snapshot: dict
    warnings: list[str]


def _snapshot_member_count(snapshot_json: str) -> int:
    try:
        return len(json.loads(snapshot_json).get("features", []))
    except (ValueError, TypeError):
        return 0


def _annotate_snapshot_with_stale(db, snapshot_json: str) -> tuple[dict, list[str]]:
    """Decode snapshot JSON, mark features deleted-after-freeze, and return warnings.

    Stale check is by feature *name*, not id, because ids may collide if a
    user deletes-and-recreates with the same spec. Name+source-path is the
    reproducibility contract.
    """
    snapshot = json.loads(snapshot_json)
    warnings: list[str] = []
    group = snapshot.get("group") or {}
    if group.get("lifecycle_status") == "production":
        for feature in snapshot.get("features", []):
            if (feature.get("leakage_risk") or "low").lower() == "high":
                warnings.append(
                    f"Feature '{feature.get('name')}' has high leakage risk in "
                    f"production feature set '{group.get('name')}'."
                )
    for feature in snapshot.get("features", []):
        current = db.get_feature_by_name(feature.get("name", ""))
        if current is None:
            feature["deleted_after_freeze"] = True
            warnings.append(f"Feature '{feature.get('name')}' was deleted after this version was frozen.")
        else:
            feature["deleted_after_freeze"] = False
    return snapshot, warnings


@router.post("/{name}/freeze", response_model=FreezeResponse)
def freeze_group(name: str, body: FreezeRequest, db=Depends(get_db)):  # noqa: B008
    """Snapshot the group's current members as a new immutable version."""
    group = _group_or_404(db, name)
    if db.count_group_members(group.id) == 0:
        raise HTTPException(status_code=400, detail=f"Group is empty: {name}")
    version = db.freeze_group(group.id, note=body.note, frozen_by=body.frozen_by)
    member_count = _snapshot_member_count(version.snapshot_json)
    _, warnings = _annotate_snapshot_with_stale(db, version.snapshot_json)
    return FreezeResponse(
        group=name,
        version_number=version.version_number,
        frozen_at=version.frozen_at,
        frozen_by=version.frozen_by,
        note=version.note,
        member_count=member_count,
        warnings=warnings,
    )


@router.get("/{name}/versions", response_model=list[VersionSummary])
def list_group_versions(name: str, db=Depends(get_db)):  # noqa: B008
    """List frozen versions for the group, newest first."""
    group = _group_or_404(db, name)
    versions = db.list_group_versions(group.id)
    return [
        VersionSummary(
            version_number=v.version_number,
            frozen_at=v.frozen_at,
            frozen_by=v.frozen_by,
            note=v.note,
            member_count=_snapshot_member_count(v.snapshot_json),
        )
        for v in versions
    ]


@router.get("/{name}/versions/{version_number}", response_model=VersionDetail)
def get_group_version(name: str, version_number: int, db=Depends(get_db)):  # noqa: B008
    """Fetch one frozen version with the full snapshot and stale-feature warnings."""
    group = _group_or_404(db, name)
    version = db.get_group_version(group.id, version_number)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Version not found: {name} v{version_number}")
    snapshot, warnings = _annotate_snapshot_with_stale(db, version.snapshot_json)
    return VersionDetail(
        version_number=version.version_number,
        frozen_at=version.frozen_at,
        frozen_by=version.frozen_by,
        note=version.note,
        snapshot=snapshot,
        warnings=warnings,
    )


@router.get("/{name}/versions/{version_number}/export")
def export_group_version(  # noqa: PLR0911
    name: str,
    version_number: int,
    format: str = Query("json", pattern="^(json|csv|parquet)$"),  # noqa: A002 — preserves ?format=... URL contract
    db=Depends(get_db),  # noqa: B008
):
    """Export a frozen version as a feature *manifest* (not the underlying data values).

    Reproducibility contract: the manifest captures every feature's name,
    dtype, definition, and source path/format at freeze time. Re-running
    the pipeline against the same sources should yield matching columns.
    Features deleted from the catalog after freeze are flagged but still
    exported (per the plan: export-with-warning).
    """
    group = _group_or_404(db, name)
    version = db.get_group_version(group.id, version_number)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Version not found: {name} v{version_number}")
    snapshot, warnings = _annotate_snapshot_with_stale(db, version.snapshot_json)
    snapshot["warnings"] = warnings
    filename_stem = f"{name}-v{version_number}"

    if format == "json":
        body = json.dumps(snapshot, ensure_ascii=False, indent=2)
        return StreamingResponse(
            io.BytesIO(body.encode("utf-8")),
            media_type="application/json",
            headers={"Content-Disposition": f'attachment; filename="{filename_stem}.json"'},
        )

    columns = [
        "name",
        "dtype",
        "definition",
        "definition_type",
        "column_name",
        "source_name",
        "source_path",
        "source_format",
        "source_entity_key",
        "source_event_timestamp_column",
        "source_created_timestamp_column",
        "owner",
        "deleted_after_freeze",
    ]
    rows = [{c: f.get(c, "") for c in columns} for f in snapshot.get("features", [])]

    if format == "csv":
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=columns)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
        return StreamingResponse(
            io.BytesIO(buf.getvalue().encode("utf-8")),
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="{filename_stem}.csv"'},
        )

    # parquet
    try:
        import pyarrow as pa  # type: ignore[import-untyped]
        import pyarrow.parquet as pq  # type: ignore[import-untyped]
    except ImportError as e:  # pragma: no cover — pyarrow ships via parquet scanning deps
        raise HTTPException(status_code=503, detail="pyarrow is not installed") from e
    table = pa.Table.from_pylist([{c: str(r[c]) if r[c] is not None else "" for c in columns} for r in rows])
    buf_bytes = io.BytesIO()
    pq.write_table(table, buf_bytes)
    buf_bytes.seek(0)
    return StreamingResponse(
        buf_bytes,
        media_type="application/vnd.apache.parquet",
        headers={"Content-Disposition": f'attachment; filename="{filename_stem}.parquet"'},
    )


# ---------------------------------------------------------------------------
# Group drift heatmap (Chart 2)
# ---------------------------------------------------------------------------


class DriftMatrixCell(BaseModel):
    date: date
    severity: str
    psi: float | None


class DriftMatrixFeature(BaseModel):
    id: str
    name: str
    source: str
    daily: list[DriftMatrixCell]


class DriftMatrixResponse(BaseModel):
    """30-day severity matrix for a group's features.

    ``truncated=true`` and ``total_count > len(features)`` indicate the
    server capped the response at 200 features, sorted by latest severity
    priority then alphabetically.
    """

    date_range: list[date]
    features: list[DriftMatrixFeature]
    truncated: bool
    total_count: int


@router.get("/{name}/drift-matrix", response_model=DriftMatrixResponse)
def group_drift_matrix(
    name: str,
    days: int = Query(30, ge=7, le=90),
    db=Depends(get_db),  # noqa: B008
) -> DriftMatrixResponse:
    """Per-feature per-day severity matrix for the heatmap chart."""
    cache_key = f"groups:drift_matrix:{name}:{days}"
    cached = cache_get(cache_key)
    if cached is not None:
        return DriftMatrixResponse.model_validate(cached)
    group = _group_or_404(db, name)
    matrix = db.get_group_drift_matrix(group.id, days=days)
    response = DriftMatrixResponse.model_validate(matrix)
    cache_set(cache_key, response.model_dump(mode="json"))
    return response
