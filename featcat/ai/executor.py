"""Tool executor — runs tools against CatalogBackend."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from featcat.catalog.backend import CatalogBackend
    from featcat.llm.base import BaseLLM

logger = logging.getLogger(__name__)

MAX_RESULT_LENGTH = 1500


class ToolExecutor:
    """Execute catalog tools and return string results for LLM context."""

    def __init__(self, backend: CatalogBackend, llm: BaseLLM | None = None) -> None:
        self.backend = backend
        self.llm = llm

    def execute(self, tool_name: str, params: dict[str, Any]) -> str:
        """Execute a tool by name. Returns a string result (or error)."""
        handler = getattr(self, f"_tool_{tool_name}", None)
        if handler is None:
            return f"Error: unknown tool '{tool_name}'"
        try:
            result = handler(**params)
            if len(result) > MAX_RESULT_LENGTH:
                result = result[:MAX_RESULT_LENGTH] + "\n... (truncated)"
            return result
        except Exception as e:
            logger.warning("Tool %s failed: %s", tool_name, e)
            return f"Error executing {tool_name}: {e}"

    # ------------------------------------------------------------------
    # Tool implementations
    # ------------------------------------------------------------------

    def _tool_search_features(self, query: str) -> str:
        features = self.backend.search_features(query)
        if not features:
            return "No features found matching the query."
        lines = []
        for f in features[:10]:
            tags = ", ".join(f.tags) if f.tags else ""
            desc = f.description or ""
            lines.append(f"- {f.name} ({f.dtype}) tags=[{tags}] {desc}")
        return "\n".join(lines)

    def _tool_get_feature_detail(self, feature_name: str) -> str:
        feature = self.backend.get_feature_by_name(feature_name)
        if feature is None:
            return f"Feature '{feature_name}' not found."
        lines = [
            f"Feature: {feature.name}",
            f"  Column: {feature.column_name}",
            f"  Dtype: {feature.dtype}",
            f"  Description: {feature.description or '(none)'}",
            f"  Owner: {feature.owner or '(none)'}",
            f"  Tags: {', '.join(feature.tags) if feature.tags else '(none)'}",
            f"  Source ID: {feature.data_source_id}",
        ]
        if feature.stats:
            lines.append("  Stats:")
            for k, v in feature.stats.items():
                lines.append(f"    {k}: {v}")
        doc = self.backend.get_feature_doc(feature.id)
        if doc:
            lines.append(f"  Doc: {doc.get('short_description', '')}")
        baseline = self.backend.get_baseline(feature.id)
        if baseline:
            lines.append("  Baseline: yes")
        return "\n".join(lines)

    def _tool_get_drift_report(self, feature_name: str = "") -> str:
        from featcat.plugins.monitoring import MonitoringPlugin

        plugin = MonitoringPlugin()
        kwargs: dict[str, Any] = {"action": "check"}
        if feature_name:
            kwargs["feature_name"] = feature_name
        result = plugin.execute(self.backend, None, **kwargs)
        if result.status == "error":
            return "Drift check failed: " + "; ".join(result.errors)
        data = result.data
        details = data.get("details", [])
        if not details:
            return "No drift data available. Run baseline first, then check."
        checked = data.get("checked", 0)
        healthy = data.get("healthy", 0)
        warnings = data.get("warnings", 0)
        critical = data.get("critical", 0)
        lines = [f"Checked {checked} features: {healthy} healthy, {warnings} warnings, {critical} critical"]
        for d in details[:10]:
            severity = d.get("severity", "?")
            issues = d.get("issues", [])
            issue_text = issues[0].get("message", "") if issues else ""
            lines.append(f"  {d['feature']}: {severity} — {issue_text}")
        return "\n".join(lines)

    def _tool_suggest_features(self, use_case: str) -> str:
        if self.llm is None:
            return "Feature suggestion requires LLM. LLM server is not available."
        from featcat.plugins.discovery import DiscoveryPlugin

        plugin = DiscoveryPlugin()
        result = plugin.execute(self.backend, self.llm, use_case=use_case)
        if result.status == "error":
            return "Discovery failed: " + "; ".join(result.errors)
        data = result.data
        lines = []
        existing = data.get("existing_features", [])
        if existing:
            lines.append("Existing features:")
            for f in existing[:5]:
                name = f.get("name", "?")
                reason = f.get("reason", "")
                lines.append(f"  - {name}: {reason}")
        suggested = data.get("new_feature_suggestions", data.get("suggested_features", []))
        if suggested:
            lines.append("Suggested new features:")
            for f in suggested[:5]:
                name = f.get("name", "?")
                reason = f.get("reason", "")
                lines.append(f"  - {name}: {reason}")
        summary = data.get("summary", data.get("strategy", ""))
        if summary:
            lines.append(f"Strategy: {summary}")
        return "\n".join(lines) if lines else "No suggestions generated."

    def _tool_compare_features(self, feature_names: str) -> str:
        names = [n.strip() for n in feature_names.split(",") if n.strip()]
        if len(names) < 2:
            return "Need at least 2 feature names separated by commas."
        lines = ["Feature Comparison:"]
        for name in names[:5]:
            feature = self.backend.get_feature_by_name(name)
            if feature is None:
                lines.append(f"\n{name}: NOT FOUND")
                continue
            lines.append(f"\n{name} ({feature.dtype}):")
            if feature.stats:
                for k, v in feature.stats.items():
                    val = f"{v:.4f}" if isinstance(v, float) else str(v)
                    lines.append(f"  {k}: {val}")
            else:
                lines.append("  (no stats)")
        return "\n".join(lines)

    def _tool_list_sources(self) -> str:
        sources = self.backend.list_sources()
        if not sources:
            return "No data sources registered."
        lines = []
        for s in sources:
            lines.append(f"- {s.name}: {s.path} ({s.storage_type}/{s.format})")
        return "\n".join(lines)
