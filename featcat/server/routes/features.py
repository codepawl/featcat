"""Feature management endpoints."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
from datetime import datetime, timedelta, timezone
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text
from starlette.concurrency import run_in_threadpool

from ...catalog.health import compute_health_score
from ...catalog.usage import log_feature_usage
from ..cache import cache_get, cache_set
from ..deps import get_db, get_llm

router = APIRouter()


def _bulk_health_data(db) -> tuple[dict, dict, dict]:
    """Batch-query docs, drift, and usage data for health score computation.

    Returns (doc_map, drift_map, usage_map) keyed by feature_id.
    """
    all_docs = db.get_all_feature_docs()

    # Drift: latest severity per feature
    drift_map: dict[str, str] = {}
    with contextlib.suppress(Exception):
        with db.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT feature_id, severity FROM monitoring_checks "
                        "WHERE (feature_id, checked_at) IN ( "
                        "  SELECT feature_id, MAX(checked_at) FROM monitoring_checks GROUP BY feature_id "
                        ")"
                    )
                )
                .mappings()
                .all()
            )
        for r in rows:
            drift_map[r["feature_id"]] = r["severity"]

    # Usage: views and queries in last 30 days per feature.
    # Cutoff computed in Python so SQL is portable across sqlite/postgres.
    usage_map: dict[str, dict[str, int]] = {}
    with contextlib.suppress(Exception):
        cutoff = datetime.now(timezone.utc) - timedelta(days=30)
        with db.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT feature_id, "
                        "  SUM(CASE WHEN action = 'view' THEN 1 ELSE 0 END) as views, "
                        "  SUM(CASE WHEN action = 'query' THEN 1 ELSE 0 END) as queries "
                        "FROM usage_log WHERE created_at >= :cutoff GROUP BY feature_id"
                    ),
                    {"cutoff": cutoff},
                )
                .mappings()
                .all()
            )
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
    limit: int | None = Query(None, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db=Depends(get_db),  # noqa: B008
):
    """List features with filters, sorting, and TF-IDF ranked search.

    Backward-compat envelope:
    - No ``?limit`` → returns the full list (current behavior). ``health_grade``
      and ``drift_status`` work in this mode because filtering happens
      in-memory after enrichment.
    - ``?limit=N`` (1..500) → returns ``{items, total, limit, offset}`` with
      filters pushed down to SQL. ``health_grade`` and ``drift_status`` are
      ignored in paginated mode (they require full-set enrichment before
      filter; document via 400 if/when needed). Use unpaginated mode for those.
    """
    from ...catalog.search import highlight_matches, search_features

    if limit is not None:
        return _list_features_paginated(
            db=db,
            source=source,
            search=search,
            dtype=dtype,
            has_doc=has_doc,
            owner=owner,
            tag=tag,
            sort=sort if sort != "health" else "name",  # health sort needs enrichment; fall back
            order=order,
            limit=limit,
            offset=offset,
        )

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
        enriched = [d for d in enriched if drift_map.get(d["id"], "unknown") == drift_status]
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


def _list_features_paginated(
    *,
    db: Any,
    source: str | None,
    search: str | None,
    dtype: str | None,
    has_doc: bool | None,
    owner: str | None,
    tag: str | None,
    sort: str,
    order: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    """Paginated path — pushes filters to SQL and enriches only the page slice.

    For 5000+-feature catalogs, this avoids the O(N) full-list load that the
    legacy in-memory path does. Health/drift enrichment runs on the returned
    rows only (≤ ``limit``).
    """
    items_features = db.list_features(
        source_name=source,
        dtype=dtype,
        owner=owner,
        tag=tag,
        search=search,
        has_doc=has_doc,
        sort=sort,
        order=order,
        limit=limit,
        offset=offset,
    )
    total = db.count_features(
        source_name=source,
        dtype=dtype,
        owner=owner,
        tag=tag,
        search=search,
        has_doc=has_doc,
    )
    all_docs, drift_map, usage_map = _bulk_health_data(db)
    items: list[dict] = []
    for f in items_features:
        d = f.model_dump(mode="json")
        d["has_doc"] = f.id in all_docs
        doc = all_docs.get(f.id)
        d["short_description"] = doc.get("short_description", "") if doc else ""
        _enrich_with_health(d, f.id, all_docs, drift_map, usage_map)
        items.append(d)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


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
        scored.append(
            {
                "spec": f.name,
                "score": health["score"],
                "grade": health["grade"],
                "breakdown": health["breakdown"],
            }
        )

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


class StatusCountsResponse(BaseModel):
    """Aggregated certification-status counts for the Dashboard tile."""

    draft: int
    reviewed: int
    certified: int
    deprecated: int
    total: int


@router.get("/stats/status-counts", response_model=StatusCountsResponse)
def status_counts(db=Depends(get_db)) -> StatusCountsResponse:
    """Return per-status feature counts in one query.

    Replaces the Dashboard tile's prior pattern of fetching the full feature
    list and counting client-side. A single ``GROUP BY status`` is O(1) on
    the wire vs. O(N) rows, which matters at 5k+ features.
    """
    counts = db.get_status_counts()
    return StatusCountsResponse(**counts)


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


@router.get("/by-name/certification-readiness")
def get_certification_readiness(
    name: str = Query(..., description="Feature name (source.column)"),
    db=Depends(get_db),  # noqa: B008
) -> dict:
    """Return ``{ready, missing}`` for a feature (T3.1).

    Certified-ready means: has documentation + data source + at least one
    monitoring baseline + owner + (group membership OR explicit standalone tag).
    """
    feat = db.get_feature_by_name(name)
    if feat is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    return db.check_certification_readiness(feat.id)


class StatusChangeRequest(BaseModel):
    status: str
    notes: str | None = None


@router.post("/by-name/status")
def set_status_by_name(
    body: StatusChangeRequest,
    name: str = Query(..., description="Feature name (source.column)"),
    db=Depends(get_db),  # noqa: B008
) -> dict:
    """Transition a feature's lifecycle status.

    422 with ``{missing}`` when target status is ``certified`` and the
    readiness gate fails. 400 for an unknown status string. 404 if the
    feature doesn't exist.
    """
    feat = db.get_feature_by_name(name)
    if feat is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    try:
        result = db.set_feature_status(feat.id, body.status, body.notes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    if not result["ok"]:
        raise HTTPException(
            status_code=422,
            detail={"message": "Feature is not ready for certification.", "missing": result["missing"]},
        )
    return {"name": name, "status": result["status"]}


@router.get("/by-name/similar")
def get_similar_by_name(
    name: str = Query(..., description="Feature name (source.column)"),
    top_k: int = Query(10, ge=1, le=50),
    db=Depends(get_db),  # noqa: B008
):
    """Return the ``top_k`` features most similar to ``name`` (T1.2b).

    Postgres + embeddings present → pgvector ``<=>`` cosine top-K.
    Anywhere else → TF-IDF cosine over name + description + tags. Both
    return ``[{id, name, dtype, similarity}]``. Registered ABOVE
    ``/by-name`` so FastAPI's longest-match wins despite the shared prefix.
    """
    feature = db.get_feature_by_name(name)
    if feature is None:
        raise HTTPException(status_code=404, detail=f"Feature not found: {name}")
    return db.find_similar_features(feature.id, top_k=top_k)


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

    # Drift status: latest severity per feature via the LocalBackend helper.
    # Closes both the rule violation (route was hitting raw .conn) and the
    # hot-reload race that flagged in PR #1's known-followups.
    drift_map: dict[str, str] = {}
    for f in features:
        sev = db.get_latest_severity(f.id)
        if sev is not None:
            drift_map[f.id] = sev

    # Build text corpus (variable renamed from `text` to avoid shadowing the
    # ``sqlalchemy.text`` import used above).
    corpus = []
    for f in features:
        doc_text = f.name.replace("_", " ").replace(".", " ")
        if f.tags:
            doc_text += " " + " ".join(f.tags)
        short_desc = doc_map.get(f.id, "")
        if short_desc:
            doc_text += " " + short_desc
        corpus.append(doc_text)

    vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
    tfidf_matrix = vectorizer.fit_transform(corpus)
    sim_matrix = cosine_similarity(tfidf_matrix)

    max_edges_per_node = 5
    nodes = []
    for f in features:
        src = f.name.split(".")[0] if "." in f.name else ""
        nodes.append(
            {
                "id": f.name,
                "spec": f.name,
                "source": src,
                "dtype": f.dtype,
                "has_doc": f.id in all_docs,
                "drift_status": drift_map.get(f.id, "unknown"),
                "tags": f.tags or [],
            }
        )

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
            edges.append(
                {
                    "source": f.name,
                    "target": features[j].name,
                    "similarity": round(score, 3),
                }
            )

    return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# Duplicate pairs + use-case recommendations (T-similarity-refactor)
# ---------------------------------------------------------------------------


class DuplicateReason(BaseModel):
    code: Literal["name_similarity", "schema_match", "distribution_match", "semantic_match"]
    detail: str


class FeatureBrief(BaseModel):
    id: str
    name: str
    dtype: str
    source: str
    has_doc: bool


class DuplicatePair(BaseModel):
    a: FeatureBrief
    b: FeatureBrief
    score: float
    reasons: list[DuplicateReason]


class DuplicatesResponse(BaseModel):
    threshold: float
    pairs: list[DuplicatePair]
    total: int
    cached_at: str | None = None
    summary: str | None = None


def _parse_source_filter(raw: str | None) -> list[str] | None:
    if not raw:
        return None
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    return parts or None


@router.get("/duplicates", response_model=DuplicatesResponse)
def get_duplicates(
    threshold: float = Query(0.7, ge=0.4, le=0.95),
    limit: int = Query(100, ge=1, le=500),
    source: str | None = Query(None, description="Comma-separated source names; both sides must match"),
    db=Depends(get_db),  # noqa: B008
) -> DuplicatesResponse:
    """Return ranked pairs of features that look like duplicates.

    Cross-source pairs included by default. Pass ``source=foo,bar`` to scope
    both sides of every pair to that set.
    """
    sources = _parse_source_filter(source)
    cache_key = f"duplicates:{threshold}:{','.join(sorted(sources)) if sources else '*'}:{limit}"
    cached = cache_get(cache_key)
    if cached is not None:
        return DuplicatesResponse(**cached)

    pairs, total, summary = db.find_duplicate_pairs(threshold=threshold, limit=limit, sources=sources)
    payload = DuplicatesResponse(
        threshold=threshold,
        pairs=[DuplicatePair(**p) for p in pairs],
        total=total,
        cached_at=None,
        summary=summary,
    )
    # Store with a fresh cached_at timestamp so subsequent cache hits surface
    # the staleness to the UI.
    stored = payload.model_dump()
    stored["cached_at"] = datetime.now(timezone.utc).isoformat()
    cache_set(cache_key, stored, ttl=300)
    return payload


# ---------------------------------------------------------------------------
# Similarity matrix (caller-selected feature subset) + per-pair reason lookup
# ---------------------------------------------------------------------------


class MatrixCell(BaseModel):
    a: int
    b: int
    score: float


class MatrixResponse(BaseModel):
    features: list[FeatureBrief]
    cells: list[MatrixCell]
    threshold: float
    cached_at: str | None = None


class PairResponse(BaseModel):
    a: FeatureBrief
    b: FeatureBrief
    score: float
    reasons: list[DuplicateReason]


def _parse_id_list(raw: str) -> list[str]:
    parts = [p.strip() for p in raw.split(",") if p.strip()]
    if not parts:
        raise HTTPException(status_code=400, detail="ids must contain at least one feature id")
    return parts


@router.get("/similarity-matrix", response_model=MatrixResponse)
def get_similarity_matrix(
    ids: str = Query(..., description="Comma-separated feature ids (max 100)"),
    threshold: float = Query(0.0, ge=0.0, le=1.0),
    db=Depends(get_db),  # noqa: B008
) -> MatrixResponse:
    """Score the upper triangle of an N×N similarity matrix over a caller-
    selected feature subset.

    Differs from ``/duplicates`` (which scans the whole catalog for high-score
    pairs): this endpoint takes a specific feature list and returns *every*
    pair above ``threshold`` so the UI can render a heatmap. Diagonal cells
    are not returned — clients render them locally as 1.0.
    """
    feature_ids = _parse_id_list(ids)
    cache_key = f"matrix:{','.join(sorted(feature_ids))}:{threshold}"
    cached = cache_get(cache_key)
    if cached is not None:
        return MatrixResponse(**cached)

    try:
        features, cells = db.compute_similarity_matrix(feature_ids=feature_ids, threshold=threshold)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Unknown feature id(s): {e.args[0]}") from e

    payload = MatrixResponse(
        features=[FeatureBrief(**f) for f in features],
        cells=[MatrixCell(**c) for c in cells],
        threshold=threshold,
        cached_at=None,
    )
    stored = payload.model_dump()
    stored["cached_at"] = datetime.now(timezone.utc).isoformat()
    cache_set(cache_key, stored, ttl=300)
    return payload


@router.get("/similarity-pair", response_model=PairResponse)
def get_similarity_pair(
    a: str = Query(..., description="Feature id"),
    b: str = Query(..., description="Feature id"),
    db=Depends(get_db),  # noqa: B008
) -> PairResponse:
    """Score a single pair and return the per-reason-code breakdown.

    Used by the matrix UI's cell-click panel — small payload, no cache.
    """
    try:
        brief_a, brief_b, score, reasons = db.compute_pair_reasons(a, b)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    except KeyError as e:
        raise HTTPException(status_code=404, detail=f"Unknown feature id(s): {e.args[0]}") from e

    return PairResponse(
        a=FeatureBrief(**brief_a),
        b=FeatureBrief(**brief_b),
        score=score,
        reasons=[DuplicateReason(**r) for r in reasons],
    )


class RecommendRequest(BaseModel):
    use_case: str = Field(..., min_length=3, max_length=500)
    top_k: int = Field(default=10, ge=1, le=50)
    use_llm: bool = True
    exclude_ids: list[str] | None = Field(
        default=None,
        description="Feature ids to drop from results (e.g. members already in a group).",
    )


class FeatureMatch(BaseModel):
    feature: FeatureBrief
    score: float
    reason: str


class RecommendResponse(BaseModel):
    use_case: str
    method: Literal["llm", "tfidf", "embedding"]
    matches: list[FeatureMatch]
    summary: str | None = None


_RECOMMEND_LLM_TIMEOUT_S = 8.0


def _feature_to_brief(feature: Any, doc_ids: set[str]) -> FeatureBrief:
    name = feature.name
    source = name.split(".")[0] if "." in name else ""
    return FeatureBrief(
        id=feature.id,
        name=name,
        dtype=feature.dtype or "",
        source=source,
        has_doc=feature.id in doc_ids,
    )


def _run_tfidf_recommend(
    db: Any, use_case: str, top_k: int, exclude_ids: frozenset[str] = frozenset()
) -> list[FeatureMatch]:
    doc_ids = set(db.get_all_feature_docs().keys())
    # Over-fetch by the exclusion size so we still return up to top_k after filtering.
    fetch_k = top_k + len(exclude_ids) if exclude_ids else top_k
    results = db.recommend_by_text(use_case, top_k=fetch_k)
    matches = [
        FeatureMatch(
            feature=_feature_to_brief(feat, doc_ids),
            score=round(score, 4),
            reason=f"Keyword similarity {score:.2f}",
        )
        for feat, score in results
        if feat.id not in exclude_ids
    ]
    return matches[:top_k]


async def _maybe_llm_recommend(
    db: Any, llm: Any, use_case: str, top_k: int, exclude_ids: frozenset[str] = frozenset()
) -> tuple[list[FeatureMatch] | None, str | None]:
    """Run the LLM discovery path with an 8s timeout.

    Returns ``(matches, summary)`` on success, or ``(None, reason)`` when the
    caller should fall back to TF-IDF. The ``reason`` string describes which
    fallback condition fired so the response's ``summary`` can be specific
    (timeout vs empty result vs error) rather than collapsing into a single
    generic message.
    """
    if llm is None:
        return None, "LLM unavailable, ranked by keyword similarity"
    from ...plugins.discovery import DiscoveryPlugin

    plugin = DiscoveryPlugin()
    try:
        result = await asyncio.wait_for(
            run_in_threadpool(plugin.execute, db, llm, use_case=use_case, max_features=100),
            timeout=_RECOMMEND_LLM_TIMEOUT_S,
        )
    except asyncio.TimeoutError:
        return None, f"LLM timed out after {int(_RECOMMEND_LLM_TIMEOUT_S)}s, ranked by keyword similarity"
    except Exception as exc:  # noqa: BLE001 — caller decides what to do
        return None, f"LLM error ({type(exc).__name__}), ranked by keyword similarity"

    if result.status != "success":
        return None, "LLM returned an error, ranked by keyword similarity"
    existing = result.data.get("existing_features") or []
    if not existing:
        return None, "LLM returned no matches, ranked by keyword similarity"

    doc_ids = set(db.get_all_feature_docs().keys())
    matches: list[FeatureMatch] = []
    # Iterate the full LLM list (not [:top_k]) so excluded entries don't starve the result.
    for entry in existing:
        if len(matches) >= top_k:
            break
        name = entry.get("name") if isinstance(entry, dict) else None
        if not name:
            continue
        feat = db.get_feature_by_name(name)
        if feat is None or feat.id in exclude_ids:
            continue
        score = float(entry.get("relevance", entry.get("score", 0.0)) or 0.0)
        reason = entry.get("reason") or "LLM ranked"
        matches.append(
            FeatureMatch(
                feature=_feature_to_brief(feat, doc_ids),
                score=round(score, 4),
                reason=reason,
            )
        )
    if not matches:
        return None, "LLM returned no usable matches, ranked by keyword similarity"
    summary = result.data.get("summary")
    return matches, summary


@router.post("/recommend", response_model=RecommendResponse)
async def recommend_features(
    body: RecommendRequest = Body(...),  # noqa: B008
    db=Depends(get_db),  # noqa: B008
    llm=Depends(get_llm),  # noqa: B008
) -> RecommendResponse:
    """Rank features for a natural-language use case.

    Server owns the LLM-vs-TF-IDF decision end-to-end. Client sends one
    request and renders whatever ``method`` we return — no retries.
    """
    use_case = body.use_case.strip()
    exclude_ids: frozenset[str] = frozenset(body.exclude_ids or ())
    # Sorted so the cache key is stable across client orderings of the same set.
    exclude_fingerprint = (
        hashlib.sha256(",".join(sorted(exclude_ids)).encode("utf-8")).hexdigest()[:8] if exclude_ids else "0"
    )
    cache_key = (
        f"recommend:{hashlib.sha256(use_case.encode('utf-8')).hexdigest()[:16]}"
        f":{body.top_k}:{body.use_llm}:{exclude_fingerprint}"
    )
    cached = cache_get(cache_key)
    if cached is not None:
        return RecommendResponse(**cached)

    fallback_summary: str
    if body.use_llm:
        matches_opt, reason = await _maybe_llm_recommend(db, llm, use_case, body.top_k, exclude_ids)
        if matches_opt is not None:
            response = RecommendResponse(
                use_case=use_case,
                method="llm",
                matches=matches_opt,
                summary=reason,
            )
            cache_set(cache_key, response.model_dump(), ttl=600)
            return response
        # Helper has already classified the fallback reason (unavailable /
        # timeout / error / no-matches) — propagate it verbatim.
        fallback_summary = reason or "LLM unavailable, ranked by keyword similarity"
    else:
        fallback_summary = "Ranked by keyword similarity (LLM bypassed)"

    matches = await run_in_threadpool(_run_tfidf_recommend, db, use_case, body.top_k, exclude_ids)
    response = RecommendResponse(
        use_case=use_case,
        method="tfidf",
        matches=matches,
        summary=fallback_summary if matches else (fallback_summary or "No close matches in catalog"),
    )
    cache_set(cache_key, response.model_dump(), ttl=600)
    return response
