"""Online feature store endpoints."""

from __future__ import annotations

# Pydantic needs datetime available at runtime to rebuild endpoint schemas.
from dataclasses import asdict
from datetime import datetime  # noqa: TC003
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError

from ...catalog.materialization import MaterializationResult, materialize_latest_from_source
from ...catalog.materialization_audit import record_materialization_audit, record_materialization_error_audit
from ...catalog.materialization_scheduler import run_materialization_schedule_once
from ...catalog.models import (
    MaterializationAudit,
    MaterializationSchedule,
    OnlineFeatureReadMetadata,
    OnlineFeatureReadResult,
    OnlineFeatureWrite,
    OnlineFeatureWriteError,
    OnlineFeatureWriteResult,
)
from ..deps import get_db

router = APIRouter()


class OnlineFeatureWriteRow(BaseModel):
    entity_key: dict[str, Any]
    feature_ref: str
    value: Any = None
    value_dtype: str | None = None
    event_timestamp: datetime
    created_timestamp: datetime | None = None
    source_name: str | None = None
    source_path: str | None = None
    write_id: str | None = None


class OnlineFeatureWriteRequest(BaseModel):
    project: str = ""
    feature_view: str = ""
    source_name: str | None = None
    source_path: str | None = None
    actor: str | None = None
    rows: list[OnlineFeatureWriteRow] = Field(default_factory=list)


class OnlineFeatureWriteResponse(BaseModel):
    requested: int
    written: int
    skipped_older: int
    skipped_same_timestamp: int
    errors: list[OnlineFeatureWriteError]


class OnlineFeatureReadRequest(BaseModel):
    project: str = ""
    feature_view: str = ""
    entity_keys: list[dict[str, Any]] = Field(default_factory=list)
    feature_refs: list[str] = Field(default_factory=list)


class OnlineFeatureReadRowResponse(BaseModel):
    entity_key: dict[str, Any]
    features: dict[str, Any]
    metadata: dict[str, OnlineFeatureReadMetadata]


class OnlineFeatureReadResponse(BaseModel):
    rows: list[OnlineFeatureReadRowResponse]


class OnlineMaterializationIssueResponse(BaseModel):
    code: str
    message: str
    field: str | None = None


class OnlineMaterializationRequest(BaseModel):
    source_name: str
    feature_columns: list[str] = Field(default_factory=list)
    project: str = ""
    feature_view: str = ""
    actor: str | None = None


class OnlineMaterializationResponse(BaseModel):
    is_valid: bool
    errors: list[OnlineMaterializationIssueResponse]
    warnings: list[OnlineMaterializationIssueResponse]
    source_name: str
    source_path: str | None = None
    project: str
    feature_view: str
    entity_key: str | None = None
    event_timestamp_column: str | None = None
    created_timestamp_column: str | None = None
    feature_columns: list[str]
    entity_count: int
    feature_count: int
    requested: int
    written: int
    skipped_older: int
    skipped_same_timestamp: int


class OnlineMaterializationAuditResponse(BaseModel):
    id: str
    status: str
    source_name: str
    source_path: str | None = None
    project: str
    feature_view: str
    entity_key: str | None = None
    event_timestamp_column: str | None = None
    created_timestamp_column: str | None = None
    feature_columns: list[str]
    entity_count: int
    feature_count: int
    requested: int
    written: int
    skipped_older: int
    skipped_same_timestamp: int
    errors: list[dict]
    warnings: list[dict]
    actor: str | None = None
    created_at: str


class OnlineMaterializationScheduleCreateRequest(BaseModel):
    name: str
    source_name: str
    feature_columns: list[str]
    interval_seconds: int
    project: str = ""
    feature_view: str = ""
    enabled: bool = True
    actor: str | None = None


class OnlineMaterializationSchedulePatchRequest(BaseModel):
    enabled: bool


class OnlineMaterializationScheduleResponse(BaseModel):
    id: str
    name: str
    source_name: str
    feature_columns: list[str]
    project: str
    feature_view: str
    schedule_type: str
    interval_seconds: int
    cron_expression: str | None = None
    enabled: bool
    actor: str | None = None
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    lease_owner: str | None = None
    lease_until: datetime | None = None
    created_at: datetime
    updated_at: datetime


class OnlineMaterializationScheduleRunResponse(BaseModel):
    schedule_id: str
    schedule_name: str
    status: str
    audit_id: str


def _write_from_request(body: OnlineFeatureWriteRequest) -> list[OnlineFeatureWrite]:
    writes: list[OnlineFeatureWrite] = []
    for row in body.rows:
        payload = row.model_dump()
        if payload.get("source_name") is None:
            payload["source_name"] = body.source_name
        if payload.get("source_path") is None:
            payload["source_path"] = body.source_path
        writes.append(OnlineFeatureWrite.model_validate(payload))
    return writes


def _materialization_audit_response(row: MaterializationAudit) -> OnlineMaterializationAuditResponse:
    payload = row.model_dump()
    payload["created_at"] = row.created_at.isoformat()
    return OnlineMaterializationAuditResponse.model_validate(payload)


