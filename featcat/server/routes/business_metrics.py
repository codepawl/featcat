"""Business metric registry endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ...catalog.models import BusinessMetric
from ..deps import get_db

router = APIRouter()


class BusinessMetricUpsertRequest(BaseModel):
    name: str
    business_metric_name: str
    business_definition: str = ""
    metric_domain: str
    lifecycle_stage: str
    metric_group: str = ""
    metric_level: str
    entity_grain: str
    aggregation_rule: str = ""
    mapped_features: list[str] = Field(default_factory=list)
    owner: str = ""
    lifecycle_status: str = "draft"
    allowed_use_cases: list[str] = Field(default_factory=list)


class BusinessMetricResponse(BaseModel):
    id: str
    name: str
    business_metric_name: str
    business_definition: str
    metric_domain: str
    lifecycle_stage: str
    metric_group: str
    metric_level: str
    entity_grain: str
    aggregation_rule: str
    mapped_features: list[str]
    owner: str
    lifecycle_status: str
    allowed_use_cases: list[str]
    created_at: str
    updated_at: str


def _response(metric: BusinessMetric) -> BusinessMetricResponse:
    payload = metric.model_dump(mode="json")
    payload["created_at"] = metric.created_at.isoformat()
    payload["updated_at"] = metric.updated_at.isoformat()
    return BusinessMetricResponse.model_validate(payload)


@router.get("")
def list_business_metrics(
    metric_domain: str | None = None,
    lifecycle_stage: str | None = None,
    metric_level: str | None = None,
    business_objective: str | None = None,
    owner: str | None = None,
    search: str | None = None,
    db=Depends(get_db),  # noqa: B008
) -> list[BusinessMetricResponse]:
    """List business metrics with taxonomy filters."""
    metrics = db.list_business_metrics(
        metric_domain=metric_domain,
        lifecycle_stage=lifecycle_stage,
        metric_level=metric_level,
        owner=owner,
    )
    if business_objective:
        metrics = [m for m in metrics if business_objective.lower() in (m.business_definition or "").lower()]
    if search:
        needle = search.lower()
        metrics = [
            m
            for m in metrics
            if needle in m.name.lower()
            or needle in m.business_metric_name.lower()
            or needle in m.business_definition.lower()
            or any(needle in feature.lower() for feature in m.mapped_features)
        ]
    return [_response(metric) for metric in metrics]


@router.get("/by-name")
def get_business_metric_by_name(name: str = Query(...), db=Depends(get_db)) -> BusinessMetricResponse:
    """Look up a business metric by name."""
    metric = db.get_business_metric_by_name(name)
    if metric is None:
        raise HTTPException(status_code=404, detail=f"Business metric not found: {name}")
    return _response(metric)


@router.post("", response_model=BusinessMetricResponse)
def upsert_business_metric(body: BusinessMetricUpsertRequest, db=Depends(get_db)) -> BusinessMetricResponse:
    """Insert or update a business metric definition."""
    metric = BusinessMetric.model_validate(body.model_dump())
    try:
        return _response(db.upsert_business_metric(metric))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
