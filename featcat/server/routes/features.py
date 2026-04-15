"""Feature management endpoints."""

from __future__ import annotations

import contextlib

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ...catalog.health import compute_health_score
from ...catalog.usage import log_feature_usage
from ..deps import get_db

router = APIRouter()


def _bulk_health_data(db) -> tuple[dict, dict, dict]:
    """Batch-query docs, drift, and usage data for health score computation.

    Returns (doc_map, drift_map, usage_map) keyed by feature_id.
    """
    all_docs = db.get_all_feature_docs()

    # Drift: latest severity per feature
    drift_map: dict[str, str] = {}
    with contextlib.suppress(Exception):
        rows = db.conn.execute(
            """SELECT feature_id, severity FROM monitoring_checks
               WHERE (feature_id, checked_at) IN (
                   SELECT feature_id, MAX(checked_at) FROM monitoring_checks GROUP BY feature_id
               )"""
        ).fetchall()
        for r in rows:
            drift_map[r["feature_id"]] = r["severity"]

    # Usage: views and queries in last 30 days per feature
    usage_map: dict[str, dict[str, int]] = {}
    with contextlib.suppress(Exception):
        rows = db.conn.execute(
            """SELECT feature_id,
                      SUM(CASE WHEN action = 'view' THEN 1 ELSE 0 END) as views,
                      SUM(CASE WHEN action = 'query' THEN 1 ELSE 0 END) as queries
               FROM usage_log
               WHERE created_at >= datetime('now', '-30 days')
               GROUP BY feature_id"""
        ).fetchall()
        for r in rows:
            usage_map[r["feature_id"]] = {"views": r["views"] or 0, "queries": r["queries"] or 0}

    return all_docs, drift_map, usage_map


def _enrich_with_health(d: dict, feature_id: str, all_docs: dict, drift_map: dict, usage_map: dict) -> None:
    """Add health score fields to a feature dict in-place."""
    has_doc = feature_id in all_docs
    has_hints = bool(d.get("generation_hints"))
    drift_status = drift_map.get(feature_id)
    usage = usage_map.get(feature_id, {"views": 0, "queries": 0})
    health = compute_health_score(
        has_doc=has_doc,
        has_hints=has_hints,
        drift_status=drift_status,
        views_30d=usage["views"],
        queries_30d=usage["queries"],
    )
    d["health_score"] = health["score"]
    d["health_grade"] = health["grade"]
    d["health_breakdown"] = health["breakdown"]


class FeatureUpdate(BaseModel):
    tags: list[str] | None = None
    owner: str | None = None
    description: str | None = None


@router.get("")
def list_features(
    source: str | None = None,
    search: str | None = None,
    dtype: str | None = None,
    health_grade: str | None = None,
    drift_status: str | None = None,
    has_doc: bool | None = None,
    owner: str | None = None,
    tag: str | None = None,
    sort: str = Query("name", pattern="^(name|health|created_at|updated_at)$"),
    order: str = Query("asc", pattern="^(asc|desc)$"),
    db=Depends(get_db),  # noqa: B008
):
    """List features with filters, sorting, and TF-IDF ranked search."""
    from ...catalog.search import highlight_matches, search_features

    features = db.list_features(source_name=source)
    all_docs, drift_map, usage_map = _bulk_health_data(db)

    # Enrich all features first
    enriched = []
    for f in features:
        d = f.model_dump(mode="json")
        d["has_doc"] = f.id in all_docs
        doc = all_docs.get(f.id)
        d["short_description"] = doc.get("short_description", "") if doc else ""
        _enrich_with_health(d, f.id, all_docs, drift_map, usage_map)
        enriched.append(d)

    # Apply filters
    if dtype:
        enriched = [d for d in enriched if d.get("dtype") == dtype]
    if health_grade:
        enriched = [d for d in enriched if d.get("health_grade") == health_grade]
    if drift_status:
        enriched = [d for d in enriched if drift_map.get(d["id"], "healthy") == drift_status]
    if has_doc is not None:
        enriched = [d for d in enriched if d.get("has_doc") == has_doc]
    if owner:
        enriched = [d for d in enriched if d.get("owner") == owner]
    if tag:
        enriched = [d for d in enriched if tag in (d.get("tags") or [])]

    # Search or sort
    search_scores: dict[str, float] = {}
    highlights: dict[str, dict] = {}
    if search:
        ranked = search_features(search, enriched)
        enriched = [f for f, _ in ranked]
        search_scores = {f["name"]: score for f, score in ranked}
        highlights = {f["name"]: highlight_matches(search, f) for f, _ in ranked}
        for f in features:
            if f.id and search:
                log_feature_usage(db, f.id, "search", context=search)
    else:
        sort_key = sort
        reverse = order == "desc"
        if sort_key == "health":
            enriched.sort(key=lambda d: d.get("health_score", 0), reverse=reverse)
        elif sort_key == "created_at":
            enriched.sort(key=lambda d: d.get("created_at", ""), reverse=reverse)
        elif sort_key == "updated_at":
            enriched.sort(key=lambda d: d.get("updated_at", ""), reverse=reverse)
        else:
            enriched.sort(key=lambda d: d.get("name", ""), reverse=reverse)

    # Add highlights to results
    for d in enriched:
        if d["name"] in highlights:
            d["highlight"] = highlights[d["name"]]
        if d["name"] in search_scores:
            d["search_score"] = search_scores[d["name"]]

    return enriched


