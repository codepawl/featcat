"""Helpers to extract catalog data as text for LLM context."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..catalog.backend import CatalogBackend


def get_feature_summary(db: CatalogBackend, max_features: int = 100) -> str:
    """Format catalog features as a text summary for LLM prompts.

    Returns a concise table-like text listing all features with key metadata.
    Truncates to max_features if the catalog is large.
    """
    features = db.list_features()
    if not features:
        return "No features in catalog."

    lines = ["FEATURE CATALOG SUMMARY", "=" * 60]
    lines.append(f"Total features: {len(features)}")
    lines.append("")
    lines.append(f"{'Name':<40} {'Dtype':<10} {'Tags':<30} {'Nulls'}")
    lines.append("-" * 90)

    for f in features[:max_features]:
        tags = ", ".join(f.tags) if f.tags else ""
        null_ratio = f.stats.get("null_ratio", "?")
        null_str = f"{null_ratio:.1%}" if isinstance(null_ratio, (int, float)) else str(null_ratio)
        lines.append(f"{f.name:<40} {f.dtype:<10} {tags:<30} {null_str}")

    if len(features) > max_features:
        lines.append(f"\n... and {len(features) - max_features} more features (truncated)")

    return "\n".join(lines)


def get_feature_detail(db: CatalogBackend, feature_name: str) -> str:
    """Format detailed information about one feature for LLM context."""
    feature = db.get_feature_by_name(feature_name)
    if feature is None:
        return f"Feature '{feature_name}' not found."

    lines = [
        f"FEATURE: {feature.name}",
        f"  Column: {feature.column_name}",
        f"  Dtype: {feature.dtype}",
        f"  Description: {feature.description or '(none)'}",
        f"  Tags: {', '.join(feature.tags) if feature.tags else '(none)'}",
        f"  Owner: {feature.owner or '(none)'}",
    ]

    if feature.stats:
        lines.append("  Statistics:")
        for k, v in feature.stats.items():
            lines.append(f"    {k}: {v}")

    return "\n".join(lines)


def get_source_schema(db: CatalogBackend, source_name: str) -> str:
    """Format the schema of a data source (all its features) for LLM context."""
    source = db.get_source_by_name(source_name)
    if source is None:
        return f"Source '{source_name}' not found."

    features = db.list_features(source_name=source_name)
    lines = [
        f"DATA SOURCE: {source.name}",
        f"  Path: {source.path}",
        f"  Format: {source.format}",
        f"  Storage: {source.storage_type}",
        f"  Description: {source.description or '(none)'}",
        f"  Columns ({len(features)}):",
    ]

    for f in features:
        stats_summary = ""
        if f.stats:
            parts = []
            for k in ("mean", "std", "min", "max", "null_ratio", "unique_count"):
                if k in f.stats:
                    parts.append(f"{k}={f.stats[k]}")
            stats_summary = " | " + ", ".join(parts) if parts else ""
        lines.append(f"    - {f.column_name} ({f.dtype}){stats_summary}")

    return "\n".join(lines)


def get_all_sources_schema(db: CatalogBackend) -> str:
    """Format schemas for all data sources."""
    sources = db.list_sources()
    if not sources:
        return "No data sources registered."

    parts = []
    for source in sources:
        parts.append(get_source_schema(db, source.name))

    return "\n\n".join(parts)


def get_features_for_source(db: CatalogBackend, source_name: str) -> list[dict]:
    """Get features as simple dicts for a data source (for batch prompts)."""
    features = db.list_features(source_name=source_name)
    return [
        {
            "name": f.name,
            "column_name": f.column_name,
            "dtype": f.dtype,
            "tags": f.tags,
            "stats": f.stats,
            "description": f.description,
        }
        for f in features
    ]
