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
- ``POST /api/sources``                   — add source
- ``PATCH /api/sources/{name}``           — update source metadata
- ``POST /api/sources/{name}/scan``       — scan source and register feature metadata
- ``GET  /api/groups``                    — list groups
- ``GET  /api/groups/{name}``             — group with members
- ``GET  /api/entities``                  — list entities
- ``GET  /api/entities/by-name?name=X``   — single entity
- ``POST /api/entities``                  — upsert entity
- ``GET  /api/entity-relationships``      — list relationships
- ``GET  /api/entity-relationships/by-name`` — single relationship
- ``POST /api/entity-relationships``      — upsert relationship
- ``GET  /api/feature-views``             — list feature views
- ``GET  /api/feature-views/by-name``     — single feature view
- ``POST /api/feature-views``             — upsert feature view
- ``GET  /api/feature-sets``              — list feature sets
- ``GET  /api/feature-sets/by-name``      — single feature set
- ``POST /api/feature-sets``              — upsert feature set
- ``GET  /api/business-metrics``           — list business metrics
- ``GET  /api/business-metrics/by-name``   — single business metric
- ``POST /api/business-metrics``           — upsert business metric
- ``POST /api/scan-bulk``                 — bulk source scan + register
- ``POST /api/datasets/build``            — build local PIT training dataset
- ``GET  /api/datasets/builds``           — list recent dataset build audits
- ``POST /api/online/write``              — write online feature values
- ``POST /api/online/read``               — read online feature values
- ``POST /api/online/materialize``        — materialize latest offline values
- ``GET  /api/online/materializations``   — list materialization audit history
- ``GET  /api/online/materialization-schedules`` — list materialization schedules
- ``POST /api/online/materialization-schedules`` — create materialization schedule
- ``PATCH /api/online/materialization-schedules/{id}`` — enable/disable schedule
- ``POST /api/online/materialization-schedules/{id}/run`` — run schedule once
- ``GET  /api/usage/feature?name=X``      — usage stats for a feature

