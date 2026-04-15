"""Auto Documentation plugin: generate and manage feature documentation."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from ..utils.lang import localize_system_prompt
from ..utils.prompts import AUTODOC_PROMPT_SINGLE, AUTODOC_SYSTEM
from .base import BasePlugin, PluginResult

if TYPE_CHECKING:
    from ..catalog.backend import CatalogBackend
    from ..catalog.models import Feature
    from ..llm.base import BaseLLM

logger = logging.getLogger(__name__)


class AutodocPlugin(BasePlugin):
    """Generate AI-powered documentation for features."""

    @property
    def name(self) -> str:
        return "autodoc"

    @property
    def description(self) -> str:
        return "Auto-generate documentation for catalog features"

    def execute(
        self,
        catalog_db: CatalogBackend,
        llm: BaseLLM,
        **kwargs: Any,
    ) -> PluginResult:
        feature_name: str | None = kwargs.get("feature_name")
        progress_callback = kwargs.get("progress_callback")
        language: str = kwargs.get("language", "en")
        regenerate_all: bool = kwargs.get("regenerate_all", False)
        system = localize_system_prompt(AUTODOC_SYSTEM, language)

        if feature_name:
            return self._document_single(catalog_db, llm, feature_name, system)
        else:
            return self._document_all(catalog_db, llm, progress_callback, system, regenerate_all)

    def _document_single(
        self,
        db: CatalogBackend,
        llm: BaseLLM,
        feature_name: str,
        system: str = AUTODOC_SYSTEM,
    ) -> PluginResult:
        feature = db.get_feature_by_name(feature_name)
        if feature is None:
            return PluginResult(status="error", errors=[f"Feature not found: {feature_name}"])

        doc = self._generate_one(db, llm, feature, system)
        if doc is None:
            return PluginResult(status="error", errors=[f"Failed to generate doc for: {feature_name}"])

        return PluginResult(status="success", data={"documented": 1, "features": {feature.name: doc}})

    def _document_all(
        self,
        db: CatalogBackend,
        llm: BaseLLM,
        progress_callback: Any,
        system: str = AUTODOC_SYSTEM,
        regenerate_all: bool = False,
    ) -> PluginResult:
        if regenerate_all:
            to_process = db.list_features()
            logger.info("Regenerate all: processing %d features", len(to_process))
        else:
            to_process = db.list_undocumented_features()
            logger.info("Found %d undocumented features", len(to_process))

        if not to_process:
            return PluginResult(status="success", data={"documented": 0, "message": "All features are documented"})

        total = len(to_process)
        documented = 0
        all_docs: dict[str, dict] = {}
        errors: list[str] = []

        for i, feature in enumerate(to_process):
            try:
                doc = self._generate_one(db, llm, feature, system)
                if doc:
                    all_docs[feature.name] = doc
                    documented += 1
                    logger.info("Generated doc for %s (%d/%d)", feature.name, documented, total)
                else:
                    logger.warning("No doc generated for %s — LLM returned empty/invalid", feature.name)
            except Exception as e:
                logger.error("Failed to generate doc for %s: %s", feature.name, e)
                errors.append(f"{feature.name}: {e}")

            if progress_callback:
                progress_callback(i + 1, total)

        status = "success" if not errors else "partial"
        return PluginResult(
            status=status,
            data={"documented": documented, "total": total, "features": all_docs},
            errors=errors,
        )

    def _generate_one(
        self,
        db: CatalogBackend,
        llm: BaseLLM,
        feature: Feature,
        system: str,
    ) -> dict | None:
        """Generate documentation for a single feature. Returns doc dict or None."""
        from ..catalog.context_builder import build_doc_context

        source = db.get_source_by_name(feature.name.split(".")[0]) if "." in feature.name else None
        source_name = source.name if source else "unknown"
        source_path = source.path if source else "unknown"

        # Build rich context using TF-IDF similarity
        context_features = build_doc_context(feature.id, db, max_context_features=8)

        # Build stats text
        stats_keys = ("mean", "std", "null_ratio", "min", "max")
        stats_parts = [f"{k}={feature.stats[k]}" for k in stats_keys if k in feature.stats]
        stats_text = ", ".join(stats_parts) if stats_parts else "(no stats)"

        # Build hints section
        hint = feature.generation_hints
        hints_section = ""
        if hint:
            hints_section = f'Hint from data owner: "{hint}" ← treat as ground truth'

        # Build same-source context section
        same_source = [c for c in context_features if c.source != "cross_source"]
        same_lines = []
        for c in same_source:
            parts = [f"{c.spec}: {c.dtype}"]
            if c.stats_summary.get("mean") is not None:
                parts.append(f"mean={c.stats_summary['mean']}")
            if c.stats_summary.get("null_ratio") is not None:
                parts.append(f"null={c.stats_summary['null_ratio']}%")
            if c.generation_hints:
                parts.append(f'hint: "{c.generation_hints}"')
            same_lines.append("  " + ", ".join(parts))

        same_source_section = ""
        if same_lines:
            same_source_section = (
                "RELATED FEATURES IN SAME SOURCE:\n" + "\n".join(same_lines)
            )

        # Build cross-source context section
        cross_source = [c for c in context_features if c.source == "cross_source"]
        cross_lines = []
        for c in cross_source:
            src = c.spec.split(".")[0] if "." in c.spec else "?"
            parts = [f"{c.spec} (from {src}): {c.dtype}"]
            if c.stats_summary.get("mean") is not None:
                parts.append(f"mean={c.stats_summary['mean']}")
            cross_lines.append("  " + ", ".join(parts))

        cross_source_section = ""
        if cross_lines:
            cross_source_section = (
                "CROSS-SOURCE RELATED FEATURES:\n" + "\n".join(cross_lines)
            )

        prompt = AUTODOC_PROMPT_SINGLE.format(
            feature_name=feature.name,
            column_name=feature.column_name,
            dtype=feature.dtype,
            source_name=source_name,
            source_path=source_path,
            tags=", ".join(feature.tags) if feature.tags else "(none)",
            stats_text=stats_text,
            hints_section=hints_section,
            same_source_section=same_source_section,
            cross_source_section=cross_source_section,
        )

        model_name = getattr(llm, "model", "unknown")

        try:
            doc = llm.generate_json(prompt, system=system)
            logger.debug("LLM response for %s: %s", feature.name, str(doc)[:500])
        except Exception:
            logger.debug("Retry for %s with higher temperature", feature.name)
            try:
                doc = llm.generate_json(prompt, system=system, temperature=0.3)
                logger.debug("LLM retry response for %s: %s", feature.name, str(doc)[:500])
            except Exception as e:
                logger.error("Retry also failed for %s: %s", feature.name, e)
                return None

        # Small models sometimes wrap JSON in an array
        if isinstance(doc, list):
            doc = doc[0] if doc and isinstance(doc[0], dict) else {}

        if not doc.get("short_description"):
            logger.warning("LLM returned empty short_description for %s, skipping save", feature.name)
            return None

        context_specs = [c.spec for c in context_features]
        db.save_feature_doc(
            feature.id,
            doc,
            model_used=model_name,
            hints_used=hint,
            context_features=context_specs or None,
        )
        return doc


def get_doc(db, feature_name: str) -> dict | None:
    """Retrieve documentation for a feature."""
    feature = db.get_feature_by_name(feature_name)
    if feature is None:
        return None
    return db.get_feature_doc(feature.id)


def get_doc_stats(db) -> dict:
    """Get documentation coverage statistics."""
    return db.get_doc_stats()


def export_docs_markdown(db) -> str:
    """Export all feature documentation to Markdown."""
    features = db.list_features()
    all_docs = db.get_all_feature_docs()
    lines = ["# Feature Documentation", "", "*Generated from featcat catalog*", ""]

    by_source: dict[str, list] = {}
    for f in features:
        src = f.name.split(".")[0] if "." in f.name else "unknown"
        by_source.setdefault(src, []).append(f)

    for source_name, feats in sorted(by_source.items()):
        lines.append(f"## {source_name}")
        lines.append("")

        for f in feats:
            doc = all_docs.get(f.id)

            lines.append(f"### {f.name}")
            lines.append("")
            lines.append(f"- **Column:** `{f.column_name}`")
            lines.append(f"- **Type:** `{f.dtype}`")
            lines.append(f"- **Tags:** {', '.join(f.tags) if f.tags else '(none)'}")

            if f.stats:
                lines.append(
                    f"- **Stats:** mean={f.stats.get('mean', '?')}, "
                    f"std={f.stats.get('std', '?')}, "
                    f"null_ratio={f.stats.get('null_ratio', '?')}"
                )

            if doc:
                lines.append(f"\n> {doc.get('short_description', '')}")
                if doc.get("long_description"):
                    lines.append(f"\n{doc['long_description']}")
                if doc.get("expected_range"):
                    lines.append(f"\n**Expected range:** {doc['expected_range']}")
                if doc.get("potential_issues"):
                    lines.append(f"\n**Potential issues:** {doc['potential_issues']}")
            else:
                lines.append("\n*No documentation generated yet.*")

            lines.append("")

    return "\n".join(lines)