@router.get("/health-summary")
def health_summary(db=Depends(get_db)):
    """Return aggregate health stats for the catalog."""
    features = db.list_features()
    if not features:
        return {
            "grade_distribution": {"A": 0, "B": 0, "C": 0, "D": 0},
            "average_score": 0,
            "lowest_scored": [],
            "improvement_opportunities": [],
        }

    all_docs, drift_map, usage_map = _bulk_health_data(db)

    grades: dict[str, int] = {"A": 0, "B": 0, "C": 0, "D": 0}
    scored: list[dict] = []

    for f in features:
        has_doc = f.id in all_docs
        has_hints = bool(f.generation_hints)
        drift_status = drift_map.get(f.id)
        usage = usage_map.get(f.id, {"views": 0, "queries": 0})
        health = compute_health_score(
            has_doc=has_doc,
            has_hints=has_hints,
            drift_status=drift_status,
            views_30d=usage["views"],
            queries_30d=usage["queries"],
        )
        grades[health["grade"]] += 1
        scored.append({
            "spec": f.name, "score": health["score"],
            "grade": health["grade"], "breakdown": health["breakdown"],
        })

    scored.sort(key=lambda x: x["score"])
    avg = round(sum(s["score"] for s in scored) / len(scored))

    lowest = [{"spec": s["spec"], "score": s["score"], "grade": s["grade"]} for s in scored[:5]]

    opportunities = []
    for s in scored:
        if s["score"] >= 60:
            continue
        missing = []
        if s["breakdown"]["documentation"] == 0:
            missing.append("documentation")
        if s["breakdown"]["drift"] == 0:
            missing.append("critical_drift")
        if s["breakdown"]["usage"] == 0:
            missing.append("never_queried")
        if missing:
            opportunities.append({"spec": s["spec"], "missing": missing})

    return {
        "grade_distribution": grades,
        "average_score": avg,
        "lowest_scored": lowest,
        "improvement_opportunities": opportunities[:10],
    }


class RollbackRequest(BaseModel):
    version: int


@router.get("/by-name/versions")
def list_versions(name: str = Query(...), db=Depends(get_db)):
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    return db.list_feature_versions(feature.id)


@router.get("/by-name/versions/{version}")
def get_version(version: int, name: str = Query(...), db=Depends(get_db)):
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    v = db.get_feature_version(feature.id, version)
    if v is None:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    return v


@router.post("/by-name/rollback")
def rollback_feature_endpoint(name: str = Query(...), body: RollbackRequest = ..., db=Depends(get_db)):
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    try:
        result = db.rollback_feature(feature.id, body.version)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    return result


@router.get("/by-name")
def get_feature_by_name(name: str = Query(...), db=Depends(get_db)):
    """Get a feature by name (query param for dotted names)."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    log_feature_usage(db, feature.id, "view")
    d = feature.model_dump(mode="json")
    all_docs, drift_map, usage_map = _bulk_health_data(db)
    d["has_doc"] = feature.id in all_docs
    _enrich_with_health(d, feature.id, all_docs, drift_map, usage_map)
    return d


@router.patch("/by-name")
def update_feature_by_name(name: str = Query(...), body: FeatureUpdate = ..., db=Depends(get_db)):
    """Update feature metadata (tags, owner, description)."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    updates = body.model_dump(exclude_none=True)
    if updates:
        db.update_feature_metadata(feature.id, **updates)
    return {"updated": name}


