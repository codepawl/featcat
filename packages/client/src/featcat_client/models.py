"""Pydantic models matching the featcat server response shapes.

The server uses ``str`` (UUID) IDs throughout — not integers. JSON-typed
columns (``tags``, ``stats``) are returned decoded by the server, so we
type them as ``list[str]`` / ``dict[str, Any]`` rather than as JSON strings.

``model_config = ConfigDict(extra="ignore")`` so server-side enrichments
(``health_score``, ``has_doc``, etc.) on the list/detail endpoints don't
break model parsing — the SDK exposes only the documented fields.
"""

from __future__ import annotations

# datetime is intentionally a runtime import (not TYPE_CHECKING-gated): pydantic
# resolves field annotations at model-construction time, so the symbol must
# exist in the module namespace.
from datetime import datetime  # noqa: TC003
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class _Base(BaseModel):
    model_config = ConfigDict(extra="ignore", frozen=False)


class Feature(_Base):
    id: str
    name: str
    data_source_id: str
    column_name: str
    dtype: str = ""
    description: str = ""
    tags: list[str] = []
    owner: str = ""
    stats: dict[str, Any] = {}
    definition: str | None = None
    definition_type: str | None = None
    generation_hints: str | None = None
    created_at: datetime
    updated_at: datetime


class DataSource(_Base):
    id: str
    name: str
    path: str
    storage_type: str = "local"
    format: str = "parquet"
    description: str = ""
    entity_key: str | None = None
    event_timestamp_column: str | None = None
    created_timestamp_column: str | None = None
    created_at: datetime
    updated_at: datetime


class DataSourceCreateRequest(_Base):
    """Payload for ``POST /api/sources``."""

    name: str
    path: str
    storage_type: str | None = None
    format: str = "parquet"
    description: str = ""
    entity_key: str | None = None
    event_timestamp_column: str | None = None
    created_timestamp_column: str | None = None


class DataSourceUpdateRequest(_Base):
    """Payload for ``PATCH /api/sources/{name}``."""

    description: str | None = None
    format: str | None = None
    entity_key: str | None = None
    event_timestamp_column: str | None = None
    created_timestamp_column: str | None = None


class SourceScanResult(_Base):
    """Shape returned by ``POST /api/sources/{name}/scan``."""

    source: str
    features_registered: int
    features_added: int
    features_updated: int
    scan_log_id: str


class BulkScanRequest(_Base):
    """Payload for ``POST /api/scan-bulk``."""

    path: str
    recursive: bool = False
    formats: list[str] = Field(default_factory=lambda: ["parquet", "csv"])
    owner: str = ""
    tags: list[str] = Field(default_factory=list)
    dry_run: bool = False


class BulkScanFile(_Base):
    """One file entry in ``BulkScanResponse``."""

    file: str
    status: str
    feature_count: int = 0
    error: str = ""


class BulkScanResult(_Base):
    """Shape returned by ``POST /api/scan-bulk``."""

    found: int
    registered_sources: int
    registered_features: int
    skipped: int
    details: list[BulkScanFile]


class EntityRelationshipJoinKey(_Base):
    """One join-key pair in ``EntityRelationship.join_keys``."""

    left_key: str
    right_key: str


class Entity(_Base):
    """Business or technical entity used as a catalog grain."""

    id: str
    name: str
    primary_keys: list[str] = Field(default_factory=list)
    join_keys: list[str] = Field(default_factory=list)
    description: str = ""
    owner: str = ""
    source_of_truth: str = ""
    lifecycle_status: str = "draft"
    created_at: datetime
    updated_at: datetime


class EntityCreateRequest(_Base):
    """Payload for ``POST /api/entities``."""

    name: str
    primary_keys: list[str] = Field(default_factory=list)
    join_keys: list[str] = Field(default_factory=list)
    description: str = ""
    owner: str = ""
    source_of_truth: str = ""
    lifecycle_status: str = "draft"


class EntityRelationship(_Base):
    """Relationship metadata between two entities."""

    id: str
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
    created_at: datetime
    updated_at: datetime


class EntityRelationshipCreateRequest(_Base):
    """Payload for ``POST /api/entity-relationships``."""

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


class FeatureView(_Base):
    """A grouped feature view over a target entity."""

    id: str
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
    created_at: datetime
    updated_at: datetime


