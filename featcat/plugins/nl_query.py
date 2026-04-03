"""Natural Language Query plugin: search the catalog using natural language."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

from ..utils.catalog_context import get_feature_summary
from ..utils.prompts import NL_QUERY_PROMPT, NL_QUERY_SYSTEM, NL_QUERY_SYSTEM_VI
from .base import BasePlugin, PluginResult

if TYPE_CHECKING:
    from ..catalog.backend import CatalogBackend
    from ..llm.base import BaseLLM


def _is_vietnamese(text: str) -> bool:
    """Simple heuristic: check for Vietnamese diacritics."""
    vietnamese_chars = re.compile(
        r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡ"
        r"ùúụủũưừứựửữỳýỵỷỹđ]",
        re.IGNORECASE,
    )
    return bool(vietnamese_chars.search(text))


def _fuzzy_search(db: CatalogBackend, query: str) -> list[dict]:
    """Fallback search using keyword matching when LLM is unavailable.

    Tries rapidfuzz if available, otherwise falls back to LIKE search.
    """
    try:
        from rapidfuzz import fuzz

        features = db.list_features()
        scored = []
        for f in features:
            searchable = f"{f.name} {f.description} {' '.join(f.tags)} {f.column_name}"
            score = fuzz.partial_ratio(query.lower(), searchable.lower())
            if score >= 40:
                scored.append(
                    {
                        "feature": f.name,
                        "score": round(score / 100, 2),
                        "reason": f"Fuzzy match (score: {score})",
                    }
                )
        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:20]
    except ImportError:
        # Fall back to SQL LIKE search
        results = db.search_features(query)
        return [{"feature": f.name, "score": 0.5, "reason": "Keyword match"} for f in results]


class NLQueryPlugin(BasePlugin):
    """Search the feature catalog using natural language queries."""

    @property
    def name(self) -> str:
        return "nl_query"

    @property
    def description(self) -> str:
        return "Search features using natural language"

    def execute(
        self,
        catalog_db: CatalogBackend,
        llm: BaseLLM,
        **kwargs: Any,
    ) -> PluginResult:
        """Execute a natural language query.

        Args:
            query: The natural language query (required kwarg).
            max_features: Max features in context (default 100).
            fallback_only: If True, skip LLM and use fuzzy match only.
        """
        query: str = kwargs.get("query", "")
        if not query:
            return PluginResult(status="error", errors=["query is required"])

        max_features = kwargs.get("max_features", 100)
        fallback_only = kwargs.get("fallback_only", False)

        # Try LLM first, fall back to fuzzy search
        if not fallback_only:
            try:
                return self._llm_query(catalog_db, llm, query, max_features)
            except Exception:
                pass  # Fall through to fuzzy search

        # Fallback: fuzzy/keyword search
        results = _fuzzy_search(catalog_db, query)
        return PluginResult(
            status="success",
            data={
                "results": results,
                "interpretation": f"Keyword search for: {query}",
                "follow_up": None,
                "method": "fuzzy_search",
            },
        )

    def _llm_query(
        self,
        db: CatalogBackend,
        llm: BaseLLM,
        query: str,
        max_features: int,
    ) -> PluginResult:
        """Run the query through the LLM."""
        feature_summary = get_feature_summary(db, max_features=max_features)
        is_vi = _is_vietnamese(query)
        system = NL_QUERY_SYSTEM_VI if is_vi else NL_QUERY_SYSTEM

        prompt = NL_QUERY_PROMPT.format(
            feature_summary=feature_summary,
            query=query,
        )

        result = llm.generate_json(prompt, system=system)

        # Ensure results are sorted by score
        results = result.get("results", [])
        results.sort(key=lambda x: x.get("score", 0), reverse=True)
        result["results"] = results
        result["method"] = "llm"

        return PluginResult(status="success", data=result)
