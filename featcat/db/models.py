"""SQLAlchemy ORM models — schema source of truth for the catalog DB.

Each model mirrors the legacy SCHEMA_SQL + ALTER TABLE migrations in
``featcat/catalog/local.py`` so a fresh-DB ``Base.metadata.create_all()`` produces
the same effective schema as the historical bootstrap.

Notes on column types:
- ``TIMESTAMP`` (not ``DATETIME``) is used everywhere because the legacy code
  registers ``sqlite3.register_converter("TIMESTAMP", ...)`` to parse ISO strings
  back into ``datetime`` objects. Renaming the declared type would silently
  break every caller that does ``row["created_at"].isoformat()``.
- ``Integer`` is used for boolean-ish columns (``enabled``, ``auto_refresh``)
  because the legacy schema declares them as ``INTEGER DEFAULT 0/1``.
- JSON-typed columns stay as ``Text`` because the application serializes JSON
  manually via ``json.dumps``/``json.loads``. Switching to ``JSON`` here would
  require touching every callsite — that belongs in Phase 2.
"""

from __future__ import annotations

# datetime is intentionally a runtime import (not TYPE_CHECKING-gated): SQLAlchemy
# resolves Mapped[datetime] dynamically when building the mapper, so the symbol
# must exist in the module namespace.
from datetime import datetime  # noqa: TC003

