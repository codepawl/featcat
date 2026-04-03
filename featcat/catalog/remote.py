"""Remote HTTP backend for the feature catalog (stub).

Will be implemented in server mode (Prompt 5.3).
"""

from __future__ import annotations

from typing import Any

from .backend import CatalogBackend


class RemoteBackend(CatalogBackend):
    """HTTP client backend that connects to a featcat server.

    Stub implementation — all methods raise NotImplementedError.
    Will be completed when server mode is implemented.
    """

    def __init__(self, server_url: str) -> None:
        self.server_url = server_url.rstrip("/")

    def init_db(self) -> None:
        raise NotImplementedError("Remote backend does not support init_db. Initialize the server directly.")

    def close(self) -> None:
        pass  # No persistent connection to close

    def add_source(self, source: Any) -> Any:
        raise NotImplementedError("RemoteBackend not yet implemented. Use local mode or start the featcat server.")

    def get_source_by_name(self, name: str) -> Any | None:
        raise NotImplementedError("RemoteBackend not yet implemented.")

    def list_sources(self) -> list:
        raise NotImplementedError("RemoteBackend not yet implemented.")

    def upsert_feature(self, feature: Any) -> Any:
        raise NotImplementedError("RemoteBackend not yet implemented.")

    def list_features(self, source_name: str | None = None) -> list:
        raise NotImplementedError("RemoteBackend not yet implemented.")

    def get_feature_by_name(self, name: str) -> Any | None:
        raise NotImplementedError("RemoteBackend not yet implemented.")

    def update_feature_tags(self, feature_id: str, tags: list[str]) -> None:
        raise NotImplementedError("RemoteBackend not yet implemented.")

    def search_features(self, query: str) -> list:
        raise NotImplementedError("RemoteBackend not yet implemented.")

    def get_feature_doc(self, feature_id: str) -> dict | None:
        raise NotImplementedError("RemoteBackend not yet implemented.")

    def save_feature_doc(self, feature_id: str, doc: dict, model_used: str = "unknown") -> None:
        raise NotImplementedError("RemoteBackend not yet implemented.")

    def list_undocumented_features(self) -> list:
        raise NotImplementedError("RemoteBackend not yet implemented.")

    def get_doc_stats(self) -> dict:
        raise NotImplementedError("RemoteBackend not yet implemented.")

    def get_all_feature_docs(self) -> dict[str, dict]:
        raise NotImplementedError("RemoteBackend not yet implemented.")

    def get_baseline(self, feature_id: str) -> dict | None:
        raise NotImplementedError("RemoteBackend not yet implemented.")

    def save_baseline(self, feature_id: str, stats: dict) -> None:
        raise NotImplementedError("RemoteBackend not yet implemented.")

    def get_catalog_stats(self) -> dict:
        raise NotImplementedError("RemoteBackend not yet implemented.")
