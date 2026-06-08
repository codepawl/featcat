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
    entity_grain: str | None = None
    business_metric_name: str | None = None
    metric_domain: str | None = None
    lifecycle_stage: str | None = None
    metric_group: str | None = None
    metric_level: str | None = None
    business_objective: str | None = None
    leakage_risk: str = "low"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)
    # T3.1 lifecycle status — plain label, not a permission gate.
    status: str = "draft"
    status_changed_at: datetime | None = None
    status_notes: str | None = None


METRIC_DOMAINS = {
    "network_quality",
    "device_intel",
    "customer_experience",
    "billing",
    "service_ops",
    "contact",
    "customer_profile",
}
LIFECYCLE_STAGES = {"consume", "manage", "leave"}
METRIC_LEVELS = {"device", "contract", "customer", "mixed"}
LIFECYCLE_STATUSES = {"draft", "validated", "production", "deprecated"}
RELATION_TYPES = {"one_to_one", "one_to_many", "many_to_one", "many_to_many"}


class Entity(BaseModel):
    """Business or technical entity used as a catalog grain."""

    id: str = Field(default_factory=_new_id)
    name: str
    primary_keys: list[str] = Field(default_factory=list)
    join_keys: list[str] = Field(default_factory=list)
    description: str = ""
    owner: str = ""
    source_of_truth: str = ""
    lifecycle_status: str = "draft"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _validate_entity(self) -> Entity:
        if not self.name.strip():
            raise ValueError("name is required")
        if not self.primary_keys:
            raise ValueError("primary_keys must be non-empty")
        if any(not key.strip() for key in self.primary_keys):
            raise ValueError("primary_keys must not contain empty values")
        if any(not key.strip() for key in self.join_keys):
            raise ValueError("join_keys must not contain empty values")
        if self.lifecycle_status not in LIFECYCLE_STATUSES:
            raise ValueError(f"lifecycle_status must be one of {sorted(LIFECYCLE_STATUSES)}")
        return self


class EntityRelationshipJoinKey(BaseModel):
    """One join-key mapping between two entities."""

    left_key: str
    right_key: str

    @model_validator(mode="after")
    def _validate_join_key(self) -> EntityRelationshipJoinKey:
        if not self.left_key.strip() or not self.right_key.strip():
            raise ValueError("join keys must not be empty")
        return self


class EntityRelationship(BaseModel):
    """Relationship metadata between two entities."""

    id: str = Field(default_factory=_new_id)
    name: str
    left_entity: str
    right_entity: str
    relation_type: str
    join_keys: list[EntityRelationshipJoinKey] = Field(default_factory=list)
    valid_from: str | None = None
    valid_to: str | None = None
    event_time: str | None = None
    description: str = ""
    owner: str = ""
    lifecycle_status: str = "draft"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _validate_relationship(self) -> EntityRelationship:
        if not self.name.strip():
            raise ValueError("name is required")
        if not self.left_entity.strip() or not self.right_entity.strip():
            raise ValueError("left_entity and right_entity are required")
        if self.left_entity == self.right_entity:
            raise ValueError("left_entity and right_entity must differ")
        if self.relation_type not in RELATION_TYPES:
            raise ValueError(f"relation_type must be one of {sorted(RELATION_TYPES)}")
        if not self.join_keys:
            raise ValueError("join_keys must be non-empty")
        if self.lifecycle_status not in LIFECYCLE_STATUSES:
            raise ValueError(f"lifecycle_status must be one of {sorted(LIFECYCLE_STATUSES)}")
        return self


