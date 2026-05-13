"""Full-text search endpoints (T2.2a).

Postgres uses tsvector + GIN index for ranked search; sqlite falls back to
in-process token scanning. Both expose the same response shape.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..deps import get_db

router = APIRouter()


@router.get("")
def search(
    q: str = Query(..., min_length=1, description="Free-text query"),
    source: str | None = Query(None),
    tag: str | None = Query(None),
    dtype: str | None = Query(None),
    has_doc: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db=Depends(get_db),  # noqa: B008
) -> list[dict]:
    """Ranked search across features.

    Postgres path uses ``plainto_tsquery('simple', q) @@ search_vector`` +
    ``ts_rank``; sqlite falls back to per-token scanning. Result shape:
    ``[{id, name, dtype, source, rank}]`` sorted by rank descending.
    """
    return db.full_text_search(q, source=source, tag=tag, dtype=dtype, has_doc=has_doc, limit=limit)


@router.get("/facets")
def search_facets(
    q: str | None = Query(None),
    source: str | None = Query(None),
    tag: str | None = Query(None),
    dtype: str | None = Query(None),
    has_doc: bool | None = Query(None),
    db=Depends(get_db),  # noqa: B008
) -> dict:
    """Facet counts for the search-result sidebar. Each facet is computed
    against the same filter set as the search itself, so applying a filter
    narrows the other facet counts."""
    return db.search_facets(q, source=source, tag=tag, dtype=dtype, has_doc=has_doc)
