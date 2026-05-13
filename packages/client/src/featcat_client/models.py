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
