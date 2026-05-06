"""Lineage endpoints (T1.1).

Currently exposes impact analysis only — "if this source[.column] changes,
which features break?" CRUD on individual lineage records lives under
``/api/features/by-name/lineage`` so it's grouped with other feature ops;
this router is for catalog-wide queries.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ..deps import get_db

router = APIRouter()


@router.get("/impact")
def lineage_impact(
    source: str = Query(..., description="Source name (e.g. 'user_behavior')"),
    column: str | None = Query(None, description="Optional column on the source"),
    depth: int = Query(5, ge=1, le=20, description="Max BFS depth through feature→feature edges"),
    db=Depends(get_db),  # noqa: B008
) -> list[dict]:
    """Return all features impacted (directly or transitively) by a source[.column].

    Each item: ``{name, dtype, depth, via}``. ``depth=1`` is a direct child
    of the source-column edge; deeper rows are reached via subsequent
    feature→feature edges. ``via`` carries the immediate parent name to help
    a UI render the propagation chain.
    """
    if not source.strip():
        raise HTTPException(status_code=400, detail="source is required")
    return db.get_impact(source_name=source, column=column, max_depth=depth)
