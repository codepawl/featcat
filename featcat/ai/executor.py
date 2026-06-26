"""Tool executor — runs tools against CatalogBackend."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from featcat.catalog.backend import CatalogBackend
    from featcat.llm.base import BaseLLM

logger = logging.getLogger(__name__)

MAX_RESULT_LENGTH = 1500
DEFAULT_LIST_LIMIT = 20
MAX_LIST_LIMIT = 50


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

    def _tool_list_features(
        self,
        source: str | None = None,
        has_doc: bool | None = None,
        dtype: str | None = None,
        name_contains: str | None = None,
        limit: int | None = None,
    ) -> str:
        capped = _cap_limit(limit)
        features = self.backend.list_features(
            source_name=source,
            dtype=dtype,
            search=name_contains,
            has_doc=has_doc,
            limit=capped,
        )
        if not features:
            return "No features match those filters."
        total = self.backend.count_features(source_name=source, dtype=dtype, search=name_contains, has_doc=has_doc)
        lines = [f"Showing {len(features)} of {total} matching features:"]
        for f in features:
            doc_marker = "" if has_doc is None else (" [doc]" if has_doc else " [no doc]")
            lines.append(f"- {f.name} ({f.dtype}){doc_marker}")
        if total > len(features):
            lines.append(f"... {total - len(features)} more not shown (raise limit or refine filters).")
        return "\n".join(lines)

    def _tool_count_features(
        self,
        source: str | None = None,
        has_doc: bool | None = None,
        dtype: str | None = None,
        name_contains: str | None = None,
    ) -> str:
        n = self.backend.count_features(source_name=source, dtype=dtype, search=name_contains, has_doc=has_doc)
        filters = _format_filter_summary(source=source, has_doc=has_doc, dtype=dtype, name_contains=name_contains)
        return f"{n} features{filters}."

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
        severity = self.backend.get_latest_severity(feature.id)
        if severity:
            lines.append(f"  Latest severity: {severity}")
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

    def _tool_catalog_summary(self) -> str:
        stats = self.backend.get_catalog_stats()
        groups = self.backend.list_groups()
        total = int(stats.get("total_features") or stats.get("features") or 0)
        documented = int(stats.get("documented") or 0)
        coverage = float(stats.get("coverage") or 0.0)
        lines = [
            f"Feature store: {total} features, {stats.get('sources', 0)} sources, {len(groups)} groups",
            f"Doc coverage: {documented}/{total} ({coverage}%)",
        ]
        sev_counts = self._severity_counts()
        if sev_counts:
            sev_str = ", ".join(f"{k}: {v}" for k, v in sev_counts.items() if v)
            if sev_str:
                lines.append(f"Drift status: {sev_str}")
        status_counts = self.backend.get_status_counts()
        status_keys = ("draft", "reviewed", "certified", "deprecated")
        if status_counts and any(status_counts.get(k, 0) for k in status_keys):
            status_str = ", ".join(f"{k}: {status_counts.get(k, 0)}" for k in status_keys)
            lines.append(f"Lifecycle: {status_str}")
        return "\n".join(lines)

    def _tool_features_by_source(self) -> str:
        rows = self.backend.get_stats_by_source()
        if not rows:
            return "No sources registered."
        rows_sorted = sorted(rows, key=lambda r: r.get("feature_count", 0), reverse=True)
        lines = ["Features per source (highest first):"]
        for r in rows_sorted[:20]:
            doc_n = r.get("documented_count", 0)
            total = r.get("feature_count", 0)
            drift = r.get("drift_alerts", 0)
            crit = r.get("critical_alerts", 0)
            extras = []
            if drift:
                extras.append(f"drift={drift}")
            if crit:
                extras.append(f"critical={crit}")
            extra = (" " + " ".join(extras)) if extras else ""
            lines.append(f"- {r['source_name']}: {total} features ({doc_n} documented){extra}")
        return "\n".join(lines)

    def _tool_list_groups(self) -> str:
        groups = self.backend.list_groups()
        if not groups:
            return "No feature groups defined yet."
        lines = []
        for g in groups:
            count = self.backend.count_group_members(g.id)
            owner = f" owner={g.owner}" if g.owner else ""
            desc = f" — {g.description}" if g.description else ""
            lines.append(f"- {g.name}: {count} features{owner}{desc}")
        return "\n".join(lines)

    def _tool_get_group(self, name: str) -> str:
        group = self.backend.get_group_by_name(name)
        if group is None:
            return f"Group '{name}' not found."
        members = self.backend.list_group_members(group.id)
        lines = [
            f"Group: {group.name}",
            f"  Description: {group.description or '(none)'}",
            f"  Owner: {group.owner or '(none)'}",
            f"  Members: {len(members)}",
        ]
        for m in members[:25]:
            lines.append(f"    - {m.name} ({m.dtype})")
        if len(members) > 25:
            lines.append(f"    ... {len(members) - 25} more.")
        return "\n".join(lines)

    def _tool_find_similar_features(self, feature_name: str, top_k: int | None = None) -> str:
        feature = self.backend.get_feature_by_name(feature_name)
        if feature is None:
            return f"Feature '{feature_name}' not found."
        k = max(1, min(int(top_k or 5), 20))
        similar = self.backend.find_similar_features(feature.id, top_k=k)
        if not similar:
            return f"No similar features found for {feature_name}."
        lines = [f"Top {len(similar)} similar to {feature_name}:"]
        for s in similar:
            sim = s.get("similarity", 0.0)
            lines.append(f"  - {s.get('name')} ({s.get('dtype')}): similarity={sim:.3f}")
        return "\n".join(lines)

    def _tool_find_duplicate_pairs(
        self,
        threshold: float | None = None,
        source: str | None = None,
        limit: int | None = None,
    ) -> str:
        thresh = float(threshold) if threshold is not None else 0.7
        thresh = max(0.4, min(0.95, thresh))
        lim = max(1, min(int(limit or 20), 50))
        sources = [source] if source else None
        pairs, total, _summary = self.backend.find_duplicate_pairs(threshold=thresh, limit=lim, sources=sources)
        if not pairs:
            scope = f" in source '{source}'" if source else ""
            return f"No duplicate pairs found{scope} above threshold {thresh:.2f}."
        header = f"Found {total} duplicate pair(s) above threshold {thresh:.2f}; showing top {len(pairs)}:"
        lines = [header]
        for p in pairs:
            a_name = p["a"]["name"] if isinstance(p.get("a"), dict) else getattr(p.get("a"), "name", "?")
            b_name = p["b"]["name"] if isinstance(p.get("b"), dict) else getattr(p.get("b"), "name", "?")
            score = p.get("score", 0.0)
            reasons = p.get("reasons", []) or []
            codes = ", ".join(r.get("code", "?") for r in reasons) if reasons else "unknown"
            lines.append(f"  - {a_name} ↔ {b_name}: {score:.3f} ({codes})")
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _severity_counts(self) -> dict[str, int]:
        """Latest-check severity counts across the catalog. N+1 by design — keeps the
        executor backend-agnostic (no new SQL helpers needed). Catalogs in the few-hundred-
        feature range complete in ms; if this becomes a hotspot, push down to the backend."""
        counts: dict[str, int] = {"healthy": 0, "warning": 0, "critical": 0}
        try:
            features = self.backend.list_features()
        except Exception:  # noqa: BLE001
            return counts
        for f in features:
            sev = self.backend.get_latest_severity(f.id)
            if sev in counts:
                counts[sev] += 1
        return counts


def _cap_limit(limit: int | None) -> int:
    if not limit or limit <= 0:
        return DEFAULT_LIST_LIMIT
    return min(int(limit), MAX_LIST_LIMIT)


def _format_filter_summary(
    *,
    source: str | None,
    has_doc: bool | None,
    dtype: str | None,
    name_contains: str | None,
) -> str:
    parts: list[str] = []
    if source:
        parts.append(f"in source '{source}'")
    if has_doc is True:
        parts.append("with docs")
    elif has_doc is False:
        parts.append("without docs")
    if dtype:
        parts.append(f"of dtype '{dtype}'")
    if name_contains:
        parts.append(f"matching '{name_contains}'")
    return (" " + ", ".join(parts)) if parts else ""
