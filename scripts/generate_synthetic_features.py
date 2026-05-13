#!/usr/bin/env python
"""Seed a featcat catalog with synthetic data for performance testing.

Inserts ``--sources`` data sources and roughly ``--features`` features evenly
distributed across them. Uses ``LocalBackend`` directly so it works against
either sqlite or postgres (controlled by ``FEATCAT_DB_BACKEND`` env).

Usage:
    python scripts/generate_synthetic_features.py --sources 20 --features 5000
    python scripts/generate_synthetic_features.py --sources 20 --features 5000 --reset

``--reset`` truncates the catalog tables before seeding so successive runs
don't compound.
"""

from __future__ import annotations

import argparse
import random
import sys

from sqlalchemy import text

from featcat.catalog.local import LocalBackend
from featcat.catalog.models import DataSource, Feature

DTYPES = ["int64", "float64", "string", "bool", "datetime64[ns]", "categorical"]
TAG_VOCAB = [
    "churn",
    "behavior",
    "session",
    "device",
    "geo",
    "pii",
    "critical",
    "experimental",
    "deprecated",
    "high-cardinality",
    "engagement",
    "monetization",
    "fraud",
    "ml-ready",
    "raw",
]
OWNERS = ["data-team", "ml-team", "growth", "fraud", "platform", ""]


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--sources", type=int, default=20)
    p.add_argument("--features", type=int, default=5000)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("--reset", action="store_true", help="DELETE existing catalog rows first")
    p.add_argument("--db-path", default="catalog.db", help="sqlite path (ignored in postgres mode)")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)

    db = LocalBackend(args.db_path)
    db.init_db()
    if args.reset:
        with db.session() as s:
            for t in (
                "action_items",
                "feature_lineage",
                "monitoring_checks",
                "usage_log",
                "feature_group_members",
                "feature_versions",
                "feature_docs",
                "monitoring_baselines",
                "features",
                "feature_groups",
                "data_sources",
            ):
                s.execute(text(f"DELETE FROM {t}"))
            s.commit()

    sources: list[DataSource] = []
    for i in range(args.sources):
        src = db.add_source(
            DataSource(
                name=f"synth_source_{i:02d}",
                path=f"/synthetic/source_{i:02d}.parquet",
                description=f"Synthetic source #{i}",
            )
        )
        sources.append(src)

    per_source = args.features // args.sources
    for src in sources:
        for j in range(per_source):
            tags = rng.sample(TAG_VOCAB, k=rng.randint(0, 4))
            db.upsert_feature(
                Feature(
                    name=f"{src.name}.col_{j:04d}",
                    data_source_id=src.id,
                    column_name=f"col_{j:04d}",
                    dtype=rng.choice(DTYPES),
                    tags=tags,
                    owner=rng.choice(OWNERS),
                    stats={
                        "mean": round(rng.gauss(0, 10), 3),
                        "std": round(abs(rng.gauss(1, 0.5)), 3),
                        "null_ratio": round(rng.uniform(0, 0.2), 3),
                    },
                )
            )

    total = db.count_features()
    print(f"Seeded {len(sources)} sources, {total} features into {args.db_path}")
    db.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
