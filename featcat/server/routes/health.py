"""Health and stats endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..cache import cache_get, cache_set
from ..deps import get_db, get_llm, get_settings

router = APIRouter()


@router.get("/health")
def health(db=Depends(get_db), llm=Depends(get_llm), settings=Depends(get_settings)):
    """Health check: DB, LLM reachability, and basic stats."""
    result = {"status": "ok", "db": True, "llm": False}

    try:
        stats = db.get_catalog_stats()
        result["stats"] = stats
    except Exception:
        result["db"] = False
        result["status"] = "degraded"

    if llm is not None:
        import contextlib

        with contextlib.suppress(Exception):
            result["llm"] = llm.health_check()

    result["model"] = settings.llm_model
    return result


@router.get("/stats")
def stats(db=Depends(get_db)):
    """Catalog overview statistics. Cached for 600s — invalidated on writes that
    touch the source/feature/doc tables (see routes/sources.py et al)."""
    cached = cache_get("dashboard:stats")
    if cached is not None:
        return cached
    payload = db.get_catalog_stats()
    cache_set("dashboard:stats", payload)
    return payload


@router.get("/stats/doc-debt")
def doc_debt(db=Depends(get_db)):
    """Documentation debt by owner and source. Cached for 600s."""
    cached = cache_get("dashboard:doc-debt")
    if cached is not None:
        return cached
    payload = db.get_doc_debt()
    cache_set("dashboard:doc-debt", payload)
    return payload


@router.get("/stats/by-source")
def stats_by_source(db=Depends(get_db)):
    """Per-source stats for dashboard visualization. Cached for 600s."""
    cached = cache_get("dashboard:by-source")
    if cached is not None:
        return cached
    payload = db.get_stats_by_source()
    cache_set("dashboard:by-source", payload)
    return payload
