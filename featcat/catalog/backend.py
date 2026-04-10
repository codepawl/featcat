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
    def save_feature_doc(self, feature_id: str, doc: dict, model_used: str = "unknown") -> None:
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
