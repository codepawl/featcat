"""Online feature store endpoints."""

from __future__ import annotations

# Pydantic needs datetime available at runtime to rebuild endpoint schemas.
from dataclasses import asdict
from datetime import datetime  # noqa: TC003
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ...catalog.materialization import MaterializationResult, materialize_latest_from_source
from ...catalog.models import (
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


@router.post("/materialize", response_model=OnlineMaterializationResponse)
def materialize_online_features(
    body: OnlineMaterializationRequest,
    db=Depends(get_db),
) -> OnlineMaterializationResponse:
    """Materialize latest values from a registered offline source into the online store."""
    # actor is accepted for forward-compatible audit attribution.
    result: MaterializationResult = materialize_latest_from_source(
        db,
        source_name=body.source_name,
        feature_columns=body.feature_columns,
        project=body.project,
        feature_view=body.feature_view,
    )
    return OnlineMaterializationResponse.model_validate(asdict(result))
