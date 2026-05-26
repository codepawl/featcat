"""HTTP client for the featcat server.

Sync-only (notebook-friendly). Retries 5xx with exponential backoff (max 3
attempts). Connection timeout 5s, read timeout 30s. Errors are wrapped in the
custom exception hierarchy from ``exceptions``; the underlying ``httpx``
errors aren't raised directly.

Server endpoints actually used (verified against ``featcat/server/routes/``):

- ``GET  /api/features``                  — list with filters + search
- ``GET  /api/features/by-name?name=X``   — single feature
- ``GET  /api/features/similarity-graph`` — similar features (graph format)
- ``GET  /api/sources``                   — list sources
- ``GET  /api/sources/{name}``            — single source (has parquet path)
- ``GET  /api/groups``                    — list groups
- ``GET  /api/groups/{name}``             — group with members
- ``POST /api/datasets/build``            — build local PIT training dataset
- ``GET  /api/datasets/builds``           — list recent dataset build audits
- ``POST /api/online/write``              — write online feature values
- ``POST /api/online/read``               — read online feature values
- ``GET  /api/usage/feature?name=X``      — usage stats for a feature

The server *auto-logs* a ``view`` action on every ``GET /api/features/by-name``
call, so the SDK doesn't need a separate ``log_usage`` round-trip — the
``actor`` parameter is passed as a custom header for traceability.
"""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any

import httpx

from . import __version__
from .exceptions import (
    ConnectionError,
    FeatCatError,
    FeatureNotFound,
    GroupNotFound,
    ServerError,
)
from .models import (
    DataSource,
    Feature,
    FeatureGroup,
    FeatureGroupDetail,
    FeatureUsage,
    OnlineFeatureReadResult,
    OnlineFeatureWrite,
    OnlineFeatureWriteResult,
    TrainingDatasetBuildAudit,
    TrainingDatasetBuildResult,
)

if TYPE_CHECKING:
    import polars as pl

    from ._dataframe import _read_parquet_cached  # noqa: F401 — referenced in docstrings

DEFAULT_CONNECT_TIMEOUT = 5.0
DEFAULT_READ_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 3


