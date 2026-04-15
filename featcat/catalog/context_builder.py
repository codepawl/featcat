"""Context builder for doc generation with TF-IDF similarity."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .backend import CatalogBackend


@dataclass
class FeatureContext:
    """A related feature selected as context for doc generation."""

    spec: str
    dtype: str
    stats_summary: dict = field(default_factory=dict)
    generation_hints: str | None = None
    source: str = "same_source"  # "same_source_same_group" | "same_source" | "cross_source"
    similarity: float | None = None  # only for cross_source


def _extract_stats_summary(stats: dict) -> dict:
    """Extract only mean, std, null_ratio from stats."""
    keys = ("mean", "std", "null_ratio")
    return {k: stats[k] for k in keys if k in stats}


def _feature_text(name: str, tags: list[str]) -> str:
    """Build text representation for TF-IDF: feature name tokens + tags."""
    parts = name.replace(".", " ").replace("_", " ").split()
    parts.extend(tags)
    return " ".join(parts)


def build_doc_context(
    feature_id: str,
    db: CatalogBackend,
    max_context_features: int = 8,
) -> list[FeatureContext]:
    """Select related features as context for doc generation.

    Selection priority:
    1. Same source + same feature group (up to 4)
    2. Same source, different group (fill remaining)
    3. Cross-source TF-IDF similarity (fill remaining, threshold 0.15)
    """
    # Get target feature
    target = None
    all_features = db.list_features()
    for f in all_features:
        if f.id == feature_id:
            target = f
            break
    if target is None:
        return []

    target_source = target.name.split(".")[0] if "." in target.name else ""
    context: list[FeatureContext] = []
    used_ids: set[str] = {feature_id}

    # Get groups the target belongs to
    target_group_ids: set[str] = set()
    try:
        all_groups = db.list_groups()
        for g in all_groups:
            members = db.list_group_members(g.id)
            if any(m.id == feature_id for m in members):
                target_group_ids.add(g.id)
    except Exception:  # noqa: BLE001
        pass  # Groups may not be set up

    # 1. Same source + same group (up to 4)
    if target_group_ids:
        for g_id in target_group_ids:
            if len(context) >= 4:
                break
            try:
                members = db.list_group_members(g_id)
                for m in members:
                    if m.id in used_ids:
                        continue
                    source = m.name.split(".")[0] if "." in m.name else ""
                    if source != target_source:
                        continue
                    context.append(FeatureContext(
                        spec=m.name,
                        dtype=m.dtype,
                        stats_summary=_extract_stats_summary(m.stats),
                        generation_hints=m.generation_hints,
                        source="same_source_same_group",
                    ))
                    used_ids.add(m.id)
                    if len(context) >= 4:
                        break
            except Exception:  # noqa: BLE001
                pass

    # 2. Same source, other features (fill remaining up to max)
    same_source_features = [
        f for f in all_features
        if f.id not in used_ids
        and "." in f.name
        and f.name.split(".")[0] == target_source
    ]
    for f in same_source_features:
        if len(context) >= max_context_features:
            break
        context.append(FeatureContext(
            spec=f.name,
            dtype=f.dtype,
            stats_summary=_extract_stats_summary(f.stats),
            generation_hints=f.generation_hints,
            source="same_source",
        ))
        used_ids.add(f.id)

    # 3. Cross-source TF-IDF similarity
    remaining = max_context_features - len(context)
    if remaining > 0:
        other_features = [
            f for f in all_features
            if f.id not in used_ids
        ]
        if other_features:
            cross_source = _tfidf_similar(target, other_features, top_k=remaining)
            context.extend(cross_source)

    return context


def _tfidf_similar(
    target: object,
    candidates: list,
    top_k: int,
    threshold: float = 0.15,
) -> list[FeatureContext]:
    """Find cross-source features similar to target using TF-IDF cosine similarity."""
    try:
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity
    except ImportError:
        return []

    target_text = _feature_text(target.name, target.tags or [])  # type: ignore[union-attr]
    candidate_texts = [_feature_text(f.name, f.tags or []) for f in candidates]

    all_texts = [target_text, *candidate_texts]
    vectorizer = TfidfVectorizer()
    try:
        tfidf_matrix = vectorizer.fit_transform(all_texts)
    except ValueError:
        return []

    similarities = cosine_similarity(tfidf_matrix[0:1], tfidf_matrix[1:]).flatten()

    # Sort by similarity descending, take top_k above threshold
    scored = sorted(
        zip(candidates, similarities, strict=False),
        key=lambda x: x[1],
        reverse=True,
    )

    results: list[FeatureContext] = []
    for feat, sim in scored[:top_k]:
        if sim < threshold:
            break
        results.append(FeatureContext(
            spec=feat.name,
            dtype=feat.dtype,
            stats_summary=_extract_stats_summary(feat.stats),
            generation_hints=feat.generation_hints,
            source="cross_source",
            similarity=round(float(sim), 4),
        ))
    return results
