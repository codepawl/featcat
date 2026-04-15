"""Pydantic models for the feature catalog."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _new_id() -> str:
    return str(uuid.uuid4())


class DataSource(BaseModel):
    """A registered data source (Parquet/CSV file or directory)."""

    id: str = Field(default_factory=_new_id)
    name: str
    path: str
    storage_type: str = "local"  # "local" | "s3"
    format: str = "parquet"  # "parquet" | "csv"
    description: str = ""
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)


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
