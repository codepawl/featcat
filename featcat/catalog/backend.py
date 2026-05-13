"""Abstract interface for catalog storage backends."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any


class CatalogBackend(ABC):
    """Abstract interface for catalog storage.

    All CLI/TUI/plugins call these methods only.
    Implementations: LocalBackend (SQLite), RemoteBackend (HTTP).
    """

    # --- Lifecycle ---

    @abstractmethod
    def init_db(self) -> None:
        """Initialize the storage (create tables, etc.)."""

    @abstractmethod
    def close(self) -> None:
        """Close the connection."""

    # --- Sources ---

    @abstractmethod
    def add_source(self, source: Any) -> Any:
        """Insert a new data source. Accepts a DataSource model."""

    @abstractmethod
    def get_source_by_name(self, name: str) -> Any | None:
        """Look up a data source by its unique name."""

    @abstractmethod
    def list_sources(self) -> list:
        """Return all registered data sources."""

    # --- Features ---

    @abstractmethod
    def upsert_feature(self, feature: Any) -> Any:
        """Insert or update a feature (keyed on data_source_id + column_name)."""

    @abstractmethod
    def list_features(
        self,
        source_name: str | None = None,
        *,
        dtype: str | None = None,
        owner: str | None = None,
        tag: str | None = None,
        search: str | None = None,
        has_doc: bool | None = None,
        sort: str = "name",
        order: str = "asc",
        limit: int | None = None,
        offset: int = 0,
    ) -> list:
        """Return features matching filters, with optional server-side pagination.

        Calling with no args (or only ``source_name``) preserves the legacy
        full-list behaviour. Passing ``limit`` opts into pagination.
        """

    def count_features(
        self,
        source_name: str | None = None,
        *,
        dtype: str | None = None,
        owner: str | None = None,
        tag: str | None = None,
        search: str | None = None,
        has_doc: bool | None = None,
    ) -> int:
        """Count features matching the same filters as ``list_features``.

        Default implementation falls back to ``len(list_features(...))`` so
        backends without a dedicated count path (RemoteBackend) still satisfy
        the interface — at the cost of fetching the full set, which is fine
        for the small remote-mode usage.
        """
        return len(
            self.list_features(
                source_name,
                dtype=dtype,
                owner=owner,
                tag=tag,
                search=search,
                has_doc=has_doc,
            )
        )

    @abstractmethod
    def get_feature_by_name(self, name: str) -> Any | None:
        """Look up a feature by name."""

    @abstractmethod
    def update_feature_tags(self, feature_id: str, tags: list[str]) -> None:
        """Replace tags for a feature."""

    @abstractmethod
    def search_features(self, query: str) -> list:
        """Keyword search across name, description, tags, column_name."""

    @abstractmethod
    def list_feature_versions(self, feature_id: str) -> list[dict]:
        """Return all versions for a feature, ordered by version descending."""

    @abstractmethod
    def get_feature_version(self, feature_id: str, version: int) -> dict | None:
        """Return a specific version snapshot, or None if not found."""

    @abstractmethod
    def rollback_feature(self, feature_id: str, version: int) -> dict:
        """Restore feature metadata from a version snapshot. Creates a new version record."""

    # --- Feature Docs ---

    @abstractmethod
    def get_feature_doc(self, feature_id: str) -> dict | None:
        """Retrieve documentation for a feature by its ID."""

    @abstractmethod
    def save_feature_doc(
        self,
        feature_id: str,
        doc: dict,
        model_used: str = "unknown",
        hints_used: str | None = None,
        context_features: list[str] | None = None,
    ) -> None:
        """Save or replace documentation for a feature."""

    @abstractmethod
    def list_undocumented_features(self) -> list:
        """Find features without docs or with outdated docs."""

    @abstractmethod
    def get_doc_stats(self) -> dict:
        """Return doc coverage statistics: total, documented, undocumented, coverage %."""

    @abstractmethod
    def get_all_feature_docs(self) -> dict[str, dict]:
        """Return {feature_id: doc_dict} for all documented features."""

    # --- Monitoring Baselines ---

    @abstractmethod
    def get_baseline(self, feature_id: str) -> dict | None:
        """Retrieve baseline stats for a feature."""

    @abstractmethod
    def save_baseline(self, feature_id: str, stats: dict) -> None:
        """Save or replace baseline stats for a feature."""

    def get_latest_severity(self, feature_id: str) -> str | None:
        """Return the severity of the most recent monitoring_check for a feature.

        Default implementation returns None — backends without a direct
        monitoring_checks query (RemoteBackend) opt out cleanly. LocalBackend
        overrides this with a real query.
        """
        return None

    def get_impact(self, source_name: str, column: str | None = None, max_depth: int = 5) -> list:
        """Return features impacted (directly or transitively) by source[.column].

        Each item: ``{name, dtype, depth, via}``. RemoteBackend overrides via
        ``GET /api/lineage/impact``; default returns empty so plain backends
        without lineage data still satisfy the interface.
        """
        del source_name, column, max_depth
        return []

    def find_duplicate_pairs(
        self,
        threshold: float,
        limit: int,
        sources: list[str] | None = None,
    ) -> tuple[list[dict], int, str | None]:
        """Find feature pairs whose similarity score exceeds the threshold.

        Returns ``(pairs, total_before_limit, summary_message)``. Default
        implementation returns an empty result so backends without similarity
        data (e.g. RemoteBackend before the endpoint exists) satisfy the
        interface without raising. LocalBackend overrides with a real query.
        """
        del threshold, limit, sources
        return [], 0, None

    def full_text_search(
        self,
        query: str,
        *,
        source: str | None = None,
        tag: str | None = None,
        dtype: str | None = None,
        has_doc: bool | None = None,
        limit: int = 50,
    ) -> list:
        """Postgres tsvector / sqlite token-scan ranked search (T2.2a).

        Each item: ``{id, name, dtype, source, rank}``. Default empty so
        backends without the surface satisfy the interface; LocalBackend
        overrides with the real implementation.
        """
        del query, source, tag, dtype, has_doc, limit
        return []

    def search_facets(
        self,
        query: str | None = None,
        *,
        source: str | None = None,
        tag: str | None = None,
        dtype: str | None = None,
        has_doc: bool | None = None,
    ) -> dict:
        """Facet counts for the search sidebar. Default empty per facet."""
        del query, source, tag, dtype, has_doc
        return {"sources": [], "tags": [], "dtypes": [], "has_doc": {"true": 0, "false": 0}}

    def find_similar_features(self, feature_id: str, top_k: int = 10) -> list:
        """Return up to ``top_k`` features most similar to ``feature_id``.

        Each item: ``{id, name, dtype, similarity}`` (cosine in [0, 1]).
        Default returns empty so backends without the similarity surface
        still satisfy the interface; LocalBackend overrides with
        pgvector + TF-IDF fallback.
        """
        del feature_id, top_k
        return []

    # --- Feature lifecycle status (T3.1) ---

    def check_certification_readiness(self, feature_id: str) -> dict:
        """``{ready: bool, missing: list[str]}``. Default is the no-op stub
        for backends without persistence; LocalBackend overrides."""
        del feature_id
        return {"ready": False, "missing": ["not_implemented"]}

    def set_feature_status(self, feature_id: str, status: str, notes: str | None = None) -> dict:
        """Transition a feature's lifecycle status. Returns ``{ok, status, missing}``."""
        del feature_id, status, notes
        return {"ok": False, "status": "draft", "missing": ["not_implemented"]}

    def list_features_by_status(self, status: str) -> list:
        del status
        return []

    def get_status_counts(self) -> dict:
        """Return ``{draft, reviewed, certified, deprecated, total}`` counts.

        Default returns all-zero so RemoteBackend (and any other backend
        without a dedicated SQL path) cleanly satisfies the interface.
        LocalBackend overrides with a single ``GROUP BY status`` query —
        cheaper than fetching every row and counting client-side.
        """
        return {"draft": 0, "reviewed": 0, "certified": 0, "deprecated": 0, "total": 0}

    def search_by_embedding(self, query_vec: list[float], top_k: int = 50) -> list:
        """Return up to ``top_k`` features closest to a given query embedding.

        Postgres-only at the LocalBackend layer (uses pgvector ``<=>``);
        default empty so callers can fall through to alternate retrieval.
        Each item: ``{id, name, dtype, similarity}``.
        """
        del query_vec, top_k
        return []

    # --- In-app notifications (T2.1, in-web only) ---

    def create_notification(
        self,
        kind: str,
        title: str,
        body: str = "",
        severity: str = "info",
        feature_id: str | None = None,
        link: str | None = None,
    ) -> str:
        """Default no-op — backends without persistence return ``""``.
        LocalBackend overrides with a real INSERT. ``kind`` is one of
        ``drift|doc|action|info``; ``severity`` follows the monitoring
        vocabulary (``info|warning|critical``)."""
        del kind, title, body, severity, feature_id, link
        return ""

    def list_notifications(self, *, unread_only: bool = False, limit: int = 50, offset: int = 0) -> list:
        del unread_only, limit, offset
        return []

    def count_unread_notifications(self) -> int:
        return 0

    def mark_notification_read(self, notification_id: str) -> bool:
        del notification_id
        return False

    def mark_all_notifications_read(self) -> int:
        return 0

    # --- Stats ---

    @abstractmethod
    def get_catalog_stats(self) -> dict:
        """Return catalog overview: source count, feature count, doc coverage, monitoring summary."""

    # --- Source lookup by path ---

    @abstractmethod
    def get_source_by_path(self, path: str) -> Any | None:
        """Look up a data source by its file path."""

    # --- Source mutations + scan history ---

    def update_source(
        self,
        name: str,
        *,
        description: str | None = None,
        format: str | None = None,  # noqa: A002 — mirrors DataSource.format
    ) -> Any:
        """Update mutable fields on a registered source. Currently
        ``description`` and ``format`` only — ``name``, ``path`` and
        ``storage_type`` are immutable (renaming a source would invalidate
        every dependent feature's name prefix and is intentionally deferred).

        Default no-op so backends without persistence still satisfy the
        interface; LocalBackend overrides with a real UPDATE.
        """
        del description, format
        raise NotImplementedError(f"{type(self).__name__} does not support update_source ({name!r})")

    def delete_source(self, name: str) -> int:
        """Hard-delete a source and cascade-remove its features.

        Cleans up every dependent row (features and their child docs,
        baselines, monitoring checks, usage logs, group memberships,
        lineage edges, action items) before dropping the source. Returns
        the number of features removed. Raises ``KeyError`` if the source
        doesn't exist.

        Default raises NotImplementedError; LocalBackend overrides.
        """
        raise NotImplementedError(f"{type(self).__name__} does not support delete_source ({name!r})")

    def get_source_impact(self, name: str) -> dict:
        """Pre-delete impact summary: ``{features_count, groups: [{name, feature_count}]}``.

        Drives the delete-confirmation dialog. Default returns zeros so
        backends without persistence don't block the interface; LocalBackend
        overrides.
        """
        del name
        return {"features_count": 0, "groups": []}

    def record_scan_log(
        self,
        source_id: str,
        *,
        started_at: Any,
        finished_at: Any,
        duration_seconds: float,
        status: str,
        files_scanned: int = 0,
        features_added: int = 0,
        features_updated: int = 0,
        features_removed: int = 0,
        error_message: str | None = None,
        triggered_by: str = "api",
    ) -> str:
        """Persist one scan-attempt audit row. Returns the new log id.

        Default no-op (returns ``""``) so backends without persistence
        cleanly satisfy the interface; LocalBackend overrides.
        """
        del (
            source_id,
            started_at,
            finished_at,
            duration_seconds,
            status,
            files_scanned,
            features_added,
            features_updated,
            features_removed,
            error_message,
            triggered_by,
        )
        return ""

    def list_scan_logs(self, source_id: str, limit: int = 10) -> list:
        """Return scan-attempt rows for a source, newest first.

        Default empty so backends without persistence cleanly satisfy the
        interface; LocalBackend overrides.
        """
        del source_id, limit
        return []

    # --- Feature Groups ---

    @abstractmethod
    def create_group(self, group: Any) -> Any:
        """Create a new feature group."""

    @abstractmethod
    def get_group_by_name(self, name: str) -> Any | None:
        """Get a feature group by name."""

    @abstractmethod
    def list_groups(self, project: str | None = None) -> list:
        """List all feature groups, optionally filtered by project."""

    @abstractmethod
    def update_group(self, group_id: str, **kwargs: object) -> None:
        """Update group fields."""

    @abstractmethod
    def delete_group(self, group_id: str) -> None:
        """Delete a feature group."""

    @abstractmethod
    def add_group_members(self, group_id: str, feature_ids: list[str]) -> int:
        """Add features to a group. Returns count of newly added."""

    @abstractmethod
    def remove_group_member(self, group_id: str, feature_id: str) -> None:
        """Remove a feature from a group."""

    @abstractmethod
    def list_group_members(self, group_id: str) -> list:
        """List all features in a group."""

    @abstractmethod
    def count_group_members(self, group_id: str) -> int:
        """Count members in a group."""

    # --- Feature Group Versions (freeze + export) ---

    @abstractmethod
    def freeze_group(self, group_id: str, note: str = "", frozen_by: str = "") -> Any:
        """Snapshot a group's current members and return the new version.

        The snapshot is immutable: subsequent feature edits or deletions
        do not mutate prior versions.
        """

    @abstractmethod
    def list_group_versions(self, group_id: str) -> list:
        """List all frozen versions for a group, newest first."""

    @abstractmethod
    def get_group_version(self, group_id: str, version_number: int) -> Any | None:
        """Fetch one frozen version by group_id + version_number."""

    # --- Feature Definitions ---

    @abstractmethod
    def set_feature_definition(self, feature_id: str, definition: str, definition_type: str) -> None:
        """Set or update a feature's definition."""

    @abstractmethod
    def get_feature_definition(self, feature_id: str) -> dict | None:
        """Get a feature's definition."""

    @abstractmethod
    def clear_feature_definition(self, feature_id: str) -> None:
        """Remove a feature's definition."""

    # --- Usage Tracking ---

    @abstractmethod
    def log_usage(self, feature_id: str, action: str, user: str = "", context: str = "") -> None:
        """Log a usage event for a feature."""

    @abstractmethod
    def get_top_features(self, limit: int = 10, days: int = 30) -> list[dict]:
        """Get most-used features by action counts."""

    @abstractmethod
    def get_orphaned_features(self, days: int = 30) -> list[dict]:
        """Get features with zero usage in the given period."""

    @abstractmethod
    def get_usage_activity(self, days: int = 7) -> list[dict]:
        """Get per-day usage activity summary."""

    @abstractmethod
    def get_feature_usage(self, feature_id: str, days: int = 30) -> dict:
        """Get usage summary for a single feature."""

    # --- Generation Hints ---

    @abstractmethod
    def set_feature_hint(self, feature_id: str, hint: str) -> None:
        """Set generation hints for a feature."""

    @abstractmethod
    def get_feature_hint(self, feature_id: str) -> str | None:
        """Get generation hints for a feature."""

    @abstractmethod
    def clear_feature_hint(self, feature_id: str) -> None:
        """Remove generation hints for a feature."""

    # --- Visualization Queries ---

    @abstractmethod
    def get_doc_debt(self) -> list[dict]:
        """Return doc debt grouped by owner and source."""

    @abstractmethod
    def get_monitoring_history(self, feature_name: str, days: int = 30) -> list[dict]:
        """Return PSI check history for a feature."""

    @abstractmethod
    def save_monitoring_result(
        self,
        feature_id: str,
        feature_name: str,
        psi: float | None,
        severity: str,
        *,
        null_ratio: float | None = None,
        mean_z_score: float | None = None,
        sample_size: int | None = None,
    ) -> None:
        """Save a monitoring check result for history tracking.

        ``null_ratio``/``mean_z_score``/``sample_size`` are optional auxiliary
        metrics persisted alongside PSI for the multi-metric chart. They are
        nullable so legacy callers and rows where the metric isn't computable
        (e.g. non-numeric features for Z-score) still record correctly.
        """

    @abstractmethod
    def get_baseline_for_feature(self, feature_name: str) -> dict | None:
        """Retrieve baseline stats for a feature by name, including metadata."""

    @abstractmethod
    def get_feature_metric_history(self, feature_name: str, days: int = 30) -> list[dict]:
        """Return full per-check metric history (PSI + null_ratio + Z-score + sample_size).

        Superset of ``get_monitoring_history``; legacy rows have NULL for the
        new auxiliary metrics. Used by the multi-metric feature chart.
        """

    @abstractmethod
    def get_group_drift_matrix(self, group_id: str, days: int = 30) -> dict:
        """Return a 2D severity matrix (features × days) for the group.

        Caps at 200 features sorted by latest-severity priority then name.
        Returns ``{date_range, features: [{id, name, source, daily: [...]}],
        truncated, total_count}``.
        """

    @abstractmethod
    def get_catalog_drift_trend(self, days: int = 90) -> list[dict]:
        """Return per-day catalog-wide critical/warning percentages.

        For each of the last ``days`` days, computes the share of features
        whose latest-check-on-or-before-that-day has severity == 'critical'
        and == 'warning'. Used by the dashboard drift-rate trend chart.
        """

    @abstractmethod
    def get_stats_by_source(self) -> list[dict]:
        """Return per-source stats for dashboard visualization."""

    # --- Lineage ---

    @abstractmethod
    def add_lineage(self, child_feature_id: str, parent_feature_id: str, transform: str = "") -> None:
        """Add a lineage relationship (child derives from parent)."""

    @abstractmethod
    def remove_lineage(self, child_feature_id: str, parent_feature_id: str) -> None:
        """Remove a lineage relationship."""

    @abstractmethod
    def get_lineage_graph(self) -> dict:
        """Return full lineage graph as {nodes, edges}."""

    @abstractmethod
    def get_feature_lineage(self, feature_name: str, direction: str = "both", depth: int = 3) -> dict:
        """Return lineage tree for a single feature."""

    # --- Action Items (lifecycle loop) ---

    @abstractmethod
    def create_action_item(
        self,
        feature_id: str,
        source: str,
        title: str,
        recommendation: str,
        context: dict | None = None,
        created_by: str = "",
    ) -> str:
        """Create a recommended-action record. Returns the new item id."""

    @abstractmethod
    def find_pending_action(self, feature_id: str, source: str, title: str) -> dict | None:
        """Return the latest pending action with matching (feature_id, source, title) — for de-dup."""

    @abstractmethod
    def list_action_items(
        self,
        feature_id: str | None = None,
        status: str | None = None,
        source: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """List action items with optional filters."""

    @abstractmethod
    def get_action_item(self, item_id: str) -> dict | None:
        """Get a single action item by id."""

    @abstractmethod
    def update_action_item_status(
        self,
        item_id: str,
        status: str,
        applied_by: str = "",
        change_summary: str = "",
    ) -> bool:
        """Update status to one of: pending|applied|dismissed|snoozed. Returns True if updated."""

    @abstractmethod
    def count_action_items(self, status: str | None = None) -> int:
        """Count action items, optionally filtered by status."""

    @abstractmethod
    def save_monitoring_llm_analysis(self, feature_id: str, analysis: dict) -> None:
        """Persist LLM analysis JSON onto the latest monitoring_checks row for this feature."""
