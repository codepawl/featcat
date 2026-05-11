"""Feature group endpoints."""

from __future__ import annotations

import contextlib
from datetime import date  # noqa: TC003 — Pydantic resolves at runtime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
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
            if isinstance(psi, (int, float)):
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