def _materialization_schedule_response(row: MaterializationSchedule) -> OnlineMaterializationScheduleResponse:
    return OnlineMaterializationScheduleResponse.model_validate(row.model_dump())


@router.post("/write", response_model=OnlineFeatureWriteResponse)
def write_online_features(body: OnlineFeatureWriteRequest, db=Depends(get_db)) -> OnlineFeatureWriteResponse:
    """Write latest online feature values."""
    # actor is accepted for forward-compatible audit attribution.
    result: OnlineFeatureWriteResult = db.write_online_features(
        _write_from_request(body),
        project=body.project,
        feature_view=body.feature_view,
    )
    return OnlineFeatureWriteResponse.model_validate(result.model_dump())


@router.post("/read", response_model=OnlineFeatureReadResponse)
def read_online_features(body: OnlineFeatureReadRequest, db=Depends(get_db)) -> OnlineFeatureReadResponse:
    """Read latest online feature values."""
    result: OnlineFeatureReadResult = db.get_online_features(
        entity_keys=body.entity_keys,
        feature_refs=body.feature_refs,
        project=body.project,
        feature_view=body.feature_view,
    )
    return OnlineFeatureReadResponse.model_validate(result.model_dump())


@router.get("/materializations", response_model=list[OnlineMaterializationAuditResponse])
def list_materialization_runs(
    limit: int = 20,
    status: str | None = None,
    db=Depends(get_db),
) -> list[OnlineMaterializationAuditResponse]:
    """List recent online materialization audit rows."""
    return [_materialization_audit_response(row) for row in db.list_materialization_audits(limit=limit, status=status)]


@router.get("/materialization-schedules", response_model=list[OnlineMaterializationScheduleResponse])
def list_materialization_schedules(
    limit: int = 20,
    enabled: bool | None = None,
    db=Depends(get_db),
) -> list[OnlineMaterializationScheduleResponse]:
    """List interval materialization schedules."""
    return [
        _materialization_schedule_response(row)
        for row in db.list_materialization_schedules(limit=limit, enabled=enabled)
    ]


@router.post("/materialization-schedules", response_model=OnlineMaterializationScheduleResponse)
def create_materialization_schedule(
    body: OnlineMaterializationScheduleCreateRequest,
    db=Depends(get_db),
) -> OnlineMaterializationScheduleResponse:
    """Create an interval materialization schedule."""
    try:
        schedule = db.create_materialization_schedule(
            name=body.name,
            source_name=body.source_name,
            feature_columns=body.feature_columns,
            interval_seconds=body.interval_seconds,
            project=body.project,
            feature_view=body.feature_view,
            enabled=body.enabled,
            actor=body.actor,
        )
    except ValidationError as exc:
        first_error = exc.errors()[0] if exc.errors() else {}
        detail = str(first_error.get("msg") or exc)
        if detail.startswith("Value error, "):
            detail = detail.removeprefix("Value error, ")
        raise HTTPException(status_code=400, detail=detail) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return _materialization_schedule_response(schedule)


@router.patch("/materialization-schedules/{schedule_id}", response_model=OnlineMaterializationScheduleResponse)
def patch_materialization_schedule(
    schedule_id: str,
    body: OnlineMaterializationSchedulePatchRequest,
    db=Depends(get_db),
) -> OnlineMaterializationScheduleResponse:
    """Enable or disable one interval materialization schedule."""
    schedule = db.set_materialization_schedule_enabled(schedule_id, body.enabled)
    if schedule is None:
        raise HTTPException(status_code=404, detail="Materialization schedule not found")
    return _materialization_schedule_response(schedule)


@router.post("/materialization-schedules/{schedule_id}/run", response_model=OnlineMaterializationScheduleRunResponse)
def run_materialization_schedule(
    schedule_id: str,
    db=Depends(get_db),
) -> OnlineMaterializationScheduleRunResponse:
    """Run one materialization schedule immediately."""
    record = run_materialization_schedule_once(db, schedule_id=schedule_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Materialization schedule not found")
    return OnlineMaterializationScheduleRunResponse(
        schedule_id=record.schedule_id,
        schedule_name=record.schedule_name,
        status=record.status,
        audit_id=record.audit_id,
    )


@router.post("/materialize", response_model=OnlineMaterializationResponse)
def materialize_online_features(
    body: OnlineMaterializationRequest,
    db=Depends(get_db),
) -> OnlineMaterializationResponse:
    """Materialize latest values from a registered offline source into the online store."""
    actor = body.actor or "api"
    try:
        result: MaterializationResult = materialize_latest_from_source(
            db,
            source_name=body.source_name,
            feature_columns=body.feature_columns,
            project=body.project,
            feature_view=body.feature_view,
        )
    except Exception as exc:
        record_materialization_error_audit(
            db,
            source_name=body.source_name,
            project=body.project,
            feature_view=body.feature_view,
            feature_columns=body.feature_columns,
            error=exc,
            actor=actor,
        )
        raise

    record_materialization_audit(db, result=result, actor=actor)
    return OnlineMaterializationResponse.model_validate(asdict(result))
