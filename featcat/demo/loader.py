"""Seed and clear demo data on a LocalBackend catalog.

Single owner of the demo-marker contract: features get ``tags=['demo']``,
lineage edges get ``detected_method='demo'``, sources get
``description=_DEMO_SOURCE_DESC``, groups get a description prefix, and
docs get ``model_used='demo'``. The CLI ``demo clear`` command relies on
those markers to remove only demo data.

Operates against ``LocalBackend`` rather than the abstract ``CatalogBackend``
because the clear path needs SQLAlchemy sessions and bulk deletes that the
HTTP-based ``RemoteBackend`` doesn't expose. The CLI demo commands are
local-only — running them against a remote server is a misconfiguration.
"""

from __future__ import annotations

from dataclasses import dataclass
from importlib.resources import as_file, files
from pathlib import Path
from typing import TYPE_CHECKING

from sqlalchemy import text

from ..catalog.models import DataSource, Feature, FeatureGroup

if TYPE_CHECKING:
    from ..catalog.local import LocalBackend
    from .fixture import DemoFixture

DEMO_FEATURE_TAG = "demo"
DEMO_DETECTED_METHOD = "demo"
_DEMO_SOURCE_DESC = "Auto-created by `featcat demo seed` for demo data"
_DEMO_GROUP_DESC_PREFIX = "[demo] "
_DEMO_DOC_MODEL = "demo"
_DEMO_FEATURE_DESC = "Demo feature (auto-created from demo fixture)"


@dataclass
class DemoStats:
    """Tally of seed/clear operations for the CLI to render."""

    sources_created: int = 0
    features_created: int = 0
    docs_created: int = 0
    groups_created: int = 0
    lineage_edges_created: int = 0
    sources_removed: int = 0
    features_removed: int = 0
    docs_removed: int = 0
    groups_removed: int = 0
    lineage_edges_removed: int = 0


def bundled_fixture_path() -> Path:
    """Return the path to the bundled ``demo-catalog.json``.

    Uses ``importlib.resources`` so the file is reachable both from an
    editable install and a wheel install.
    """
    ref = files("featcat.demo") / "data" / "demo-catalog.json"
    with as_file(ref) as p:
        return Path(p)


def seed_demo(db: LocalBackend, fixture: DemoFixture) -> DemoStats:
    """Insert every item in ``fixture`` into ``db``.

    Idempotent: items already present (by natural key — source name,
    feature name, group name, lineage edge identity) are skipped silently.
    """
    stats = DemoStats()

    # Sources
    for s in fixture.sources:
        if db.get_source_by_name(s.name) is None:
            db.add_source(DataSource(name=s.name, path=s.path, description=_DEMO_SOURCE_DESC))
            stats.sources_created += 1

    # Features
    for f in fixture.features:
        if db.get_feature_by_name(f.name) is not None:
            continue
        src_name = f.name.split(".", 1)[0]
        source = db.get_source_by_name(src_name)
        if source is None:
            # Defensive — fixture validator should already prevent this.
            continue
        tags = sorted({DEMO_FEATURE_TAG, *f.extra_tags})
        db.upsert_feature(
            Feature(
                name=f.name,
                data_source_id=source.id,
                column_name=f.column_name,
                dtype=f.dtype,
                description=f.description or _DEMO_FEATURE_DESC,
                tags=tags,
                owner=f.owner or "",
            )
        )
        stats.features_created += 1

    # Docs — only for features that now exist.
    for d in fixture.docs:
        feature = db.get_feature_by_name(d.feature_name)
        if feature is None:
            continue
        if _has_demo_doc(db, feature.id):
            continue
        payload = {
            "short_description": d.short_description,
            "long_description": d.long_description,
            "expected_range": d.expected_range,
            "potential_issues": d.potential_issues,
            "suggested_tags": d.suggested_tags,
        }
        db.save_feature_doc(feature.id, payload, model_used=_DEMO_DOC_MODEL)
        stats.docs_created += 1

    # Groups
    for g in fixture.groups:
        if db.get_group_by_name(g.name) is not None:
            continue
        group = db.create_group(
            FeatureGroup(
                name=g.name,
                description=f"{_DEMO_GROUP_DESC_PREFIX}{g.description or ''}",
            )
        )
        feature_ids = []
        for fname in g.feature_names:
            feature = db.get_feature_by_name(fname)
            if feature is not None:
                feature_ids.append(feature.id)
        if feature_ids:
            db.add_group_members(group.id, feature_ids)
        stats.groups_created += 1

    # Lineage edges
    for e in fixture.lineage_edges:
        child = db.get_feature_by_name(e.child)
        parent = db.get_feature_by_name(e.parent)
        if child is None or parent is None:
            continue
        if _lineage_edge_exists(db, child.id, parent.id):
            continue
        db.add_lineage(
            child_feature_id=child.id,
            parent_feature_id=parent.id,
            transform=e.transformation,
            detected_method=DEMO_DETECTED_METHOD,
        )
        stats.lineage_edges_created += 1

    return stats


def clear_demo(db: LocalBackend) -> DemoStats:
    """Remove every row tagged as demo. Real data is left intact."""
    stats = DemoStats()

    with db.session() as s:
        result = s.execute(
            text("DELETE FROM feature_lineage WHERE detected_method = :m"),
            {"m": DEMO_DETECTED_METHOD},
        )
        s.commit()
        stats.lineage_edges_removed = int(result.rowcount or 0)  # type: ignore[attr-defined]

    with db.session() as s:
        result = s.execute(
            text("DELETE FROM feature_docs WHERE model_used = :m"),
            {"m": _DEMO_DOC_MODEL},
        )
        s.commit()
        stats.docs_removed = int(result.rowcount or 0)  # type: ignore[attr-defined]

    with db.session() as s:
        # Match prefix; cascade removes group_members rows.
        result = s.execute(
            text("DELETE FROM feature_groups WHERE description LIKE :p"),
            {"p": f"{_DEMO_GROUP_DESC_PREFIX}%"},
        )
        s.commit()
        stats.groups_removed = int(result.rowcount or 0)  # type: ignore[attr-defined]

    demo_features = db.list_features(tag=DEMO_FEATURE_TAG)
    if demo_features:
        stats.features_removed = db.bulk_delete_features([f.id for f in demo_features])

    # Sources are removed only if they have no remaining features.
    for src in list(db.list_sources()):
        if src.description == _DEMO_SOURCE_DESC and not db.list_features(source_name=src.name):
            db.delete_source(src.name)
            stats.sources_removed += 1

    return stats


def _has_demo_doc(db: LocalBackend, feature_id: str) -> bool:
    with db.session() as s:
        row = s.execute(
            text("SELECT 1 FROM feature_docs WHERE feature_id = :fid AND model_used = :m LIMIT 1"),
            {"fid": feature_id, "m": _DEMO_DOC_MODEL},
        ).first()
    return row is not None


def _lineage_edge_exists(db: LocalBackend, child_id: str, parent_id: str) -> bool:
    with db.session() as s:
        row = s.execute(
            text(
                "SELECT 1 FROM feature_lineage "
                "WHERE child_feature_id = :c AND parent_feature_id = :p "
                "  AND parent_type = 'feature' LIMIT 1"
            ),
            {"c": child_id, "p": parent_id},
        ).first()
    return row is not None


__all__ = [
    "DEMO_DETECTED_METHOD",
    "DEMO_FEATURE_TAG",
    "DemoStats",
    "bundled_fixture_path",
    "clear_demo",
    "seed_demo",
]
