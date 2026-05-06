"""Admin endpoints — LLM cache, etc."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ..deps import get_settings

router = APIRouter()


@router.get("/cache/stats")
def cache_stats(settings=Depends(get_settings)):  # noqa: B008
    """Return LLM response-cache stats (total / active / expired)."""
    from ...utils.cache import ResponseCache

    cache = ResponseCache(settings.catalog_db_path)
    try:
        return cache.stats()
    finally:
        cache.close()


@router.post("/cache/clear")
def cache_clear(settings=Depends(get_settings)):  # noqa: B008
    """Drop all entries from the LLM response cache."""
    from ...utils.cache import ResponseCache

    cache = ResponseCache(settings.catalog_db_path)
    try:
        deleted = cache.clear()
    finally:
        cache.close()
    return {"deleted": deleted}


@router.post("/cache/clear-expired")
def cache_clear_expired(settings=Depends(get_settings)):  # noqa: B008
    """Drop expired entries from the LLM response cache."""
    from ...utils.cache import ResponseCache

    cache = ResponseCache(settings.catalog_db_path)
    try:
        deleted = cache.clear_expired()
    finally:
        cache.close()
    return {"deleted": deleted}
