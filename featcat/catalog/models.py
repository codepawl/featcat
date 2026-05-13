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