from sqlalchemy import (
    TIMESTAMP,
    Float,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from .embedding_type import Embedding

# Embedding dimension — must match the model in featcat/ai/embeddings.py.
# all-MiniLM-L6-v2 is 384-dim. Changing this requires re-embedding all
# features (background job ``embedding_refresh`` will detect dimension
# mismatch and rebuild).
EMBEDDING_DIM = 384


class Base(DeclarativeBase):
    pass


class DataSource(Base):
    __tablename__ = "data_sources"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    path: Mapped[str] = mapped_column(Text, nullable=False)
    storage_type: Mapped[str] = mapped_column(Text, nullable=False, default="local", server_default="local")
    format: Mapped[str] = mapped_column(Text, nullable=False, default="parquet", server_default="parquet")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    auto_refresh: Mapped[int] = mapped_column(Integer, default=0, server_default="0")


class Feature(Base):
    __tablename__ = "features"
    __table_args__ = (
        UniqueConstraint("data_source_id", "column_name", name="uq_features_source_column"),
        Index("idx_features_source", "data_source_id"),
        Index("idx_features_name", "name"),
        Index("idx_features_created_at", "created_at"),
        # Added in T1.4a — used by paginated /api/features filters and default
        # sort orders. The dtype index helps the WHERE f.dtype = X filter; the
        # updated_at index supports ORDER BY updated_at DESC pagination.
        Index("idx_features_dtype", "dtype"),
        Index("idx_features_updated_at", "updated_at"),
        Index("idx_features_status", "status"),  # T3.1 — filter-by-status pushdown
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    data_source_id: Mapped[str] = mapped_column(Text, ForeignKey("data_sources.id"), nullable=False)
    column_name: Mapped[str] = mapped_column(Text, nullable=False)
    dtype: Mapped[str] = mapped_column(Text, default="", server_default="")
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    tags: Mapped[str] = mapped_column(Text, default="[]", server_default="[]")
    owner: Mapped[str] = mapped_column(Text, default="", server_default="")
    stats: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    definition: Mapped[str | None] = mapped_column(Text)
    definition_type: Mapped[str | None] = mapped_column(Text)
    definition_updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    generation_hints: Mapped[str | None] = mapped_column(Text)
    # T1.2 — embedding for vector similarity search. ``vector(384)`` on postgres
    # (HNSW-indexed via Alembic migration), JSON-encoded TEXT on sqlite.
    # Populated by featcat/ai/embeddings.py; nullable so features without
    # embeddings yet (or when sentence-transformers isn't installed) work.
    embedding: Mapped[list | None] = mapped_column(Embedding(EMBEDDING_DIM))
    embedding_updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    # T3.1 — lifecycle status. Plain label, NOT a permission gate. Transitions
    # are loose (any → any allowed); the only gate is for ``certified``, which
    # ``LocalBackend.set_feature_status`` validates against the checklist in
    # ``check_certification_readiness``.
    status: Mapped[str] = mapped_column(Text, nullable=False, default="draft", server_default="draft")
    status_changed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    status_notes: Mapped[str | None] = mapped_column(Text)


class FeatureDoc(Base):
    __tablename__ = "feature_docs"
    # Legacy schema had no primary key; save_feature_doc enforces uniqueness via
    # DELETE-then-INSERT. We materialize feature_id as the PK here so SQLAlchemy's
    # ORM can map the table; this is a strict refinement of existing semantics.
    __table_args__ = (PrimaryKeyConstraint("feature_id", name="pk_feature_docs"),)

    feature_id: Mapped[str] = mapped_column(Text, ForeignKey("features.id"), nullable=False)
    short_description: Mapped[str] = mapped_column(Text, default="", server_default="")
    long_description: Mapped[str] = mapped_column(Text, default="", server_default="")
    expected_range: Mapped[str] = mapped_column(Text, default="", server_default="")
    potential_issues: Mapped[str] = mapped_column(Text, default="", server_default="")
    generated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    model_used: Mapped[str] = mapped_column(Text, default="", server_default="")
    hints_used: Mapped[str | None] = mapped_column(Text)
    context_features: Mapped[str | None] = mapped_column(Text)


class MonitoringBaseline(Base):
    __tablename__ = "monitoring_baselines"
    # Same PK rationale as feature_docs.
    __table_args__ = (PrimaryKeyConstraint("feature_id", name="pk_monitoring_baselines"),)

    feature_id: Mapped[str] = mapped_column(Text, ForeignKey("features.id"), nullable=False)
    baseline_stats: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    computed_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


class ScanLog(Base):
    """Audit row written each time a data source is scanned.

    One row per scan attempt (success or failure). Cascade-deletes with the
    parent source so the source detail UI's "scan history" section never
    surfaces orphaned rows. Distinct from ``job_logs`` — that table tracks
    APScheduler-driven jobs; this one tracks per-source scan operations
    triggered ad-hoc from the UI/CLI.
    """

    __tablename__ = "scan_logs"
    __table_args__ = (Index("idx_scan_logs_source_started", "source_id", "started_at"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str] = mapped_column(Text, ForeignKey("data_sources.id", ondelete="CASCADE"), nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    files_scanned: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    features_added: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    features_updated: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    features_removed: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    status: Mapped[str] = mapped_column(Text, nullable=False)  # "success" | "failed"
    error_message: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[str] = mapped_column(Text, nullable=False)  # "api" | "cli" | "scheduler"


class JobSchedule(Base):
    __tablename__ = "job_schedules"

    job_name: Mapped[str] = mapped_column(Text, primary_key=True)
    cron_expression: Mapped[str] = mapped_column(Text, nullable=False)
    enabled: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    last_run_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    next_run_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    max_log_retention_days: Mapped[int] = mapped_column(Integer, default=30, server_default="30")


class JobLog(Base):
    __tablename__ = "job_logs"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float)
    result_summary: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    error_message: Mapped[str | None] = mapped_column(Text)
    triggered_by: Mapped[str] = mapped_column(Text, nullable=False)


class FeatureVersion(Base):
    __tablename__ = "feature_versions"
    __table_args__ = (UniqueConstraint("feature_id", "version", name="uq_feature_versions_fid_ver"),)

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    feature_id: Mapped[str] = mapped_column(Text, ForeignKey("features.id", ondelete="CASCADE"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    change_summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    changed_by: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    change_type: Mapped[str] = mapped_column(Text, default="metadata", server_default="metadata")
    previous_value: Mapped[str | None] = mapped_column(Text)
    new_value: Mapped[str | None] = mapped_column(Text)


class FeatureGroup(Base):
    __tablename__ = "feature_groups"

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    name: Mapped[str] = mapped_column(Text, unique=True, nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", server_default="")
    project: Mapped[str] = mapped_column(Text, default="", server_default="")
    owner: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class FeatureGroupMember(Base):
    __tablename__ = "feature_group_members"
    __table_args__ = (
        PrimaryKeyConstraint("group_id", "feature_id", name="pk_feature_group_members"),
        Index("idx_group_members_group_feature", "group_id", "feature_id"),
    )

    group_id: Mapped[str] = mapped_column(Text, ForeignKey("feature_groups.id", ondelete="CASCADE"), nullable=False)
    feature_id: Mapped[str] = mapped_column(Text, ForeignKey("features.id", ondelete="CASCADE"), nullable=False)
    added_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class FeatureGroupVersion(Base):
    """Frozen snapshot of a group's members for reproducibility.

    Stored as JSON (snapshot_json) so re-derivation is impossible after
    freeze: a model trained on version N can always rebuild the exact
    feature manifest, even if the underlying features have since changed
    or been deleted.
    """

    __tablename__ = "feature_group_versions"
    __table_args__ = (
        UniqueConstraint("group_id", "version_number", name="uq_fgv_group_version"),
        Index("idx_fgv_group_version", "group_id", "version_number"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    group_id: Mapped[str] = mapped_column(Text, ForeignKey("feature_groups.id", ondelete="CASCADE"), nullable=False)
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot_json: Mapped[str] = mapped_column(Text, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", server_default="")
    frozen_by: Mapped[str] = mapped_column(Text, default="", server_default="")
    frozen_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class UsageLog(Base):
    __tablename__ = "usage_log"
    __table_args__ = (
        Index("idx_usage_log_feature", "feature_id"),
        Index("idx_usage_log_created", "created_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    feature_id: Mapped[str] = mapped_column(Text, ForeignKey("features.id"), nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    user: Mapped[str] = mapped_column(Text, default="", server_default="")
    context: Mapped[str] = mapped_column(Text, default="", server_default="")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class MonitoringCheck(Base):
    __tablename__ = "monitoring_checks"
    __table_args__ = (
        Index("idx_monitoring_checks_feature", "feature_name"),
        Index("idx_monitoring_checks_date", "checked_at"),
        # Composite indexes for the new chart endpoints — feature timeline scans
        # and catalog-wide drift-rate aggregation both benefit from a covering
        # leading column on the filter predicate.
        Index("idx_monitoring_checks_feature_date", "feature_id", "checked_at"),
        Index("idx_monitoring_checks_date_severity", "checked_at", "severity"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    feature_id: Mapped[str] = mapped_column(Text, ForeignKey("features.id"), nullable=False)
    feature_name: Mapped[str] = mapped_column(Text, nullable=False)
    psi: Mapped[float | None] = mapped_column(Float)
    severity: Mapped[str] = mapped_column(Text, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    llm_analysis_json: Mapped[str | None] = mapped_column(Text)
    # Per-check metrics added for the multi-metric feature chart. All nullable:
    # legacy rows have these as NULL; only checks performed after this column
    # landed will have values populated. Frontend handles the gap.
    null_ratio: Mapped[float | None] = mapped_column(Float)
    mean_z_score: Mapped[float | None] = mapped_column(Float)
    sample_size: Mapped[int | None] = mapped_column(Integer)


class FeatureLineage(Base):
    __tablename__ = "feature_lineage"
    __table_args__ = (
        # Pre-T1.1 the unique key was (child, parent_feature). Now widened to
        # cover source-column parents too — a feature can be derived from a
        # raw column instead of (or in addition to) another feature.
        UniqueConstraint(
            "child_feature_id",
            "parent_type",
            "parent_feature_id",
            "parent_source_id",
            "parent_column",
            name="uq_feature_lineage_pair",
        ),
        Index("idx_lineage_child", "child_feature_id"),
        Index("idx_lineage_parent", "parent_feature_id"),
        Index("idx_lineage_parent_source", "parent_source_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    child_feature_id: Mapped[str] = mapped_column(Text, ForeignKey("features.id", ondelete="CASCADE"), nullable=False)
    # parent_type discriminates what the parent is. Pre-T1.1 rows are backfilled
    # to 'feature'. New rows can also be 'source_column' (parent is a raw
    # column on a data source, not another feature).
    parent_type: Mapped[str] = mapped_column(Text, nullable=False, default="feature", server_default="feature")
    # parent_feature_id NULL when parent_type='source_column'.
    parent_feature_id: Mapped[str | None] = mapped_column(Text, ForeignKey("features.id", ondelete="CASCADE"))
    # parent_source_id + parent_column populated when parent_type='source_column'.
    # ondelete='SET NULL' so removing a source detaches the lineage record
    # rather than cascade-deleting it (downstream features keep their history).
    parent_source_id: Mapped[str | None] = mapped_column(Text, ForeignKey("data_sources.id", ondelete="SET NULL"))
    parent_column: Mapped[str | None] = mapped_column(Text)
    transform: Mapped[str] = mapped_column(Text, default="", server_default="")
    # detected_method tracks how the lineage was recorded — 'manual' (user
    # added via CLI/API), 'sql_parse' (sqlglot auto-detect from definition,
    # T1.1b), 'imported' (bulk import from external lineage source).
    detected_method: Mapped[str] = mapped_column(Text, nullable=False, default="manual", server_default="manual")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class ActionItem(Base):
    __tablename__ = "action_items"
    __table_args__ = (
        Index("idx_action_items_feature", "feature_id", "status"),
        Index("idx_action_items_status", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    feature_id: Mapped[str] = mapped_column(Text, ForeignKey("features.id", ondelete="CASCADE"), nullable=False)
    source: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    recommendation: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, default="pending", server_default="pending")
    created_by: Mapped[str] = mapped_column(Text, default="", server_default="")
    applied_by: Mapped[str] = mapped_column(Text, default="", server_default="")
    applied_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    change_summary: Mapped[str] = mapped_column(Text, default="", server_default="")
    context_json: Mapped[str] = mapped_column(Text, default="{}", server_default="{}")
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)


class Notification(Base):
    """In-app notification (T2.1 reframed — in-web only, no external integrations).

    The composite index on ``(read_at, created_at DESC)`` accelerates the
    most common query: ``SELECT … WHERE read_at IS NULL ORDER BY created_at
    DESC``. ``feature_id`` is nullable because catalog-wide notifications
    (e.g. "documentation generation finished") have no specific feature.
    Severity follows the monitoring vocabulary so a critical-drift alert
    can route through the same channel as a manually-emitted info note.
    """

    __tablename__ = "notifications"
    __table_args__ = (
        Index("idx_notifications_unread", "read_at", "created_at"),
        Index("idx_notifications_feature", "feature_id"),
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    kind: Mapped[str] = mapped_column(Text, nullable=False)  # 'drift' | 'doc' | 'action' | 'info'
    title: Mapped[str] = mapped_column(Text, nullable=False)
    body: Mapped[str] = mapped_column(Text, default="", server_default="")
    severity: Mapped[str] = mapped_column(Text, default="info", server_default="info")
    # Optional feature link — set when the notification refers to a specific feature.
    # ON DELETE SET NULL so deleting a feature doesn't cascade-delete history.
    feature_id: Mapped[str | None] = mapped_column(Text, ForeignKey("features.id", ondelete="SET NULL"))
    # Optional URL the UI can navigate to when the notification is clicked.
    link: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))


__all__ = [
    "ActionItem",
    "Base",
    "DataSource",
    "Feature",
    "FeatureDoc",
    "FeatureGroup",
    "FeatureGroupMember",
    "FeatureLineage",
    "FeatureVersion",
    "JobLog",
    "JobSchedule",
    "MonitoringBaseline",
    "MonitoringCheck",
    "Notification",
    "ScanLog",
    "UsageLog",
]
