"""Business metric registry endpoints."""

from __future__ import annotations

import csv
import io
import re
import unicodedata

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from ...catalog.models import BusinessMetric
from ..deps import get_db

router = APIRouter()
CSV_IMPORT_REQUIRED_FIELDS = {"Domain", "Metric Name", "Stage"}


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
    external_id: str = ""
    source_systems: list[str] = Field(default_factory=list)
    implementation_status: str = "unknown"
    source_view: str = ""


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
    external_id: str
    source_systems: list[str]
    implementation_status: str
    source_view: str
    created_at: str
    updated_at: str


class BusinessMetricCsvImportRequest(BaseModel):
    csv_text: str
    namespace: str = "cx360"
    owner: str = "cx360-import"
    dry_run: bool = False


class BusinessMetricCsvImportError(BaseModel):
    row: int
    metric_name: str = ""
    error: str


class BusinessMetricCsvImportResponse(BaseModel):
    total: int
    created: int
    updated: int
    skipped: int
    errors: list[BusinessMetricCsvImportError] = Field(default_factory=list)


def _response(metric: BusinessMetric) -> BusinessMetricResponse:
    payload = metric.model_dump(mode="json")
    payload["created_at"] = metric.created_at.isoformat()
    payload["updated_at"] = metric.updated_at.isoformat()
    return BusinessMetricResponse.model_validate(payload)


def _slug(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value.strip())
    ascii_value = normalized.encode("ascii", "ignore").decode("ascii").lower()
    slug = re.sub(r"[^a-z0-9]+", "_", ascii_value).strip("_")
    return slug or "metric"


def _normalize_domain(value: str) -> str:
    raw = value.strip().lower().replace(" ", "")
    if "market" in raw or "sales" in raw:
        return "market_sales"
    if "product" in raw:
        return "product"
    if "service" in raw:
        return "service"
    if "customer" in raw:
        return "customer"
    raise ValueError(f"unsupported Domain: {value!r}")


def _normalize_stage(value: str) -> str:
    raw = value.strip().lower().replace(" ", "").replace("_", "")
    if raw in {"customeprofile", "customerprofile", "profile"}:
        return "customer_profile"
    for stage in ("awareness", "consume", "manage", "pay", "renew", "recommend", "leave"):
        if stage in raw:
            return stage
    raise ValueError(f"unsupported Stage: {value!r}")


def _normalize_status(value: str) -> tuple[str, str]:
    raw = value.strip().lower()
    if not raw:
        return "unknown", "draft"
    if "done" in raw or "hoan thanh" in raw or "hoàn thành" in raw or "đã triển khai" in raw or "da trien khai" in raw:
        return "done", "validated"
    if "processing" in raw or "process" in raw or "dang" in raw or "đang" in raw:
        return "processing", "draft"
    if "not started" in raw or "chua" in raw or "chưa" in raw:
        return "not_started", "draft"
    return "unknown", "draft"


def _normalize_view(value: str) -> tuple[str, str, str]:
    raw = value.strip()
    lower = raw.lower()
    levels: list[str] = []
    if "device" in lower:
        levels.append("device")
    if "contract" in lower:
        levels.append("contract")
    if "customer" in lower:
        levels.append("customer")
    unique_levels = list(dict.fromkeys(levels))
    if not unique_levels:
        return "mixed", "mixed_id", f"Imported source view: {raw or 'unknown'}"
    entity_grain = f"{unique_levels[0]}_id"
    if len(unique_levels) == 1:
        return unique_levels[0], entity_grain, ""
    return "mixed", entity_grain, f"Imported source view: {raw}"


def _split_source_systems(value: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\s*(?:\+|;|,)\s*", value.strip()) if part.strip()]
    return parts


def _csv_cell(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ",".join(str(item or "") for item in value).strip()
    return str(value).strip()


def _records_from_csv(csv_text: str) -> list[dict[str, str]]:
    text = csv_text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(text))
    fieldnames = {(field or "").strip() for field in reader.fieldnames or []}
    missing = sorted(CSV_IMPORT_REQUIRED_FIELDS - fieldnames)
    if missing:
        raise ValueError(f"CSV missing required columns: {', '.join(missing)}")
    return [{key.strip(): _csv_cell(value) for key, value in row.items() if key} for row in reader]


def _metric_from_csv_row(row: dict[str, str], *, namespace: str, owner: str, name: str) -> BusinessMetric:
    metric_name = row.get("Metric Name", "").strip()
    if not metric_name:
        raise ValueError("Metric Name is required")
    metric_level, entity_grain, aggregation_rule = _normalize_view(row.get("View", ""))
    implementation_status, lifecycle_status = _normalize_status(row.get("Status", ""))
    return BusinessMetric(
        name=name,
        business_metric_name=metric_name,
        business_definition=row.get("Definition", ""),
        metric_domain=_normalize_domain(row.get("Domain", "")),
        lifecycle_stage=_normalize_stage(row.get("Stage", "")),
        metric_group=namespace,
        metric_level=metric_level,
        entity_grain=entity_grain,
        aggregation_rule=aggregation_rule,
        mapped_features=[],
        owner=owner,
        lifecycle_status=lifecycle_status,
        allowed_use_cases=[namespace],
        external_id=row.get("Metric Number", ""),
        source_systems=_split_source_systems(row.get("Data Sources", "")),
        implementation_status=implementation_status,
        source_view=row.get("View", ""),
    )


def _csv_metric_name(row: dict[str, str], *, namespace: str, seen: dict[str, int]) -> str:
    metric_name = row.get("Metric Name", "")
    metric_number = row.get("Metric Number", "")
    parts = [_slug(namespace)]
    if metric_number.strip():
        parts.append(_slug(metric_number))
    parts.append(_slug(metric_name))
    base = ".".join(parts)
    seen[base] = seen.get(base, 0) + 1
    if seen[base] == 1:
        return base
    return f"{base}.{seen[base]}"


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
            or needle in m.external_id.lower()
            or needle in m.implementation_status.lower()
            or needle in m.source_view.lower()
            or any(needle in feature.lower() for feature in m.mapped_features)
            or any(needle in source.lower() for source in m.source_systems)
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


@router.post("/import-csv", response_model=BusinessMetricCsvImportResponse)
def import_business_metrics_csv(
    body: BusinessMetricCsvImportRequest,
    db=Depends(get_db),  # noqa: B008
) -> BusinessMetricCsvImportResponse:
    """Import business metric definitions from the CX/Cus360 CSV shape."""
    try:
        rows = _records_from_csv(body.csv_text)
    except (csv.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"Invalid CSV: {exc}") from exc

    namespace = _slug(body.namespace)
    seen: dict[str, int] = {}
    created = 0
    updated = 0
    errors: list[BusinessMetricCsvImportError] = []

    for index, row in enumerate(rows, start=2):
        metric_name = row.get("Metric Name", "")
        try:
            name = _csv_metric_name(row, namespace=namespace, seen=seen)
            metric = _metric_from_csv_row(row, namespace=namespace, owner=body.owner, name=name)
            exists = db.get_business_metric_by_name(metric.name) is not None
            if body.dry_run:
                updated += int(exists)
                created += int(not exists)
            else:
                db.upsert_business_metric(metric)
                updated += int(exists)
                created += int(not exists)
        except ValueError as exc:
            errors.append(BusinessMetricCsvImportError(row=index, metric_name=metric_name, error=str(exc)))

    return BusinessMetricCsvImportResponse(
        total=len(rows),
        created=created,
        updated=updated,
        skipped=len(errors),
        errors=errors,
    )
