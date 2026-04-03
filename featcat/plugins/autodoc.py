"""Auto Documentation plugin: generate and manage feature documentation."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any, Optional

from ..catalog.db import CatalogDB
from ..catalog.models import Feature
from ..llm.base import BaseLLM
from ..utils.catalog_context import get_features_for_source
from ..utils.prompts import AUTODOC_PROMPT_BATCH, AUTODOC_PROMPT_SINGLE, AUTODOC_SYSTEM
from .base import BasePlugin, PluginResult


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
        catalog_db: CatalogDB,
        llm: BaseLLM,
        **kwargs: Any,
    ) -> PluginResult:
        """Generate documentation for features.

        Args:
            feature_name: If provided, document only this feature.
            batch_size: Max features per LLM call (default 10).
            progress_callback: Optional callable(current, total) for progress.
        """
        feature_name: Optional[str] = kwargs.get("feature_name")
        batch_size: int = kwargs.get("batch_size", 10)
        progress_callback = kwargs.get("progress_callback")

        if feature_name:
            return self._document_single(catalog_db, llm, feature_name)
        else:
            return self._document_all(catalog_db, llm, batch_size, progress_callback)

    def _document_single(
        self,
        db: CatalogDB,
        llm: BaseLLM,
        feature_name: str,
    ) -> PluginResult:
        """Generate documentation for a single feature."""
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
            doc = llm.generate_json(prompt, system=AUTODOC_SYSTEM)
        except Exception as e:
            return PluginResult(status="error", errors=[str(e)])

        self._save_doc(db, feature.id, doc, llm)

        return PluginResult(status="success", data={"documented": 1, "features": {feature.name: doc}})

    def _document_all(
        self,
        db: CatalogDB,
        llm: BaseLLM,
        batch_size: int,
        progress_callback: Any,
    ) -> PluginResult:
        """Generate docs for all undocumented features, batched by source."""
        undocumented = self._get_undocumented(db)
        if not undocumented:
            return PluginResult(status="success", data={"documented": 0, "message": "All features are documented"})

        total = len(undocumented)
        documented = 0
        all_docs: dict[str, dict] = {}
        errors: list[str] = []

        # Group by source
        by_source: dict[str, list[Feature]] = {}
        for f in undocumented:
            src = f.name.split(".")[0] if "." in f.name else "unknown"
            by_source.setdefault(src, []).append(f)

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
                    result = llm.generate_json(prompt, system=AUTODOC_SYSTEM)
                    docs_list = result if isinstance(result, list) else [result]

                    for doc in docs_list:
                        fname = doc.get("feature_name", "")
                        matching = [f for f in batch if f.name == fname or f.column_name == fname]
                        if matching:
                            self._save_doc(db, matching[0].id, doc, llm)
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

    def _get_undocumented(self, db: CatalogDB) -> list[Feature]:
        """Find features without docs or with outdated docs."""
        rows = db.conn.execute(
            """SELECT f.* FROM features f
               LEFT JOIN feature_docs fd ON f.id = fd.feature_id
               WHERE fd.feature_id IS NULL OR f.updated_at > fd.generated_at"""
        ).fetchall()
        from ..catalog.db import _row_to_feature
        return [_row_to_feature(r) for r in rows]

    def _format_batch(self, features: list[Feature]) -> str:
        """Format a batch of features for the batch prompt."""
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

    def _save_doc(self, db: CatalogDB, feature_id: str, doc: dict, llm: BaseLLM) -> None:
        """Save or update a feature doc in the database."""
        now = datetime.now(timezone.utc)
        model_name = getattr(llm, "model", "unknown")

        # Delete existing doc if any
        db.conn.execute("DELETE FROM feature_docs WHERE feature_id = ?", (feature_id,))
        db.conn.execute(
            """INSERT INTO feature_docs
               (feature_id, short_description, long_description, expected_range, potential_issues, generated_at, model_used)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                feature_id,
                doc.get("short_description", ""),
                doc.get("long_description", ""),
                doc.get("expected_range", ""),
                doc.get("potential_issues", ""),
                now,
                model_name,
            ),
        )
        db.conn.commit()


def get_doc(db: CatalogDB, feature_name: str) -> Optional[dict]:
    """Retrieve documentation for a feature."""
    feature = db.get_feature_by_name(feature_name)
    if feature is None:
        return None

    row = db.conn.execute(
        "SELECT * FROM feature_docs WHERE feature_id = ?", (feature.id,)
    ).fetchone()
    if row is None:
        return None
    return dict(row)


def get_doc_stats(db: CatalogDB) -> dict:
    """Get documentation coverage statistics."""
    total = db.conn.execute("SELECT COUNT(*) FROM features").fetchone()[0]
    documented = db.conn.execute(
        "SELECT COUNT(DISTINCT feature_id) FROM feature_docs"
    ).fetchone()[0]
    return {
        "total_features": total,
        "documented": documented,
        "undocumented": total - documented,
        "coverage": round(documented / total * 100, 1) if total > 0 else 0.0,
    }


def export_docs_markdown(db: CatalogDB) -> str:
    """Export all feature documentation to Markdown."""
    features = db.list_features()
    lines = ["# Feature Documentation", "", f"*Generated from featcat catalog*", ""]

    # Group by source
    by_source: dict[str, list] = {}
    for f in features:
        src = f.name.split(".")[0] if "." in f.name else "unknown"
        by_source.setdefault(src, []).append(f)

    for source_name, feats in sorted(by_source.items()):
        lines.append(f"## {source_name}")
        lines.append("")

        for f in feats:
            row = db.conn.execute(
                "SELECT * FROM feature_docs WHERE feature_id = ?", (f.id,)
            ).fetchone()

            lines.append(f"### {f.name}")
            lines.append("")
            lines.append(f"- **Column:** `{f.column_name}`")
            lines.append(f"- **Type:** `{f.dtype}`")
            lines.append(f"- **Tags:** {', '.join(f.tags) if f.tags else '(none)'}")

            if f.stats:
                lines.append(f"- **Stats:** mean={f.stats.get('mean', '?')}, "
                           f"std={f.stats.get('std', '?')}, "
                           f"null_ratio={f.stats.get('null_ratio', '?')}")

            if row:
                doc = dict(row)
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
