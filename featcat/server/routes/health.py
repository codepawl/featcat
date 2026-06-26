"""Health and stats endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from ... import __version__
from ..cache import cache_get, cache_set
from ..deps import get_db, get_llm, get_settings

router = APIRouter()


@router.get("/health")
def health(db=Depends(get_db), llm=Depends(get_llm), settings=Depends(get_settings)):
    """Health check: DB, LLM reachability, basic stats, and the cheap-subset
    structured checks shared with ``featcat doctor db``.

    The existing ``{status, db, llm, stats, model}`` shape is preserved so
    the web UI and any external monitors don't break; the additional
    ``checks`` field is purely additive.
    """
    result = {"status": "ok", "version": __version__, "db": True, "llm": False}

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

    # Structured checks. Keep the timeout tight so /health stays cheap.
    import contextlib as _ctx

    with _ctx.suppress(Exception):
        from featcat.diagnostics import run_group

        report = run_group("db", timeout_per_check=0.5, settings=settings)
        result["checks"] = [c.model_dump(mode="json") for c in report.checks]

    return result


@router.get("/ready")
def ready(db=Depends(get_db), settings=Depends(get_settings)):
    """Readiness check for orchestrators.

    Unlike /health, this endpoint is intentionally strict: it returns 503 when
    the backing feature-store database cannot answer a cheap metadata query.
    LLM and scheduler state do not block readiness because they are optional
    MVP capabilities and report through /health.
    """
    payload = {
        "status": "ready",
        "version": __version__,
        "db_backend": settings.db_backend,
        "db": True,
    }
    try:
        db.get_catalog_stats()
    except Exception as exc:
        payload.update({"status": "not_ready", "db": False, "detail": str(exc)})
        return JSONResponse(payload, status_code=503)
    return payload


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