class FeatureViewCreateRequest(_Base):
    """Payload for ``POST /api/feature-views``."""

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


class FeatureSet(_Base):
    """A model/use-case specific selection of features."""

    id: str
    name: str
    target_entity: str
    feature_names: list[str] = Field(default_factory=list)
    rollup_rules: dict[str, str] = Field(default_factory=dict)
    use_case: str = ""
    description: str = ""
    owner: str = ""
    lifecycle_status: str = "draft"
    created_at: datetime
    updated_at: datetime


class FeatureSetCreateRequest(_Base):
    """Payload for ``POST /api/feature-sets``."""

    name: str
    target_entity: str
    feature_names: list[str] = Field(default_factory=list)
    rollup_rules: dict[str, str] = Field(default_factory=dict)
    use_case: str = ""
    description: str = ""
    owner: str = ""
    lifecycle_status: str = "draft"


class BusinessMetric(_Base):
    """Business-facing metric mapped to one or more technical features."""

    id: str
    name: str
    business_metric_name: str
    business_definition: str
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
    created_at: datetime
    updated_at: datetime


class BusinessMetricCreateRequest(_Base):
    """Payload for ``POST /api/business-metrics``."""

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


class BusinessMetricCsvImportError(_Base):
    """One row-level error from ``POST /api/business-metrics/import-csv``."""

    row: int
    metric_name: str = ""
    error: str


class BusinessMetricCsvImportResult(_Base):
    """Import summary from ``POST /api/business-metrics/import-csv``."""

    total: int
    created: int
    updated: int
    skipped: int
    errors: list[BusinessMetricCsvImportError] = Field(default_factory=list)


class FlowResult(_Base):
    """Typed return value from ``flow(...)``."""

    source: DataSource
    entity: Entity
    feature_views: list[FeatureView]
    feature_set: FeatureSet
    source_feature_count: int
    scan_result: SourceScanResult


class FeatureGroup(_Base):
    """Group summary — the shape returned by ``GET /api/groups``."""

    id: str
    name: str
    description: str = ""
    project: str = ""
    owner: str = ""
    created_at: datetime
    updated_at: datetime


class FeatureGroupDetail(_Base):
    """Group with members — the shape returned by ``GET /api/groups/{name}``.

    Has ``to_polars()`` / ``to_pandas()`` helpers that join member features
    on a shared entity key (auto-detected or supplied).
    """

    group: FeatureGroup
    members: list[Feature]

    def to_polars(self, *, entity_key: str | None = None, source_resolver: Any = None) -> Any:
        """Read every member's parquet, join on ``entity_key``, return polars.

        ``source_resolver`` is a callable ``(source_name: str) -> DataSource``
        that the client supplies. Kept abstract here so models.py stays free
        of HTTP/io deps.
        """
        from ._dataframe import group_to_polars

        return group_to_polars(self, entity_key=entity_key, source_resolver=source_resolver)

    def to_pandas(self, *, entity_key: str | None = None, source_resolver: Any = None) -> Any:
        df = self.to_polars(entity_key=entity_key, source_resolver=source_resolver)
        return df.to_pandas()


class FeatureUsage(_Base):
    """Shape returned by ``GET /api/usage/feature?name=...``."""

    views: int = 0
    queries: int = 0
    total: int = 0
    last_seen: datetime | None = None
    daily: list[dict[str, Any]] = []


class TrainingDatasetIssue(_Base):
    """Structured validation issue from the training dataset builder."""

    code: str
    message: str
    field: str | None = None


class TrainingDatasetBuildResult(_Base):
    """Shape returned by ``POST /api/datasets/build``."""

    is_valid: bool
    errors: list[TrainingDatasetIssue] = []
    warnings: list[TrainingDatasetIssue] = []
    entity_df_path: str | None = None
    source_path: str | None = None
    entity_key: str | None = None
    entity_timestamp_column: str | None = None
    source_event_timestamp_column: str | None = None
    feature_columns: list[str] = []
    output_path: str | None = None
    row_count: int = 0
    feature_count: int = 0
    unresolved_row_count: int = 0
    missing_feature_value_count: int = 0