@router.delete("/by-name")
def delete_feature_by_name(name: str = Query(...), db=Depends(get_db)):
    """Delete a feature."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    return {"deleted": name}


# --- Feature Definitions ---


class DefinitionUpdate(BaseModel):
    definition: str
    definition_type: str = "sql"  # "sql" | "python" | "manual"


@router.get("/by-name/definition")
def get_definition(name: str = Query(...), db=Depends(get_db)):
    """Get a feature's definition."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    defn = db.get_feature_definition(feature.id)
    if defn is None:
        return {"definition": None, "definition_type": None, "definition_updated_at": None}
    return defn


@router.put("/by-name/definition")
def set_definition(name: str = Query(...), body: DefinitionUpdate = ..., db=Depends(get_db)):
    """Set or update a feature's definition."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    db.set_feature_definition(feature.id, body.definition, body.definition_type)
    return {"updated": name}


@router.delete("/by-name/definition")
def delete_definition(name: str = Query(...), db=Depends(get_db)):
    """Remove a feature's definition."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    db.clear_feature_definition(feature.id)
    return {"deleted": name}


# --- Generation Hints ---


class HintsUpdate(BaseModel):
    hints: str


@router.get("/by-name/hints")
def get_hints(name: str = Query(...), db=Depends(get_db)):
    """Get generation hints for a feature."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    hint = db.get_feature_hint(feature.id)
    return {"spec": name, "hints": hint}


@router.patch("/by-name/hints")
def set_hints(name: str = Query(...), body: HintsUpdate = ..., db=Depends(get_db)):
    """Set generation hints for a feature."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    db.set_feature_hint(feature.id, body.hints)
    return {"spec": name, "hints": body.hints}


@router.delete("/by-name/hints")
def delete_hints(name: str = Query(...), db=Depends(get_db)):
    """Remove generation hints for a feature."""
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    db.clear_feature_hint(feature.id)
    return {"spec": name, "hints": None}


# --- Similarity Graph ---


@router.get("/similarity-graph")
def similarity_graph(
    threshold: float = Query(0.3, ge=0.1, le=0.9),
    source: str | None = None,
    db=Depends(get_db),  # noqa: B008
):
    """Return feature similarity graph computed via TF-IDF cosine similarity."""
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity

    features = db.list_features(source_name=source)
    if len(features) < 2:
        return {"nodes": [], "edges": []}

    # Enrich with doc info and drift status
    all_docs = db.get_all_feature_docs()
    doc_map = {fid: doc.get("short_description", "") for fid, doc in all_docs.items()}

    # Drift status: query monitoring_checks for latest severity per feature
    drift_map: dict[str, str] = {}
    for f in features:
        row = db.conn.execute(
            "SELECT severity FROM monitoring_checks WHERE feature_id = ? ORDER BY checked_at DESC LIMIT 1",
            (f.id,),
        ).fetchone()
        if row:
            drift_map[f.id] = row["severity"]

    # Build text corpus
    corpus = []
    for f in features:
        text = f.name.replace("_", " ").replace(".", " ")
        if f.tags:
            text += " " + " ".join(f.tags)
        short_desc = doc_map.get(f.id, "")
        if short_desc:
            text += " " + short_desc
        corpus.append(text)

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    tfidf_matrix = vectorizer.fit_transform(corpus)
    sim_matrix = cosine_similarity(tfidf_matrix)

    max_edges_per_node = 5
    nodes = []
    for f in features:
        src = f.name.split(".")[0] if "." in f.name else ""
        nodes.append({
            "id": f.name,
            "spec": f.name,
            "source": src,
            "dtype": f.dtype,
            "has_doc": f.id in all_docs,
            "drift_status": drift_map.get(f.id, "healthy"),
            "tags": f.tags or [],
        })

    edges = []
    seen: set[tuple[str, str]] = set()
    for i, f in enumerate(features):
        sims = sim_matrix[i].copy()
        sims[i] = 0  # exclude self
        top_k = np.argsort(sims)[::-1][:max_edges_per_node]
        for j in top_k:
            score = float(sims[j])
            if score < threshold:
                break
            pair = (min(f.name, features[j].name), max(f.name, features[j].name))
            if pair in seen:
                continue
            seen.add(pair)
            edges.append({
                "source": f.name,
                "target": features[j].name,
                "similarity": round(score, 3),
            })

    return {"nodes": nodes, "edges": edges}