class FeatCatClient:
    """Sync HTTP client for the featcat catalog server.

    Construction:

        client = FeatCatClient(base_url="http://localhost:8000")
        client = FeatCatClient(base_url="...", actor="ds-pipeline-v2")

    The ``actor`` string is sent as a ``X-Featcat-Actor`` header on every
    request. The server treats it as opaque metadata; pass it for
    operational traceability rather than auth (the server has no auth).
    """

    def __init__(
        self,
        base_url: str,
        actor: str = "sdk-client",
        *,
        connect_timeout: float = DEFAULT_CONNECT_TIMEOUT,
        read_timeout: float = DEFAULT_READ_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.actor = actor
        self.max_retries = max_retries
        timeout = httpx.Timeout(read_timeout, connect=connect_timeout)
        headers = {
            "User-Agent": f"featcat-client/{__version__}",
            "X-Featcat-Actor": actor,
        }
        self._http = httpx.Client(
            base_url=self.base_url,
            timeout=timeout,
            headers=headers,
            transport=transport,
        )

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> FeatCatClient:
        return self

    def __exit__(self, *_exc: Any) -> None:
        self.close()

    # --- Internal: request + retry + error mapping ---

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any = None,
        not_found_exc: type[FeatCatError] | None = None,
        not_found_arg: str | None = None,
    ) -> Any:
        """Issue a request with retries on 5xx. Return decoded JSON on 2xx."""
        last_exc: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                resp = self._http.request(method, path, params=params, json=json_body)
            except httpx.HTTPError as exc:  # network/DNS/timeout — retry
                last_exc = exc
                if attempt < self.max_retries:
                    time.sleep(0.25 * (2**attempt))
                    continue
                raise ConnectionError(f"{method} {path}: {exc}") from exc
            if 200 <= resp.status_code < 300:
                if resp.status_code == 204 or not resp.content:
                    return None
                return resp.json()
            if resp.status_code == 404 and not_found_exc is not None:
                raise not_found_exc(not_found_arg or path)
            if 500 <= resp.status_code < 600 and attempt < self.max_retries:
                time.sleep(0.25 * (2**attempt))
                continue
            try:
                body = resp.json()
            except ValueError:
                body = resp.text
            raise ServerError(
                f"{method} {path} → HTTP {resp.status_code}",
                status_code=resp.status_code,
                body=body,
            )
        # Exhausted retries on a network error.
        raise ConnectionError(f"{method} {path}: retries exhausted ({last_exc})")

    # --- Sources ---

    def list_sources(self) -> list[DataSource]:
        rows = self._request("GET", "/api/sources")
        return [DataSource.model_validate(r) for r in rows]

    def get_source(self, name: str) -> DataSource:
        row = self._request(
            "GET",
            f"/api/sources/{name}",
            not_found_exc=FeatureNotFound,  # server returns 404 — surface generic
            not_found_arg=name,
        )
        return DataSource.model_validate(row)

    # --- Features ---

    def list_features(
        self,
        *,
        source: str | None = None,
        search: str | None = None,
        dtype: str | None = None,
        tag: str | None = None,
        owner: str | None = None,
        has_doc: bool | None = None,
        sort: str = "name",
        order: str = "asc",
    ) -> list[Feature]:
        """List features with optional filters.

        ``tag`` filters to features carrying that single tag. To filter by
        multiple tags, call once per tag and intersect on ``id``.
        """
        params: dict[str, Any] = {"sort": sort, "order": order}
        if source:
            params["source"] = source
        if search:
            params["search"] = search
        if dtype:
            params["dtype"] = dtype
        if tag:
            params["tag"] = tag
        if owner:
            params["owner"] = owner
        if has_doc is not None:
            params["has_doc"] = "true" if has_doc else "false"
        rows = self._request("GET", "/api/features", params=params)
        return [Feature.model_validate(r) for r in rows]

    def get_feature(self, name: str) -> Feature:
        """Get a single feature by ``source.column`` name."""
        row = self._request(
            "GET",
            "/api/features/by-name",
            params={"name": name},
            not_found_exc=FeatureNotFound,
            not_found_arg=name,
        )
        return Feature.model_validate(row)

    def get_path(self, name: str) -> str:
        """Return the parquet file path that contains this feature.

        Two round-trips: the feature endpoint gives us ``data_source_id``,
        the source endpoint gives us ``path``. Cached at the source level by
        the server's HTTP cache, not here.
        """
        feat = self.get_feature(name)
        source = self._get_source_by_id(feat.data_source_id)
        return source.path

    def _get_source_by_id(self, source_id: str) -> DataSource:
        # ``GET /api/sources`` returns all sources; the server has no
        # by-id endpoint. Linear scan — fine for the typical 10s-of-sources case.
        for src in self.list_sources():
            if src.id == source_id:
                return src
        msg = f"data_source_id {source_id!r} not found"
        raise ServerError(msg, status_code=404, body=None)

    def search(self, query: str, *, limit: int = 50) -> list[Feature]:
        """TF-IDF ranked search across feature name/description/tags/column.

        Maps to ``GET /api/features?search=...&sort=name`` — the server applies
        the ranking and returns features in score order.
        """
        rows = self._request(
            "GET",
            "/api/features",
            params={"search": query},
        )
        return [Feature.model_validate(r) for r in rows[:limit]]

    def find_similar(self, name: str, *, top_k: int = 10, threshold: float = 0.3) -> list[Feature]:
        """Return features most similar to ``name``.

        Calls the dedicated ``GET /api/features/by-name/similar`` endpoint
        added in T1.2b — server picks pgvector cosine when available, TF-IDF
        otherwise. Falls back to walking the legacy ``similarity-graph`` if
        the new endpoint isn't there (older servers).

        ``threshold`` is honored only on the legacy fallback path; the new
        endpoint already returns ranked top-K so threshold filtering happens
        client-side.
        """
        # Try the dedicated endpoint first. A 404 means EITHER the endpoint
        # isn't there (older server) OR the feature itself doesn't exist; in
        # both cases the graph-walk fallback returns sensible results (empty
        # for the missing-feature case, populated for the older-server case),
        # so a single ``except`` covers both without distinguishing.
        try:
            rows = self._request(
                "GET",
                "/api/features/by-name/similar",
                params={"name": name, "top_k": top_k},
            )
        except ServerError as exc:
            if exc.status_code != 404:
                raise
            rows = None
        if rows is not None:
            out: list[Feature] = []
            for r in rows:
                if r.get("similarity", 0) < threshold:
                    continue
                try:
                    out.append(self.get_feature(r["name"]))
                except FeatureNotFound:
                    continue
            return out

        graph = self._request(
            "GET",
            "/api/features/similarity-graph",
            params={"threshold": threshold},
        )
        edges = graph.get("edges", [])
        scored: list[tuple[str, float]] = []
        for e in edges:
            if e.get("source") == name:
                scored.append((e.get("target", ""), float(e.get("similarity", 0.0))))
            elif e.get("target") == name:
                scored.append((e.get("source", ""), float(e.get("similarity", 0.0))))
        scored.sort(key=lambda x: x[1], reverse=True)
        out = []
        for n, _score in scored[:top_k]:
            try:
                out.append(self.get_feature(n))
            except FeatureNotFound:
                continue
        return out

    def get_feature_usage(self, name: str) -> FeatureUsage:
        row = self._request("GET", "/api/usage/feature", params={"name": name})
        return FeatureUsage.model_validate(row)

    # --- Training datasets ---

    def build_training_dataset(
        self,
        *,
        entity_df_path: str,
        feature_columns: list[str],
        source_path: str | None = None,
        source_name: str | None = None,
        entity_key: str | None = None,
        entity_timestamp_column: str | None = None,
        source_event_timestamp_column: str | None = None,
        output_path: str | None = None,
    ) -> TrainingDatasetBuildResult:
        """Build a local point-in-time training dataset via the server.

        The server currently supports local parquet paths only. Pass either
        ``source_path`` for an explicit parquet file or ``source_name`` for a
        registered DataSource with join metadata.
        """
        body: dict[str, Any] = {
            "entity_df_path": entity_df_path,
            "feature_columns": feature_columns,
        }
        if source_path is not None:
            body["source_path"] = source_path
        if source_name is not None:
            body["source_name"] = source_name
        if entity_key is not None:
            body["entity_key"] = entity_key
        if entity_timestamp_column is not None:
            body["entity_timestamp_column"] = entity_timestamp_column
        if source_event_timestamp_column is not None:
            body["source_event_timestamp_column"] = source_event_timestamp_column
        if output_path is not None:
            body["output_path"] = output_path

        row = self._request("POST", "/api/datasets/build", json_body=body)
        return TrainingDatasetBuildResult.model_validate(row)

    def list_training_dataset_builds(
        self,
        *,
        limit: int = 20,
        status: str | None = None,
    ) -> list[TrainingDatasetBuildAudit]:
        """List recent training dataset build audit records."""
        params: dict[str, Any] = {"limit": limit}
        if status is not None:
            params["status"] = status
        rows = self._request("GET", "/api/datasets/builds", params=params)
        return [TrainingDatasetBuildAudit.model_validate(row) for row in rows]

    # --- Online store ---

    def write_online_features(
        self,
        rows: list[OnlineFeatureWrite | dict[str, Any]],
        *,
        project: str = "",
        feature_view: str = "",
        source_name: str | None = None,
        source_path: str | None = None,
    ) -> OnlineFeatureWriteResult:
        """Write latest online feature values.

        ``rows`` accepts either ``OnlineFeatureWrite`` instances or dictionaries
        matching the API row shape. Datetime strings and ``datetime`` objects are
        both accepted by the model layer.
        """
        body: dict[str, Any] = {
            "project": project,
            "feature_view": feature_view,
            "rows": [OnlineFeatureWrite.model_validate(row).model_dump(mode="json") for row in rows],
        }
        if source_name is not None:
            body["source_name"] = source_name
        if source_path is not None:
            body["source_path"] = source_path

        result = self._request("POST", "/api/online/write", json_body=body)
        return OnlineFeatureWriteResult.model_validate(result)

    def get_online_features(
        self,
        *,
        entity_keys: list[dict[str, Any]],
        feature_refs: list[str],
        project: str = "",
        feature_view: str = "",
    ) -> OnlineFeatureReadResult:
        """Read latest online feature values preserving request order."""
        body = {
            "project": project,
            "feature_view": feature_view,
            "entity_keys": entity_keys,
            "feature_refs": feature_refs,
        }
        result = self._request("POST", "/api/online/read", json_body=body)
        return OnlineFeatureReadResult.model_validate(result)

    # --- DataFrame helpers ---

    def read_feature(self, name: str) -> pl.DataFrame:
        """Read a single feature column from its source parquet as a polars DataFrame."""
        from ._dataframe import read_feature_parquet

        feat = self.get_feature(name)
        source = self._get_source_by_id(feat.data_source_id)
        return read_feature_parquet(feat, source)

    # --- Groups ---

    def list_groups(self, *, project: str | None = None) -> list[FeatureGroup]:
        params: dict[str, Any] = {}
        if project:
            params["project"] = project
        rows = self._request("GET", "/api/groups", params=params)
        return [FeatureGroup.model_validate(r) for r in rows]

    def get_group(self, name: str) -> FeatureGroupDetail:
        """Return a group plus all its member features.

        ``FeatureGroupDetail.to_polars()`` / ``to_pandas()`` join the member
        parquets on a common entity key. Pass ``entity_key=...`` to skip
        auto-detection (recommended in production).
        """
        body = self._request(
            "GET",
            f"/api/groups/{name}",
            not_found_exc=GroupNotFound,
            not_found_arg=name,
        )
        # Server response is the FeatureGroup with a members list directly on it.
        # Normalize to FeatureGroupDetail shape.
        members_raw = body.pop("members", [])
        group = FeatureGroup.model_validate(body)
        members = [Feature.model_validate(m) for m in members_raw]
        detail = FeatureGroupDetail(group=group, members=members)
        # Bind a source resolver so .to_polars() can read parquets.
        # Stored on the instance via the bind-method pattern.
        client_ref = self  # capture for the closure

        def _resolver(source_id: str) -> DataSource:
            return client_ref._get_source_by_id(source_id)

        # Patch the methods to default to this resolver.
        original_to_polars = detail.to_polars
        original_to_pandas = detail.to_pandas

        def _to_polars(*, entity_key: str | None = None, source_resolver: Any = None) -> Any:
            return original_to_polars(
                entity_key=entity_key,
                source_resolver=source_resolver or _resolver,
            )

        def _to_pandas(*, entity_key: str | None = None, source_resolver: Any = None) -> Any:
            return original_to_pandas(
                entity_key=entity_key,
                source_resolver=source_resolver or _resolver,
            )

        # Use object.__setattr__ since pydantic models don't allow arbitrary attr.
        object.__setattr__(detail, "to_polars", _to_polars)
        object.__setattr__(detail, "to_pandas", _to_pandas)
        return detail
