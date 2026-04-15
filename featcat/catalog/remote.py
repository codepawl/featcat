"""Remote HTTP backend for the feature catalog.

Connects to a running featcat server via HTTP.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

from .backend import CatalogBackend
from .models import DataSource, Feature


class RemoteBackend(CatalogBackend):
    """HTTP client backend that connects to a featcat server."""

    def __init__(self, server_url: str) -> None:
        self.server_url = server_url.rstrip("/")
        headers = {}
        token = os.environ.get("FEATCAT_SERVER_AUTH_TOKEN")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(base_url=self.server_url, timeout=30, headers=headers)

    # --- Lifecycle ---

    def init_db(self) -> None:
        """Remote backend does not support init_db."""
        raise NotImplementedError("Remote backend does not support init_db. Initialize the server directly.")

    def close(self) -> None:
        self._client.close()

    # --- Sources ---

    def add_source(self, source: Any) -> Any:
        data = source.model_dump(mode="json") if hasattr(source, "model_dump") else source
        result = self._request("POST", "/api/sources", json=data)
        return DataSource.model_validate(result)

    def get_source_by_name(self, name: str) -> Any | None:
        try:
            result = self._request("GET", f"/api/sources/{name}")
            return DataSource.model_validate(result)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def list_sources(self) -> list:
        result = self._request("GET", "/api/sources")
        return [DataSource.model_validate(s) for s in result]

    # --- Features ---

    def upsert_feature(self, feature: Any) -> Any:
        # upsert is handled server-side via scan; for individual features, PATCH is used
        return feature

    def list_features(self, source_name: str | None = None) -> list:
        params = {}
        if source_name:
            params["source"] = source_name
        result = self._request("GET", "/api/features", params=params)
        return [Feature.model_validate(f) for f in result]

    def get_feature_by_name(self, name: str) -> Any | None:
        try:
            result = self._request("GET", "/api/features/by-name", params={"name": name})
            return Feature.model_validate(result)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def update_feature_tags(self, feature_id: str, tags: list[str]) -> None:
        self._request("PATCH", "/api/features/by-name", params={"name": feature_id}, json={"tags": tags})

    def search_features(self, query: str) -> list:
        result = self._request("GET", "/api/features", params={"search": query})
        return [Feature.model_validate(f) for f in result]

    # --- Feature Docs ---

    def get_feature_doc(self, feature_id: str) -> dict | None:
        try:
            return self._request("GET", "/api/docs/by-name", params={"name": feature_id})
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def save_feature_doc(
        self,
        feature_id: str,
        doc: dict,
        model_used: str = "unknown",
        hints_used: str | None = None,
        context_features: list[str] | None = None,
    ) -> None:
        # Doc saving happens via generate endpoint on server
        pass

    def list_undocumented_features(self) -> list:
        # Get all features and doc stats to determine undocumented ones
        features = self.list_features()
        undoc = []
        for f in features:
            doc = self.get_feature_doc(f.id)
            if doc is None:
                undoc.append(f)
        return undoc

    def get_doc_stats(self) -> dict:
        return self._request("GET", "/api/docs/stats")

    def get_all_feature_docs(self) -> dict[str, dict]:
        features = self.list_features()
        docs = {}
        for f in features:
            doc = self.get_feature_doc(f.id)
            if doc is not None:
                docs[f.id] = doc
        return docs

    # --- Monitoring Baselines ---

    def get_baseline(self, feature_id: str) -> dict | None:
        # Not exposed as individual endpoint; use check endpoint
        return None

    def save_baseline(self, feature_id: str, stats: dict) -> None:
        # Baseline computation happens via server endpoint
        self._request("POST", "/api/monitor/baseline")

    # --- Feature Versions ---

    def list_feature_versions(self, feature_id: str) -> list[dict]:
        return []

    def get_feature_version(self, feature_id: str, version: int) -> dict | None:
        return None

    def rollback_feature(self, feature_id: str, version: int) -> dict:
        return {}

    # --- Stats ---

    def get_catalog_stats(self) -> dict:
        return self._request("GET", "/api/stats")

    # --- Source lookup by path ---

    def get_source_by_path(self, path: str) -> Any | None:
        sources = self.list_sources()
        for s in sources:
            if s.path == path:
                return s
        return None

    # --- Feature Groups ---

    def create_group(self, group: Any) -> Any:
        data = group.model_dump(mode="json") if hasattr(group, "model_dump") else group
        return self._request("POST", "/api/groups", json=data)

    def get_group_by_name(self, name: str) -> Any | None:
        try:
            return self._request("GET", f"/api/groups/{name}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def list_groups(self, project: str | None = None) -> list:
        params = {}
        if project:
            params["project"] = project
        return self._request("GET", "/api/groups", params=params)

    def update_group(self, group_id: str, **kwargs: object) -> None:
        self._request("PATCH", f"/api/groups/{group_id}", json=kwargs)

    def delete_group(self, group_id: str) -> None:
        self._request("DELETE", f"/api/groups/{group_id}")

    def add_group_members(self, group_id: str, feature_ids: list[str]) -> int:
        result = self._request("POST", f"/api/groups/{group_id}/members", json={"feature_ids": feature_ids})
        return result.get("added", 0)

    def remove_group_member(self, group_id: str, feature_id: str) -> None:
        self._request("DELETE", f"/api/groups/{group_id}/members", params={"spec": feature_id})

    def list_group_members(self, group_id: str) -> list:
        result = self._request("GET", f"/api/groups/{group_id}")
        return [Feature.model_validate(f) for f in result.get("members", [])]

    def count_group_members(self, group_id: str) -> int:
        result = self._request("GET", f"/api/groups/{group_id}")
        return result.get("member_count", 0)

    # --- Feature Definitions ---

    def set_feature_definition(self, feature_id: str, definition: str, definition_type: str) -> None:
        self._request("PUT", "/api/features/by-name/definition", params={"name": feature_id},
                       json={"definition": definition, "definition_type": definition_type})

    def get_feature_definition(self, feature_id: str) -> dict | None:
        try:
            return self._request("GET", "/api/features/by-name/definition", params={"name": feature_id})
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def clear_feature_definition(self, feature_id: str) -> None:
        self._request("DELETE", "/api/features/by-name/definition", params={"name": feature_id})

    # --- Usage Tracking ---

    def log_usage(self, feature_id: str, action: str, user: str = "", context: str = "") -> None:
        pass  # Usage is logged server-side

    def get_top_features(self, limit: int = 10, days: int = 30) -> list[dict]:
        return self._request("GET", "/api/usage/top", params={"limit": str(limit), "days": str(days)})

    def get_orphaned_features(self, days: int = 30) -> list[dict]:
        return self._request("GET", "/api/usage/orphaned", params={"days": str(days)})

    def get_usage_activity(self, days: int = 7) -> list[dict]:
        return self._request("GET", "/api/usage/activity", params={"days": str(days)})

    def get_feature_usage(self, feature_id: str, days: int = 30) -> dict:
        return self._request("GET", "/api/usage/feature", params={"name": feature_id, "days": str(days)})

    # --- Generation Hints ---

    def set_feature_hint(self, feature_id: str, hint: str) -> None:
        self._request("PATCH", "/api/features/by-name/hints",
                       params={"name": feature_id}, json={"hints": hint})

    def get_feature_hint(self, feature_id: str) -> str | None:
        try:
            result = self._request("GET", "/api/features/by-name",
                                    params={"name": feature_id})
            return result.get("generation_hints")
        except httpx.HTTPStatusError:
            return None

    def clear_feature_hint(self, feature_id: str) -> None:
        self._request("DELETE", "/api/features/by-name/hints",
                       params={"name": feature_id})

    # --- Visualization Queries ---

    def get_doc_debt(self) -> list[dict]:
        return self._request("GET", "/api/stats/doc-debt")

    def get_monitoring_history(self, feature_name: str, days: int = 30) -> list[dict]:
        return self._request("GET", f"/api/monitor/history/{feature_name}", params={"days": days})

    def save_monitoring_result(self, feature_id: str, feature_name: str, psi: float | None, severity: str) -> None:
        pass  # Server-side only

    def get_baseline_for_feature(self, feature_name: str) -> dict | None:
        return self._request("GET", f"/api/monitor/baseline/{feature_name}")

    def get_stats_by_source(self) -> list[dict]:
        return self._request("GET", "/api/stats/by-source")

    # --- Lineage ---

    def add_lineage(self, child_feature_id: str, parent_feature_id: str, transform: str = "") -> None:
        self._request("POST", "/api/lineage", json={"child": child_feature_id, "parent": parent_feature_id, "transform": transform})

    def remove_lineage(self, child_feature_id: str, parent_feature_id: str) -> None:
        self._request("DELETE", "/api/lineage", params={"child": child_feature_id, "parent": parent_feature_id})

    def get_lineage_graph(self) -> dict:
        return self._request("GET", "/api/lineage/graph")

    def get_feature_lineage(self, feature_name: str, direction: str = "both", depth: int = 3) -> dict:
        return self._request("GET", f"/api/lineage/feature/{feature_name}", params={"direction": direction, "depth": depth})

    # --- Server-side AI/plugin operations (used by CLI in remote mode) ---

    def ai_ask(self, query: str) -> dict:
        """Call the server's NL query endpoint."""
        return self._request("POST", "/api/ai/ask", json={"query": query}, timeout=60)

    def ai_discover(self, use_case: str) -> dict:
        """Call the server's discovery endpoint."""
        return self._request("POST", "/api/ai/discover", json={"use_case": use_case}, timeout=60)

    def doc_generate(self, feature_name: str | None = None) -> dict:
        """Call the server's doc generation endpoint."""
        body = {"feature_name": feature_name} if feature_name else {}
        return self._request("POST", "/api/docs/generate", json=body, timeout=120)

    def monitor_check(self, feature_name: str | None = None, use_llm: bool = False) -> dict:
        """Call the server's monitoring check endpoint."""
        params: dict = {}
        if feature_name:
            params["feature_name"] = feature_name
        if use_llm:
            params["use_llm"] = "true"
        return self._request("GET", "/api/monitor/check", params=params)

    def monitor_baseline(self) -> dict:
        """Call the server's baseline computation endpoint."""
        return self._request("POST", "/api/monitor/baseline")

    def _request(self, method: str, path: str, **kwargs) -> Any:
        """Make an HTTP request and handle errors."""
        timeout = kwargs.pop("timeout", None)
        try:
            if timeout:
                resp = self._client.request(method, path, timeout=timeout, **kwargs)
            else:
                resp = self._client.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as e:
            raise ConnectionError(f"Cannot connect to featcat server at {self.server_url}. Is it running?") from e