class BusinessMetric(BaseModel):
    """Business-facing metric mapped to one or more technical features."""

    id: str = Field(default_factory=_new_id)
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
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _validate_business_metric(self) -> BusinessMetric:
        if not self.name.strip():
            raise ValueError("name is required")
        if not self.business_metric_name.strip():
            raise ValueError("business_metric_name is required")
        if self.metric_domain not in METRIC_DOMAINS:
            raise ValueError(f"metric_domain must be one of {sorted(METRIC_DOMAINS)}")
        if self.lifecycle_stage not in LIFECYCLE_STAGES:
            raise ValueError(f"lifecycle_stage must be one of {sorted(LIFECYCLE_STAGES)}")
        if self.metric_level not in METRIC_LEVELS:
            raise ValueError(f"metric_level must be one of {sorted(METRIC_LEVELS)}")
        if not self.entity_grain.strip():
            raise ValueError("entity_grain is required")
        if self.metric_level == "mixed" and not self.aggregation_rule.strip():
            raise ValueError("aggregation_rule is required when metric_level is mixed")
        technical_level = self._infer_entity_level(self.entity_grain)
        if technical_level and technical_level != self.metric_level and not self.aggregation_rule.strip():
            raise ValueError("aggregation_rule is required when metric_level differs from entity_grain")
        if not self.mapped_features:
            raise ValueError("mapped_features must be non-empty")
        if any(not feature_ref.strip() for feature_ref in self.mapped_features):
            raise ValueError("mapped_features must not contain empty values")
        if self.lifecycle_status not in LIFECYCLE_STATUSES:
            raise ValueError(f"lifecycle_status must be one of {sorted(LIFECYCLE_STATUSES)}")
        return self

    @staticmethod
    def _infer_entity_level(entity_grain: str) -> str | None:
        grain = entity_grain.strip().lower()
        if grain.endswith("_id"):
            grain = grain[:-3]
        if grain in METRIC_LEVELS:
            return grain
        return None


class FeatureView(BaseModel):
    """A grouped feature view over a target entity."""

    id: str = Field(default_factory=_new_id)
    name: str
    entity: str
    source_name: str = ""
    source_entity: str | None = None
    relationship: str | None = None
    aggregation: str = ""
    feature_names: list[str] = Field(default_factory=list)
    description: str = ""
    owner: str = ""
    lifecycle_status: str = "draft"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _validate_feature_view(self) -> FeatureView:
        if not self.name.strip():
            raise ValueError("name is required")
        if not self.entity.strip():
            raise ValueError("entity is required")
        if not self.feature_names:
            raise ValueError("feature_names must be non-empty")
        if any(not feature_name.strip() for feature_name in self.feature_names):
            raise ValueError("feature_names must not contain empty values")
        if self.source_entity and self.source_entity.strip() and self.source_entity != self.entity:
            if not self.relationship:
                raise ValueError("relationship is required when source_entity differs from entity")
            if not self.aggregation.strip():
                raise ValueError("aggregation is required when source_entity differs from entity")
        if self.lifecycle_status not in LIFECYCLE_STATUSES:
            raise ValueError(f"lifecycle_status must be one of {sorted(LIFECYCLE_STATUSES)}")
        return self


class FeatureSet(BaseModel):
    """A model/use-case specific selection of features."""

    id: str = Field(default_factory=_new_id)
    name: str
    target_entity: str
    feature_names: list[str] = Field(default_factory=list)
    rollup_rules: dict[str, str] = Field(default_factory=dict)
    use_case: str = ""
    description: str = ""
    owner: str = ""
    lifecycle_status: str = "draft"
    created_at: datetime = Field(default_factory=_utcnow)
    updated_at: datetime = Field(default_factory=_utcnow)

    @model_validator(mode="after")
    def _validate_feature_set(self) -> FeatureSet:
        if not self.name.strip():
            raise ValueError("name is required")
        if not self.target_entity.strip():
            raise ValueError("target_entity is required")
        if not self.feature_names:
            raise ValueError("feature_names must be non-empty")
        if any(not feature_name.strip() for feature_name in self.feature_names):
            raise ValueError("feature_names must not contain empty values")
        if any(not rule.strip() for rule in self.rollup_rules.values()):
            raise ValueError("rollup_rules must not contain empty values")
        if self.lifecycle_status not in LIFECYCLE_STATUSES:
            raise ValueError(f"lifecycle_status must be one of {sorted(LIFECYCLE_STATUSES)}")
        return self


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
    lifecycle_status: str = "draft"
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