class TrainingDatasetBuildAudit(_Base):
    """Shape returned by ``GET /api/datasets/builds``."""

    id: str
    status: str
    entity_df_path: str
    source_path: str | None = None
    source_name: str | None = None
    output_path: str | None = None
    entity_key: str | None = None
    entity_timestamp_column: str | None = None
    source_event_timestamp_column: str | None = None
    feature_columns: list[str] = []
    row_count: int = 0
    feature_count: int = 0
    unresolved_row_count: int = 0
    missing_feature_value_count: int = 0
    errors: list[TrainingDatasetIssue] = []
    warnings: list[TrainingDatasetIssue] = []
    actor: str | None = None
    created_at: datetime


class OnlineFeatureWrite(_Base):
    """One online feature value write."""

    entity_key: dict[str, Any]
    feature_ref: str
    value: Any = None
    value_dtype: str | None = None
    event_timestamp: datetime
    created_timestamp: datetime | None = None
    source_name: str | None = None
    source_path: str | None = None
    write_id: str | None = None


class OnlineFeatureWriteError(_Base):
    """Structured per-row online write error."""

    index: int
    code: str
    message: str
    field: str | None = None


class OnlineFeatureWriteResult(_Base):
    """Shape returned by ``POST /api/online/write``."""

    requested: int
    written: int = 0
    skipped_older: int = 0
    skipped_same_timestamp: int = 0
    errors: list[OnlineFeatureWriteError] = []


class OnlineFeatureReadMetadata(_Base):
    """Per-feature metadata returned by online reads."""

    found: bool
    event_timestamp: datetime | None = None


class OnlineFeatureReadRow(_Base):
    """One entity row returned by ``POST /api/online/read``."""

    entity_key: dict[str, Any]
    features: dict[str, Any]
    metadata: dict[str, OnlineFeatureReadMetadata]


class OnlineFeatureReadResult(_Base):
    """Shape returned by ``POST /api/online/read``."""

    rows: list[OnlineFeatureReadRow]


class MaterializationIssue(_Base):
    """Structured materialization validation or write issue."""

    code: str
    message: str
    field: str | None = None


class MaterializationResult(_Base):
    """Shape returned by ``POST /api/online/materialize``."""

    is_valid: bool
    errors: list[MaterializationIssue] = []
    warnings: list[MaterializationIssue] = []
    source_name: str = ""
    source_path: str | None = None
    project: str = ""
    feature_view: str = ""
    entity_key: str | None = None
    event_timestamp_column: str | None = None
    created_timestamp_column: str | None = None
    feature_columns: list[str] = []
    entity_count: int = 0
    feature_count: int = 0
    requested: int = 0
    written: int = 0
    skipped_older: int = 0
    skipped_same_timestamp: int = 0


class MaterializationAudit(_Base):
    """Shape returned by ``GET /api/online/materializations``."""

    id: str
    status: str
    source_name: str
    source_path: str | None = None
    project: str = ""
    feature_view: str = ""
    entity_key: str | None = None
    event_timestamp_column: str | None = None
    created_timestamp_column: str | None = None
    feature_columns: list[str] = []
    entity_count: int = 0
    feature_count: int = 0
    requested: int = 0
    written: int = 0
    skipped_older: int = 0
    skipped_same_timestamp: int = 0
    errors: list[MaterializationIssue] = []
    warnings: list[MaterializationIssue] = []
    actor: str | None = None
    created_at: datetime


class MaterializationScheduleCreateRequest(_Base):
    """Body sent to ``POST /api/online/materialization-schedules``."""

    name: str
    source_name: str
    feature_columns: list[str]
    interval_seconds: int
    project: str = ""
    feature_view: str = ""
    enabled: bool = True
    actor: str | None = None


class MaterializationScheduleUpdateRequest(_Base):
    """Body sent to ``PATCH /api/online/materialization-schedules/{schedule_id}``."""

    enabled: bool


class MaterializationSchedule(_Base):
    """Shape returned by materialization schedule management endpoints."""

    id: str
    name: str
    source_name: str
    feature_columns: list[str]
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
    created_at: datetime
    updated_at: datetime


class MaterializationScheduleRunResult(_Base):
    """Shape returned by ``POST /api/online/materialization-schedules/{schedule_id}/run``."""

    schedule_id: str
    schedule_name: str
    status: str
    audit_id: str
