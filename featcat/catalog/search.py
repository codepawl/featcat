"""TF-IDF ranked feature search."""

from __future__ import annotations

from typing import Any


def _feature_text(f: dict) -> str:
    """Build text representation for TF-IDF from a feature dict."""
    parts = []
    name = f.get("name", "")
    parts.append(name.replace("_", " ").replace(".", " "))
    col = f.get("column_name", "")
    if col:
        parts.append(col.replace("_", " "))
    tags = f.get("tags", [])
    if tags:
        parts.extend(tags)
    desc = f.get("short_description", "") or f.get("description", "")
    if desc:
        parts.append(str(desc))
    hints = f.get("generation_hints")
    if hints:
        parts.append(str(hints))
    return " ".join(parts)


def search_features(
    query: str,
    features: list[dict[str, Any]],
    top_k: int = 50,
) -> list[tuple[dict[str, Any], float]]:
    """Return features ranked by TF-IDF cosine similarity to query.

    Each feature dict should have: name, column_name, tags, description/short_description, generation_hints.
    Returns list of (feature_dict, score) tuples, descending by score, score > 0 only.
    """
    if not query.strip():
        return [(f, 1.0) for f in features]

    if not features:
        return []

    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    corpus = [_feature_text(f) for f in features]
    corpus.append(query)

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    try:
        tfidf = vectorizer.fit_transform(corpus)
    except ValueError:
        return []

    query_vec = tfidf[-1]
    feature_vecs = tfidf[:-1]
    scores = cosine_similarity(query_vec, feature_vecs)[0]

    ranked = sorted(
        zip(features, scores.tolist(), strict=False),
        key=lambda x: x[1],
        reverse=True,
    )
    return [(f, round(score, 4)) for f, score in ranked if score > 0][:top_k]


def highlight_matches(query: str, feature: dict[str, Any]) -> dict[str, list[str]]:
    """Return which query tokens matched in each feature field."""
    tokens = [t.lower() for t in query.split() if len(t) >= 2]
    if not tokens:
        return {}

    highlights: dict[str, list[str]] = {}
    fields = {
        "column_name": (feature.get("column_name") or "").replace("_", " "),
        "name": (feature.get("name") or "").replace("_", " ").replace(".", " "),
        "short_description": str(feature.get("short_description") or feature.get("description") or ""),
        "tags": " ".join(feature.get("tags") or []),
    }

    for field_name, text in fields.items():
        text_lower = text.lower()
        matched = [t for t in tokens if t in text_lower]
        if matched:
            highlights[field_name] = matched

    return highlights
