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

from pydantic import BaseModel, ConfigDict


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
