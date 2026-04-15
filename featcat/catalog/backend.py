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
    def list_features(self, source_name: str | None = None) -> list:
        """Return features, optionally filtered by source name."""

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

    # --- Stats ---

    @abstractmethod
    def get_catalog_stats(self) -> dict:
        """Return catalog overview: source count, feature count, doc coverage, monitoring summary."""

    # --- Source lookup by path ---

    @abstractmethod
    def get_source_by_path(self, path: str) -> Any | None:
        """Look up a data source by its file path."""

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
    def save_monitoring_result(self, feature_id: str, feature_name: str, psi: float | None, severity: str) -> None:
        """Save a monitoring check result for history tracking."""

    @abstractmethod
    def get_baseline_for_feature(self, feature_name: str) -> dict | None:
        """Retrieve baseline stats for a feature by name, including metadata."""

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
