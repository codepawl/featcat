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

    def _request(self, method: str, path: str, **kwargs) -> Any:
        """Make an HTTP request and handle errors."""
        try:
            resp = self._client.request(method, path, **kwargs)
            resp.raise_for_status()
            return resp.json()
        except httpx.ConnectError as e:
            raise ConnectionError(f"Cannot connect to featcat server at {self.server_url}. Is it running?") from e

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
            result = self._request("GET", f"/api/features/{name}")
            return Feature.model_validate(result)
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def update_feature_tags(self, feature_id: str, tags: list[str]) -> None:
        self._request("PATCH", f"/api/features/{feature_id}", json={"tags": tags})

    def search_features(self, query: str) -> list:
        result = self._request("GET", "/api/features", params={"search": query})
        return [Feature.model_validate(f) for f in result]

    # --- Feature Docs ---

    def get_feature_doc(self, feature_id: str) -> dict | None:
        try:
            return self._request("GET", f"/api/docs/{feature_id}")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 404:
                return None
            raise

    def save_feature_doc(self, feature_id: str, doc: dict, model_used: str = "unknown") -> None:
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

    # --- Stats ---

    def get_catalog_stats(self) -> dict:
        return self._request("GET", "/api/stats")
