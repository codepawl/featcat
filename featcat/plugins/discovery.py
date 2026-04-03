"""Feature Discovery plugin: suggest relevant features for a use case."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..utils.catalog_context import get_all_sources_schema, get_feature_summary
from ..utils.prompts import DISCOVERY_PROMPT, DISCOVERY_SYSTEM
from .base import BasePlugin, PluginResult

if TYPE_CHECKING:
    from ..catalog.db import CatalogDB
    from ..llm.base import BaseLLM


class DiscoveryPlugin(BasePlugin):
    """Analyze the catalog and suggest features for a given use case."""

    @property
    def name(self) -> str:
        return "discovery"

    @property
    def description(self) -> str:
        return "Discover and suggest features for a use case"

    def execute(
        self,
        catalog_db: CatalogDB,
        llm: BaseLLM,
        **kwargs: Any,
    ) -> PluginResult:
        """Run feature discovery for a use case.

        Args:
            catalog_db: The catalog database.
            llm: The LLM backend.
            use_case: Description of the use case (required kwarg).
            max_features: Max features in context (default 100).
        """
        use_case: str = kwargs.get("use_case", "")
        if not use_case:
            return PluginResult(status="error", errors=["use_case is required"])

        max_features = kwargs.get("max_features", 100)

        feature_summary = get_feature_summary(catalog_db, max_features=max_features)
        source_schemas = get_all_sources_schema(catalog_db)

        prompt = DISCOVERY_PROMPT.format(
            use_case=use_case,
            feature_summary=feature_summary,
            source_schemas=source_schemas,
        )

        try:
            result = llm.generate_json(prompt, system=DISCOVERY_SYSTEM)
        except Exception as e:
            return PluginResult(status="error", errors=[str(e)])

        # Validate and sort existing features by relevance
        existing = result.get("existing_features", [])
        existing.sort(key=lambda x: x.get("relevance", 0), reverse=True)
        result["existing_features"] = existing

        return PluginResult(status="success", data=result)
