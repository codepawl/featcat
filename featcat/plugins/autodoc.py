"""Auto Documentation plugin: generate and manage feature documentation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from ..utils.lang import localize_system_prompt
from ..utils.prompts import AUTODOC_PROMPT_BATCH, AUTODOC_PROMPT_SINGLE, AUTODOC_SYSTEM
from .base import BasePlugin, PluginResult

if TYPE_CHECKING:
    from ..catalog.backend import CatalogBackend
    from ..catalog.models import Feature
    from ..llm.base import BaseLLM


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
        batch_size: int = kwargs.get("batch_size", 10)
        progress_callback = kwargs.get("progress_callback")
        language: str = kwargs.get("language", "en")
        system = localize_system_prompt(AUTODOC_SYSTEM, language)

        if feature_name:
            return self._document_single(catalog_db, llm, feature_name, system)
        else:
            return self._document_all(catalog_db, llm, batch_size, progress_callback, system)

    def _document_single(
        self, db: CatalogBackend, llm: BaseLLM, feature_name: str, system: str = AUTODOC_SYSTEM,
    ) -> PluginResult:
        feature = db.get_feature_by_name(feature_name)
        if feature is None:
            return PluginResult(status="error", errors=[f"Feature not found: {feature_name}"])

        source = db.get_source_by_name(feature.name.split(".")[0]) if "." in feature.name else None
        source_name = source.name if source else "unknown"
        source_path = source.path if source else "unknown"

        siblings = db.list_features(source_name=source_name) if source else []
        sibling_names = ", ".join(f.column_name for f in siblings if f.name != feature.name)

        stats_text = "\n".join(f"  {k}: {v}" for k, v in feature.stats.items()) if feature.stats else "  (no stats)"

        prompt = AUTODOC_PROMPT_SINGLE.format(
            feature_name=feature.name,
            column_name=feature.column_name,
            dtype=feature.dtype,
            source_name=source_name,
            source_path=source_path,
            tags=", ".join(feature.tags) if feature.tags else "(none)",
            stats_text=stats_text,
            sibling_columns=sibling_names or "(none)",
        )

        try:
            doc = llm.generate_json(prompt, system=system)
        except Exception as e:
            return PluginResult(status="error", errors=[str(e)])

        model_name = getattr(llm, "model", "unknown")
        db.save_feature_doc(feature.id, doc, model_used=model_name)

        return PluginResult(status="success", data={"documented": 1, "features": {feature.name: doc}})

    def _document_all(
        self, db: CatalogBackend, llm: BaseLLM, batch_size: int, progress_callback: Any,
        system: str = AUTODOC_SYSTEM,
    ) -> PluginResult:
        undocumented = db.list_undocumented_features()
        if not undocumented:
            return PluginResult(status="success", data={"documented": 0, "message": "All features are documented"})

        total = len(undocumented)
        documented = 0
        all_docs: dict[str, dict] = {}
        errors: list[str] = []

        by_source: dict[str, list[Feature]] = {}
        for f in undocumented:
            src = f.name.split(".")[0] if "." in f.name else "unknown"
            by_source.setdefault(src, []).append(f)

        model_name = getattr(llm, "model", "unknown")

        for source_name, features in by_source.items():
            source = db.get_source_by_name(source_name)
            source_path = source.path if source else "unknown"

            for i in range(0, len(features), batch_size):
                batch = features[i : i + batch_size]
                features_text = self._format_batch(batch)

                prompt = AUTODOC_PROMPT_BATCH.format(
                    source_name=source_name,
                    source_path=source_path,
                    features_text=features_text,
                )

                try:
                    result = llm.generate_json(prompt, system=system)
                    docs_list = result if isinstance(result, list) else [result]

                    for doc in docs_list:
                        fname = doc.get("feature_name", "")
                        matching = [f for f in batch if f.name == fname or f.column_name == fname]
                        if matching:
                            db.save_feature_doc(matching[0].id, doc, model_used=model_name)
                            all_docs[matching[0].name] = doc
                            documented += 1
                except Exception as e:
                    errors.append(f"Batch error ({source_name}): {e}")

                if progress_callback:
                    progress_callback(min(documented + i + len(batch), total), total)

        status = "success" if not errors else "partial"
        return PluginResult(
            status=status,
            data={"documented": documented, "total": total, "features": all_docs},
            errors=errors,
        )

    def _format_batch(self, features: list[Feature]) -> str:
        lines = []
        for f in features:
            stats = "\n".join(f"    {k}: {v}" for k, v in f.stats.items()) if f.stats else "    (no stats)"
            lines.append(
                f"Feature: {f.name}\n"
                f"  Column: {f.column_name}\n"
                f"  Dtype: {f.dtype}\n"
                f"  Tags: {', '.join(f.tags) if f.tags else '(none)'}\n"
                f"  Stats:\n{stats}\n"
            )
        return "\n".join(lines)


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
