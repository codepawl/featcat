"""Demo catalog seeding and clearing.

`featcat demo seed` populates a catalog with bundled demo data (sources,
features, pre-canned docs, groups, lineage edges) so operators can take a
screencast or screenshot tour without bringing real data. `featcat demo
clear` removes only data tagged as demo, leaving real catalog content
untouched.

Demo data is identified by these markers (mirroring `featcat lineage seed`):

- features: ``tags`` contains ``'demo'``
- lineage edges: ``detected_method == 'demo'``
- sources: ``description == _DEMO_SOURCE_DESC``
- groups: ``description`` starts with ``_DEMO_GROUP_DESC_PREFIX``
- docs: ``model_used == 'demo'``
"""

from __future__ import annotations

from .fixture import DemoFixture, load_demo_fixture
from .loader import DemoStats, bundled_fixture_path, clear_demo, seed_demo

__all__ = [
    "DemoFixture",
    "DemoStats",
    "bundled_fixture_path",
    "clear_demo",
    "load_demo_fixture",
    "seed_demo",
]
