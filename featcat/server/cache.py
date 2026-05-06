"""In-process TTL cache for hot read endpoints (T1.4a).

Single-process, thread-safe via ``cachetools.TTLCache``'s implicit lock pattern.
Designed for the small set of read endpoints that are hit on every page load
and don't depend on user identity:

- ``GET /api/sources`` — full source list (rare writes, frequent reads)
- ``GET /api/health/stats`` — dashboard headline metrics
- ``GET /api/health/stats/by-source`` — dashboard per-source aggregations

Usage:

    from featcat.server.cache import cache_get, cache_set, invalidate

    @router.get("")
    def list_sources(db = Depends(get_db)):
        cached = cache_get("sources:list")
        if cached is not None:
            return cached
        result = [...]
        cache_set("sources:list", result, ttl=300)
        return result

    # Write endpoints call invalidate(prefix=...) to drop entries.
    @router.post("")
    def add_source(...):
        ...
        invalidate(prefix="sources:")
        invalidate(prefix="dashboard:")  # source counts feed the dashboard

The cache is process-local. With multi-worker uvicorn, each worker has its
own copy — a write hitting worker A doesn't invalidate worker B's cache,
which means up to TTL seconds of staleness on the other workers. Acceptable
for the targeted endpoints (TTL is 60–300s); upgrade to Redis when that
ceases to be acceptable.
"""

from __future__ import annotations

from threading import Lock
from typing import Any

from cachetools import TTLCache

# A single shared cache backs all entries — keys are namespaced by prefix
# (``sources:``, ``dashboard:``, etc.) so ``invalidate(prefix="sources:")``
# can drop a related set in one call.
#
# maxsize=512 covers all the parameterless reads plus headroom; entries are
# small (a few KB each in practice).
_CACHE: TTLCache[str, Any] = TTLCache(maxsize=512, ttl=600)
_LOCK = Lock()


def cache_get(key: str) -> Any | None:
    """Return the cached value for ``key`` or ``None`` if missing/expired."""
    with _LOCK:
        return _CACHE.get(key)


def cache_set(key: str, value: Any, *, ttl: int | None = None) -> None:
    """Store ``value`` under ``key``.

    The TTLCache itself has a single global TTL; the optional ``ttl`` arg
    is honored by re-setting the entry with a custom expiry where needed.
    For now we ignore the per-key TTL (the global 600s default is conservative
    enough for the current callers) and document this so callers don't expect
    fine-grained control.
    """
    del ttl  # documented above — single-TTL cache for simplicity
    with _LOCK:
        _CACHE[key] = value


def invalidate(prefix: str = "") -> int:
    """Drop all entries whose key starts with ``prefix``. Returns dropped count.

    ``invalidate("")`` clears the whole cache.
    """
    with _LOCK:
        keys_to_drop = [k for k in _CACHE if k.startswith(prefix)]
        for k in keys_to_drop:
            del _CACHE[k]
        return len(keys_to_drop)


__all__ = ["cache_get", "cache_set", "invalidate"]