The server *auto-logs* a ``view`` action on every ``GET /api/features/by-name``
call, so the SDK doesn't need a separate ``log_usage`` round-trip — the
``actor`` parameter is passed as a custom header for traceability.
"""

from __future__ import annotations

import time
from fnmatch import fnmatch
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from . import __version__
from .exceptions import (
    BusinessMetricNotFound,
    ConnectionError,
    EntityNotFound,
    EntityRelationshipNotFound,
    FeatCatError,
    FeatureNotFound,
    FeatureSetNotFound,
    FeatureViewNotFound,
    GroupNotFound,
    ServerError,
    SourceNotFound,
)
from .models import (
    BulkScanRequest,
    BulkScanResult,
    BusinessMetric,
    BusinessMetricCreateRequest,
    DataSource,
    DataSourceCreateRequest,
    DataSourceUpdateRequest,
    Entity,
    EntityCreateRequest,
    EntityRelationship,
    EntityRelationshipCreateRequest,
    Feature,
    FeatureGroup,
    FeatureGroupDetail,
    FeatureSet,
    FeatureSetCreateRequest,
    FeatureUsage,
    FeatureView,
    FeatureViewCreateRequest,
    FlowResult,
    MaterializationAudit,
    MaterializationResult,
    MaterializationSchedule,
    MaterializationScheduleCreateRequest,
    MaterializationScheduleRunResult,
    MaterializationScheduleUpdateRequest,
    OnlineFeatureReadResult,
    OnlineFeatureWrite,
    OnlineFeatureWriteResult,
    SourceScanResult,
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

    @staticmethod
    def _coerce_payload(model: type[Any], payload: Any) -> dict[str, Any]:
        """Convert a model-like payload into JSON-serializable dict form."""
        if hasattr(payload, "model_dump"):
            return payload.model_dump(mode="json")  # type: ignore[no-any-return]
        return model.model_validate(payload).model_dump(mode="json")  # type: ignore[no-any-return]

    @staticmethod
    def _source_name_from_path(path: str, explicit_name: str | None = None) -> str:
        return explicit_name.strip() if explicit_name and explicit_name.strip() else Path(path).stem

    @staticmethod
    def _parse_feature_view_specs(
        specs: list[str],
        source_name: str,
        columns: list[str],
    ) -> list[tuple[str, list[str]]]:
        """Parse ``name[:glob]`` specs into ``(name, feature_names)`` tuples.

        Mirrors ``featcat.cli._parse_feature_view_specs`` so SDK and CLI
        behavior stay aligned. ``columns`` are raw column names without the
        source prefix.
        """
        if not specs:
            # Backward-compatible shorthand: one view over all scanned features.
            return [(f"{source_name}_all", [f"{source_name}.{c}" for c in columns])]

        parsed: list[tuple[str, list[str]]] = []
        seen_names: set[str] = set()
        for raw in specs:
            raw = raw.strip()
            if not raw:
                continue

            if ":" in raw:
                view_name, pattern = [part.strip() for part in raw.split(":", 1)]
                pattern = pattern or "*"
            else:
                view_name, pattern = raw, "*"

            if not view_name:
                raise ValueError("feature-view names cannot be empty")
            if view_name in seen_names:
                raise ValueError(f"duplicate feature-view name: {view_name}")
            matched = [col for col in columns if fnmatch(col, pattern)]
            if not matched:
                raise ValueError(f"no columns matched feature-view pattern '{raw}'")

            seen: set[str] = set()
            feature_names = []
            for feature_name in [f"{source_name}.{c}" for c in matched]:
                if feature_name in seen:
                    continue
                seen.add(feature_name)
                feature_names.append(feature_name)

            parsed.append((view_name, feature_names))
            seen_names.add(view_name)

        return parsed

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
            not_found_exc=SourceNotFound,  # server returns 404 — surface typed SDK error
            not_found_arg=name,
        )
        return DataSource.model_validate(row)

    def upsert_source(self, source: DataSource | DataSourceCreateRequest | dict[str, Any]) -> DataSource:
        body = self._coerce_payload(DataSourceCreateRequest, source)
        row = self._request("POST", "/api/sources", json_body=body)
        return DataSource.model_validate(row)

    def update_source(
        self,
        name: str,
        *,
        description: str | None = None,
        format: str | None = None,
        entity_key: str | None = None,
        event_timestamp_column: str | None = None,
        created_timestamp_column: str | None = None,
    ) -> DataSource:
        body = DataSourceUpdateRequest(
            description=description,
            format=format,
            entity_key=entity_key,
            event_timestamp_column=event_timestamp_column,
            created_timestamp_column=created_timestamp_column,
        )
        row = self._request(
            "PATCH",
            f"/api/sources/{name}",
            json_body=body.model_dump(mode="json"),
        )
        return DataSource.model_validate(row)

    def scan_source(self, name: str) -> SourceScanResult:
        row = self._request("POST", f"/api/sources/{name}/scan")
        return SourceScanResult.model_validate(row)

    def scan_bulk(
        self,
        *,
        path: str,
        recursive: bool = False,
        formats: list[str] | None = None,
        owner: str = "",
        tags: list[str] | None = None,
        dry_run: bool = False,
    ) -> BulkScanResult:
        request = BulkScanRequest(
            path=path,
            recursive=recursive,
            formats=formats or ["parquet", "csv"],
            owner=owner,
            tags=tags or [],
            dry_run=dry_run,
        )
        row = self._request("POST", "/api/scan-bulk", json_body=request.model_dump(mode="json"))
        return BulkScanResult.model_validate(row)

    # --- Entities ---

    def list_entities(self) -> list[Entity]:
        rows = self._request("GET", "/api/entities")
        return [Entity.model_validate(r) for r in rows]

    def get_entity(self, name: str) -> Entity:
        row = self._request(
            "GET",
            "/api/entities/by-name",
            params={"name": name},
            not_found_exc=EntityNotFound,
            not_found_arg=name,
        )
        return Entity.model_validate(row)

    def get_entity_by_name(self, name: str) -> Entity:
        return self.get_entity(name)

    def upsert_entity(self, entity: Entity | EntityCreateRequest | dict[str, Any]) -> Entity:
        row = self._request("POST", "/api/entities", json_body=self._coerce_payload(EntityCreateRequest, entity))
        return Entity.model_validate(row)

    # --- Entity relationships ---

    def list_entity_relationships(
        self,
        *,
        left_entity: str | None = None,
        right_entity: str | None = None,
        relation_type: str | None = None,
    ) -> list[EntityRelationship]:
        params: dict[str, Any] = {}
        if left_entity is not None:
            params["left_entity"] = left_entity
        if right_entity is not None:
            params["right_entity"] = right_entity
        if relation_type is not None:
            params["relation_type"] = relation_type
        rows = self._request("GET", "/api/entity-relationships", params=params)
        return [EntityRelationship.model_validate(r) for r in rows]

    def get_entity_relationship(self, name: str) -> EntityRelationship:
        row = self._request(
            "GET",
            "/api/entity-relationships/by-name",
            params={"name": name},
            not_found_exc=EntityRelationshipNotFound,
            not_found_arg=name,
        )
        return EntityRelationship.model_validate(row)

    def get_entity_relationship_by_name(self, name: str) -> EntityRelationship:
        return self.get_entity_relationship(name)

    def upsert_entity_relationship(
        self,
        relationship: EntityRelationship | EntityRelationshipCreateRequest | dict[str, Any],
    ) -> EntityRelationship:
        row = self._request(
            "POST",
            "/api/entity-relationships",
            json_body=self._coerce_payload(EntityRelationshipCreateRequest, relationship),
        )
        return EntityRelationship.model_validate(row)

    # --- Feature views ---

    def list_feature_views(self, *, entity: str | None = None, owner: str | None = None) -> list[FeatureView]:
        params: dict[str, Any] = {}
        if entity is not None:
            params["entity"] = entity
        if owner is not None:
            params["owner"] = owner
        rows = self._request("GET", "/api/feature-views", params=params)
        return [FeatureView.model_validate(r) for r in rows]

    def get_feature_view(self, name: str) -> FeatureView:
        row = self._request(
            "GET",
            "/api/feature-views/by-name",
            params={"name": name},
            not_found_exc=FeatureViewNotFound,
            not_found_arg=name,
        )
        return FeatureView.model_validate(row)

    def get_feature_view_by_name(self, name: str) -> FeatureView:
        return self.get_feature_view(name)

    def upsert_feature_view(self, feature_view: FeatureView | FeatureViewCreateRequest | dict[str, Any]) -> FeatureView:
        row = self._request(
            "POST",
            "/api/feature-views",
            json_body=self._coerce_payload(FeatureViewCreateRequest, feature_view),
        )
        return FeatureView.model_validate(row)

    # --- Feature sets ---

    def list_feature_sets(
        self,
        *,
        target_entity: str | None = None,
        owner: str | None = None,
    ) -> list[FeatureSet]:
        params: dict[str, Any] = {}
        if target_entity is not None:
            params["target_entity"] = target_entity
        if owner is not None:
            params["owner"] = owner
        rows = self._request("GET", "/api/feature-sets", params=params)
        return [FeatureSet.model_validate(r) for r in rows]

    def get_feature_set(self, name: str) -> FeatureSet:
        row = self._request(
            "GET",
            "/api/feature-sets/by-name",
            params={"name": name},
            not_found_exc=FeatureSetNotFound,
            not_found_arg=name,
        )
        return FeatureSet.model_validate(row)

    def get_feature_set_by_name(self, name: str) -> FeatureSet:
        return self.get_feature_set(name)

    def upsert_feature_set(self, feature_set: FeatureSet | FeatureSetCreateRequest | dict[str, Any]) -> FeatureSet:
        row = self._request(
            "POST",
            "/api/feature-sets",
            json_body=self._coerce_payload(FeatureSetCreateRequest, feature_set),
        )
        return FeatureSet.model_validate(row)

    # --- Business metrics ---

    def list_business_metrics(
        self,
        *,
        metric_domain: str | None = None,
        lifecycle_stage: str | None = None,
        metric_level: str | None = None,
        business_objective: str | None = None,
        owner: str | None = None,
        search: str | None = None,
    ) -> list[BusinessMetric]:
        params: dict[str, Any] = {}
        if metric_domain is not None:
            params["metric_domain"] = metric_domain
        if lifecycle_stage is not None:
            params["lifecycle_stage"] = lifecycle_stage
        if metric_level is not None:
            params["metric_level"] = metric_level
        if business_objective is not None:
            params["business_objective"] = business_objective
        if owner is not None:
            params["owner"] = owner
        if search is not None:
            params["search"] = search
        rows = self._request("GET", "/api/business-metrics", params=params)
        return [BusinessMetric.model_validate(r) for r in rows]

    def get_business_metric(self, name: str) -> BusinessMetric:
        row = self._request(
            "GET",
            "/api/business-metrics/by-name",
            params={"name": name},
            not_found_exc=BusinessMetricNotFound,
            not_found_arg=name,
        )
        return BusinessMetric.model_validate(row)

    def get_business_metric_by_name(self, name: str) -> BusinessMetric:
        return self.get_business_metric(name)

    def upsert_business_metric(
        self,
        metric: BusinessMetric | BusinessMetricCreateRequest | dict[str, Any],
    ) -> BusinessMetric:
        row = self._request(
            "POST",
            "/api/business-metrics",
            json_body=self._coerce_payload(BusinessMetricCreateRequest, metric),
        )
        return BusinessMetric.model_validate(row)

    def flow(
        self,
        *,
        path: str,
        entity: str,
        entity_primary_key: list[str],
        source_name: str | None = None,
        entity_join_key: list[str] | None = None,
        feature_view: list[str] | None = None,
        feature_set: str | None = None,
        feature_set_views: list[str] | None = None,
        relationship: str | None = None,
        format: str | None = None,
        description: str | None = None,
        source_entity_key: str | None = None,
        source_event_timestamp_column: str | None = None,
        source_created_timestamp_column: str | None = None,
    ) -> FlowResult:
        """One-command onboarding flow: source → feature registration → feature views → feature set."""
        if not entity:
            raise ValueError("entity is required")
        if not entity_primary_key:
            raise ValueError("entity_primary_key is required and cannot be empty")
        normalized_source_name = self._source_name_from_path(path, source_name)
        storage_type = "s3" if path.startswith("s3://") else "local"
        normalized_feature_views = feature_view or []
        normalized_entity_join_key = entity_join_key or []
        normalized_feature_set_views = feature_set_views or []
        source_format = format or "parquet"

        try:
            source = self.get_source(normalized_source_name)
        except SourceNotFound:
            source = self.upsert_source(
                DataSourceCreateRequest(
                    name=normalized_source_name,
                    path=path,
                    storage_type=storage_type,
                    format=source_format,
                    description=description or "",
                    entity_key=source_entity_key,
                    event_timestamp_column=source_event_timestamp_column,
                    created_timestamp_column=source_created_timestamp_column,
                )
            )
        else:
            if source.path != path or source.storage_type != storage_type:
                raise ValueError(
                    "Source exists with different path or storage type; "
                    f"name={normalized_source_name!r}, existing={source.path!r}, new={path!r}"
                )
            source = self.update_source(
                normalized_source_name,
                description=description,
                format=format,
                entity_key=source_entity_key,
                event_timestamp_column=source_event_timestamp_column,
                created_timestamp_column=source_created_timestamp_column,
            )

        scan_result = self.scan_source(normalized_source_name)

        source_features = self.list_features(source=normalized_source_name, sort="name", order="asc")
        if not source_features:
            raise ServerError(f"No features discovered for source {normalized_source_name}", status_code=422, body=None)
        feature_columns = []
        for item in source_features:
            if item.name.startswith(f"{normalized_source_name}."):
                feature_columns.append(item.name.split(".", 1)[1])

        if not feature_columns:
            raise ServerError(
                f"Feature scan did not return usable columns for source {normalized_source_name}",
                status_code=422,
                body=None,
            )

        parsed_views = self._parse_feature_view_specs(
            normalized_feature_views,
            normalized_source_name,
            feature_columns,
        )
        created_feature_views: list[FeatureView] = []
        created_feature_view_names: list[str] = []
        feature_view_features: dict[str, list[str]] = {}
        for view_name, feature_names in parsed_views:
            feature_view_obj = self.upsert_feature_view(
                FeatureViewCreateRequest(
                    name=view_name,
                    entity=entity,
                    source_name=normalized_source_name,
                    source_entity=entity,
                    relationship=relationship,
                    feature_names=feature_names,
                )
            )
            created_feature_views.append(feature_view_obj)
            created_feature_view_names.append(feature_view_obj.name)
            feature_view_features[feature_view_obj.name] = feature_names

        selected_view_names = normalized_feature_set_views or created_feature_view_names
        missing_views = [name for name in selected_view_names if name not in feature_view_features]
        if missing_views:
            raise ValueError(f"Unknown feature view names: {', '.join(sorted(missing_views))}")

        selected_feature_names: list[str] = []
        seen: set[str] = set()
        for view_name in selected_view_names:
            for feature_name in feature_view_features[view_name]:
                if feature_name not in seen:
                    selected_feature_names.append(feature_name)
                    seen.add(feature_name)

        if not selected_feature_names:
            raise ValueError("No features selected for feature set")

        feature_set_obj = self.upsert_feature_set(
            FeatureSetCreateRequest(
                name=feature_set or f"{normalized_source_name}_set",
                target_entity=entity,
                feature_names=selected_feature_names,
            )
        )

        entity_obj = self.upsert_entity(
            EntityCreateRequest(
                name=entity,
                primary_keys=entity_primary_key,
                join_keys=normalized_entity_join_key,
            )
        )

        return FlowResult(
            source=source,
            entity=entity_obj,
            feature_views=created_feature_views,
            feature_set=feature_set_obj,
            source_feature_count=len(source_features),
            scan_result=scan_result,
        )

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

    def materialize_online_features(
        self,
        *,
        source_name: str,
        feature_columns: list[str],
        project: str = "",
        feature_view: str = "",
        actor: str | None = None,
    ) -> MaterializationResult:
        """Materialize latest offline values from a registered source into the online store."""
        body: dict[str, Any] = {
            "source_name": source_name,
            "feature_columns": feature_columns,
            "project": project,
            "feature_view": feature_view,
        }
        if actor is not None:
            body["actor"] = actor
        result = self._request("POST", "/api/online/materialize", json_body=body)
        return MaterializationResult.model_validate(result)

    def list_materialization_runs(
        self,
        *,
        limit: int = 20,
        status: str | None = None,
    ) -> list[MaterializationAudit]:
        """List recent online materialization audit records."""
        params: dict[str, Any] = {"limit": limit}
        if status is not None:
            params["status"] = status
        rows = self._request("GET", "/api/online/materializations", params=params)
        return [MaterializationAudit.model_validate(row) for row in rows]

    def list_materialization_schedules(
        self,
        *,
        limit: int = 20,
        enabled: bool | None = None,
    ) -> list[MaterializationSchedule]:
        """List interval materialization schedules."""
        params: dict[str, Any] = {"limit": limit}
        if enabled is not None:
            params["enabled"] = "true" if enabled else "false"
        rows = self._request("GET", "/api/online/materialization-schedules", params=params)
        return [MaterializationSchedule.model_validate(row) for row in rows]

    def create_materialization_schedule(
        self,
        *,
        name: str,
        source_name: str,
        feature_columns: list[str],
        interval_seconds: int,
        project: str = "",
        feature_view: str = "",
        enabled: bool = True,
        actor: str | None = None,
    ) -> MaterializationSchedule:
        """Create an interval materialization schedule."""
        body = MaterializationScheduleCreateRequest(
            name=name,
            source_name=source_name,
            feature_columns=feature_columns,
            interval_seconds=interval_seconds,
            project=project,
            feature_view=feature_view,
            enabled=enabled,
            actor=actor,
        ).model_dump(mode="json")
        row = self._request("POST", "/api/online/materialization-schedules", json_body=body)
        return MaterializationSchedule.model_validate(row)

    def set_materialization_schedule_enabled(
        self,
        schedule_id: str,
        enabled: bool,
    ) -> MaterializationSchedule:
        """Enable or disable an interval materialization schedule."""
        body = MaterializationScheduleUpdateRequest(enabled=enabled).model_dump(mode="json")
        row = self._request("PATCH", f"/api/online/materialization-schedules/{schedule_id}", json_body=body)
        return MaterializationSchedule.model_validate(row)

    def run_materialization_schedule(
        self,
        schedule_id: str,
        *,
        runner_id: str | None = None,
    ) -> MaterializationScheduleRunResult:
        """Run one materialization schedule immediately."""
        body = {"runner_id": runner_id} if runner_id is not None else None
        row = self._request("POST", f"/api/online/materialization-schedules/{schedule_id}/run", json_body=body)
        return MaterializationScheduleRunResult.model_validate(row)

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
