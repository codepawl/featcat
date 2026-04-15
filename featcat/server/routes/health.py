"""Health and stats endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends

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
    """Catalog overview statistics."""
    return db.get_catalog_stats()


@router.get("/stats/doc-debt")
def doc_debt(db=Depends(get_db)):
    """Documentation debt by owner and source."""
    return db.get_doc_debt()


@router.get("/stats/by-source")
def stats_by_source(db=Depends(get_db)):
    """Per-source stats for dashboard visualization."""
    return db.get_stats_by_source()
