"""Lineage endpoints (T1.1).

Currently exposes impact analysis only — "if this source[.column] changes,
which features break?" CRUD on individual lineage records lives under
``/api/features/by-name/lineage`` so it's grouped with other feature ops;
this router is for catalog-wide queries.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import text

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


@router.get("/full")
def lineage_full(db=Depends(get_db)) -> dict:  # noqa: B008
    """Return the catalog-wide feature→feature lineage graph (T1.1c).

    Shape::

        {
          "nodes": [{"name", "source", "dtype", "owner"}, ...],
          "edges": [{"child", "parent", "transform", "detected_method"}, ...]
        }

    Empty catalogs (or catalogs with no recorded lineage) return
    ``{"nodes": [], "edges": []}``. Source-column → feature edges are
    excluded — this endpoint feeds a pure feature-to-feature flowchart;
    raw column dependencies are surfaced via ``/api/lineage/impact``.
    """
    # Routes don't normally hit raw SQL, but the lineage table isn't on the
    # CatalogBackend interface in this shape (the existing get_lineage_graph
    # returns drift/has-doc enrichment we don't need here, and it doesn't
    # surface detected_method). Single SELECT keeps this lean enough that
    # adding a backend method is overkill.
    with db.session() as s:
        edges_rows = (
            s.execute(
                text(
                    "SELECT fc.name AS child_name, fp.name AS parent_name, "
                    "       fl.transform, fl.detected_method "
                    "FROM feature_lineage fl "
                    "JOIN features fc ON fl.child_feature_id = fc.id "
                    "JOIN features fp ON fl.parent_feature_id = fp.id "
                    "WHERE fl.parent_type = 'feature'"
                )
            )
            .mappings()
            .all()
        )

        if not edges_rows:
            return {"nodes": [], "edges": []}

        edges: list[dict] = []
        names: set[str] = set()
        for r in edges_rows:
            edges.append(
                {
                    "child": r["child_name"],
                    "parent": r["parent_name"],
                    "transform": r["transform"] or "",
                    "detected_method": r["detected_method"] or "manual",
                }
            )
            names.add(r["child_name"])
            names.add(r["parent_name"])

        from sqlalchemy import bindparam

        feat_rows = (
            s.execute(
                text("SELECT name, dtype, owner FROM features WHERE name IN :names").bindparams(
                    bindparam("names", expanding=True)
                ),
                {"names": list(names)},
            )
            .mappings()
            .all()
        )

    nodes: list[dict] = []
    for r in feat_rows:
        name = r["name"]
        nodes.append(
            {
                "name": name,
                "source": name.split(".")[0] if "." in name else "",
                "dtype": r["dtype"] or "",
                "owner": r["owner"] or "",
            }
        )
    return {"nodes": nodes, "edges": edges}
