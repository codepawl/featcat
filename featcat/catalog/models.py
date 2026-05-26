"""Pydantic models for the feature catalog."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class DataSource(BaseModel):
    """A registered data source (Parquet/CSV file or directory)."""

    id: str = Field(default_factory=_new_id)
    name: str
    path: str
    storage_type: str = "local"  # "local" | "s3"; auto-derived from path scheme when caller omits it
    format: str = "parquet"  # "parquet" | "csv"
    description: str = ""
    entity_key: str | None = None
    event_timestamp_column: str | None = None
    created_timestamp_column: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="before")
    @classmethod
    def _sync_storage_type(cls, data: Any) -> Any:
        """Auto-derive ``storage_type`` from the URI prefix when the caller
        didn't provide it; reject mismatches when they did.

        This closes audit gap #4: previously the field was decorative —
        runtime logic re-derived from the path prefix, so a caller could
        set ``storage_type="local"`` on an ``s3://`` path and the catalog
        silently accepted it. Lab catalog check (per the implementation
        plan) confirmed 0 existing mismatches, so this enforcement ships
        without a backfill migration.
        """
        if not isinstance(data, dict):
            return data
        path = data.get("path")
        if not isinstance(path, str) or not path:
            return data  # Let normal validation surface the missing/empty path error.
        derived = "s3" if path.startswith("s3://") else "local"
        if "storage_type" not in data or data["storage_type"] is None:
            data["storage_type"] = derived
            return data
        if data["storage_type"] != derived:
            raise ValueError(
                f"storage_type={data['storage_type']!r} does not match path scheme "
                f"(derived: {derived!r}, path: {path!r})"
            )
        return data


class Feature(BaseModel):
    """A single feature (column) extracted from a data source."""

    id: str = Field(default_factory=_new_id)
    name: str
    data_source_id: str
    column_name: str
    dtype: str = ""
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    owner: str = ""
    stats: dict[str, Any] = Field(default_factory=dict)
    definition: str | None = None
    definition_type: str | None = None  # "sql" | "python" | "manual"
    definition_updated_at: datetime | None = None
    generation_hints: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    # T3.1 lifecycle status — plain label, not a permission gate.
    status: str = "draft"
    status_changed_at: datetime | None = None
    status_notes: str | None = None


class FeatureDoc(BaseModel):
    """AI-generated documentation for a feature (Phase 2)."""

    feature_id: str
    short_description: str = ""
    long_description: str = ""
    expected_range: str = ""
    potential_issues: str = ""
    generated_at: datetime = Field(default_factory=_utcnow)
    model_used: str = ""


class MonitoringBaseline(BaseModel):
    """Baseline statistics for drift monitoring (Phase 3)."""

    feature_id: str
    baseline_stats: dict[str, Any] = Field(default_factory=dict)
    computed_at: datetime = Field(default_factory=_utcnow)


class FeatureGroup(BaseModel):
    """A named group of features for organizing related features."""

    id: str = Field(default_factory=_new_id)
    name: str
    description: str = ""
    project: str = ""
    owner: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


class FeatureGroupVersion(BaseModel):
    """Frozen snapshot of a group's members for reproducibility.

    ``snapshot_json`` is a JSON string capturing the group metadata and
    every member's name/dtype/definition/source at freeze time. Stored as
    a string (not a parsed dict) so it round-trips losslessly through the
    DB and the API without datetime/numeric coercion drift.
    """

    id: str = Field(default_factory=_new_id)
    group_id: str
    version_number: int
    snapshot_json: str
    note: str = ""
    frozen_by: str = ""
    frozen_at: datetime = Field(default_factory=_utcnow)


class UsageEvent(BaseModel):
    """A logged usage event for a feature."""

    id: str = Field(default_factory=_new_id)
    feature_id: str
    action: str  # "view" | "search" | "query" | "group_add"
    user: str = ""
    context: str = ""
    created_at: datetime = Field(default_factory=_utcnow)


class ColumnInfo(BaseModel):
    """Intermediate result from scanning a data source column."""

    column_name: str
    dtype: str
    stats: dict[str, Any] = Field(default_factory=dict)


class ScanLog(BaseModel):
    """Audit row for a single scan attempt against a data source."""

    id: str = Field(default_factory=_new_id)
    source_id: str
    started_at: datetime
    finished_at: datetime | None = None
    duration_seconds: float | None = None
    files_scanned: int = 0
    features_added: int = 0
    features_updated: int = 0
    features_removed: int = 0
    status: str  # "success" | "failed"
    error_message: str | None = None
    triggered_by: str  # "api" | "cli" | "scheduler"


class DatasetBuildAudit(BaseModel):
    """Audit row for an API/CLI training dataset build request."""

    id: str = Field(default_factory=_new_id)
    status: str  # "success" | "validation_failed" | "error"
    entity_df_path: str
    source_path: str | None = None
    source_name: str | None = None
    output_path: str | None = None
    entity_key: str | None = None
    entity_timestamp_column: str | None = None
    source_event_timestamp_column: str | None = None
    feature_columns: list[str] = Field(default_factory=list)
    row_count: int = 0
    feature_count: int = 0
    unresolved_row_count: int = 0
    missing_feature_value_count: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    actor: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class MaterializationAudit(BaseModel):
    """Audit row for an API/CLI online materialization request."""

    id: str = Field(default_factory=_new_id)
    schedule_id: str | None = None
    status: str  # "success" | "validation_failed" | "error"
    source_name: str
    source_path: str | None = None
    project: str = ""
    feature_view: str = ""
    entity_key: str | None = None
    event_timestamp_column: str | None = None
    created_timestamp_column: str | None = None
    feature_columns: list[str] = Field(default_factory=list)
    entity_count: int = 0
    feature_count: int = 0
    requested: int = 0
    written: int = 0
    skipped_older: int = 0
    skipped_same_timestamp: int = 0
    errors: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)
    actor: str | None = None
    created_at: datetime = Field(default_factory=_utcnow)


class MaterializationSchedule(BaseModel):
    """DB-backed interval schedule for latest-value online materialization."""

    id: str = Field(default_factory=_new_id)
    name: str
    source_name: str
    feature_columns: list[str] = Field(default_factory=list)
    project: str = ""
    feature_view: str = ""
    schedule_type: str = "interval"
    interval_seconds: int
    cron_expression: str | None = None
    enabled: bool = True
    actor: str | None = None
    last_run_at: datetime | None = None
    next_run_at: datetime | None = None
    lease_owner: str | None = None
    lease_until: datetime | None = None
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _validate_schedule(self) -> MaterializationSchedule:
        if not self.name.strip():
            raise ValueError("name is required")
        if not self.source_name.strip():
            raise ValueError("source_name is required")
        if not self.feature_columns:
            raise ValueError("feature_columns must be non-empty")
        if any(not column.strip() for column in self.feature_columns):
            raise ValueError("feature_columns must not contain empty values")
        if self.schedule_type != "interval":
            raise ValueError("schedule_type must be 'interval'")
        if self.interval_seconds <= 0:
            raise ValueError("interval_seconds must be greater than 0")
        return self


class OnlineFeatureWrite(BaseModel):
    """One latest-value write into the PostgreSQL online store."""

    entity_key: dict[str, Any]
    feature_ref: str
    value: Any = None
    value_dtype: str | None = None
    event_timestamp: datetime
    created_timestamp: datetime | None = None
    source_name: str | None = None
    source_path: str | None = None
    write_id: str | None = None


class OnlineFeatureWriteError(BaseModel):
    """Structured per-row validation/write error."""

    index: int
    code: str
    message: str
    field: str | None = None


class OnlineFeatureWriteResult(BaseModel):
    """Summary of a batch online-store write."""

    requested: int
    written: int = 0
    skipped_older: int = 0
    skipped_same_timestamp: int = 0
    errors: list[OnlineFeatureWriteError] = Field(default_factory=list)


class OnlineFeatureReadMetadata(BaseModel):
    """Per-feature online read metadata."""

    found: bool
    event_timestamp: datetime | None = None


class OnlineFeatureReadRow(BaseModel):
    """Online read result for one requested entity."""

    entity_key: dict[str, Any]
    features: dict[str, Any]
    metadata: dict[str, OnlineFeatureReadMetadata]


class OnlineFeatureReadResult(BaseModel):
    """Batch online-store read result preserving request order."""

    rows: list[OnlineFeatureReadRow]
