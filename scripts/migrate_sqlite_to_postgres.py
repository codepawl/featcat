#!/usr/bin/env python
"""Migrate the featcat catalog from SQLite to PostgreSQL.

Usage:
    python scripts/migrate_sqlite_to_postgres.py \
        --source /path/to/catalog.db \
        --target postgresql+psycopg2://featcat:pw@host:5432/featcat \
        [--sample-size 10]

Workflow:
1. ``Base.metadata.create_all`` on the target so the destination schema exists.
   (For first-time setup; in production the operator typically runs
   ``alembic upgrade head`` against postgres before invoking this script. Both
   produce the same schema.)
2. For each table, in FK-safe order:
   a. Stream rows from SQLite via SQLAlchemy Core ``select(table)``.
   b. Bulk insert into postgres in a single transaction.
   c. Verify row count matches.
   d. Spot-check ``--sample-size`` random rows: fetch by primary key from both
      sides and deep-compare every column. JSON-typed columns are decoded
      before comparison so semantically-equal payloads with different
      whitespace/key-ordering still match.
3. Abort with non-zero exit on any count or content mismatch.

Tables migrated (13): data_sources, features, feature_docs,
monitoring_baselines, job_schedules, job_logs, feature_versions,
feature_groups, feature_group_members, usage_log, monitoring_checks,
feature_lineage, action_items.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import Engine, Table, and_, create_engine, func, insert, select

from featcat.db.models import Base

if TYPE_CHECKING:
    from sqlalchemy.engine import Row

# Columns that store JSON-as-text. Compared via json.loads on both sides so that
# whitespace/ordering differences don't trigger spurious mismatches.
JSON_COLUMNS: dict[str, list[str]] = {
    "features": ["tags", "stats"],
    "feature_versions": ["snapshot", "previous_value", "new_value"],
    "monitoring_baselines": ["baseline_stats"],
    "feature_docs": ["context_features"],
    "monitoring_checks": ["llm_analysis_json"],
    "action_items": ["context_json"],
    "job_logs": ["result_summary"],
}


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--source", required=True, help="Source SQLite database file path")
    p.add_argument("--target", required=True, help="Target Postgres URL (postgresql+psycopg2://...)")
    p.add_argument("--sample-size", type=int, default=10, help="Rows to spot-check per table (default: 10)")
    p.add_argument("--seed", type=int, default=42, help="Random seed for reproducible sampling")
    p.add_argument("--dry-run", action="store_true", help="Read source and verify schema only; no writes")
    return p.parse_args()


def _to_utc_naive(dt: datetime) -> datetime:
    """Normalize a datetime to UTC-naive for comparison.

    SQLite has no native timezone storage: SQLAlchemy's SQLite dialect strips
    tzinfo on TIMESTAMP roundtrip even with ``timezone=True``. PostgreSQL's
    ``timestamptz`` preserves tz natively. To make the verification meaningful
    in both directions (sqlite→postgres in production, sqlite→sqlite in CI),
    we compare semantic instants rather than strict-equal datetimes.
    """
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _values_equal(col_name: str, table_name: str, src_v: Any, dst_v: Any) -> bool:
    """Semantic-equal compare with JSON-decoding and tz-tolerant datetime."""
    if col_name in JSON_COLUMNS.get(table_name, []):
        # Both sides may be None or empty string when the JSON column is unset.
        src_p = json.loads(src_v) if isinstance(src_v, str) and src_v else src_v
        dst_p = json.loads(dst_v) if isinstance(dst_v, str) and dst_v else dst_v
        return src_p == dst_p
    if isinstance(src_v, datetime) and isinstance(dst_v, datetime):
        return _to_utc_naive(src_v) == _to_utc_naive(dst_v)
    return src_v == dst_v


def _spot_check(table: Table, src: Engine, dst: Engine, sample_size: int, rng: random.Random) -> list[str]:
    """Return list of mismatch messages (empty = success)."""
    pk_cols = list(table.primary_key.columns)
    if not pk_cols:
        return [f"{table.name}: no primary key — cannot spot-check by PK"]

    with src.connect() as src_conn:
        all_pks = src_conn.execute(select(*pk_cols)).all()
    if not all_pks:
        return []
    sample = rng.sample(all_pks, min(sample_size, len(all_pks)))

    mismatches: list[str] = []
    for pk_tuple in sample:
        where = and_(*[col == val for col, val in zip(pk_cols, pk_tuple, strict=True)])
        with src.connect() as src_conn:
            src_row: Row | None = src_conn.execute(select(table).where(where)).first()
        with dst.connect() as dst_conn:
            dst_row: Row | None = dst_conn.execute(select(table).where(where)).first()
        if src_row is None or dst_row is None:
            mismatches.append(f"{table.name}: row missing on {'dst' if dst_row is None else 'src'} for pk={pk_tuple}")
            continue
        src_map = src_row._mapping
        dst_map = dst_row._mapping
        for c in table.columns:
            if not _values_equal(c.name, table.name, src_map[c.name], dst_map[c.name]):
                mismatches.append(
                    f"{table.name}.{c.name} mismatch for pk={pk_tuple}: "
                    f"src={src_map[c.name]!r}, dst={dst_map[c.name]!r}"
                )
    return mismatches


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)

    src = create_engine(f"sqlite:///{args.source}", future=True)
    dst = create_engine(args.target, future=True)

    print(f"Source: sqlite:///{args.source}")
    print(f"Target: {args.target}")
    print(f"Sample size: {args.sample_size} (seed={args.seed}){' [dry-run]' if args.dry_run else ''}")
    print()

    # Ensure target schema exists. No-op if Alembic already brought it up.
    if not args.dry_run:
        Base.metadata.create_all(dst, checkfirst=True)

    summary: list[tuple[str, int, int]] = []
    all_mismatches: list[str] = []

    for table in Base.metadata.sorted_tables:
        # 1. Read all source rows.
        with src.connect() as src_conn:
            src_rows = src_conn.execute(select(table)).mappings().all()
        src_count = len(src_rows)

        # 2. Bulk insert to dst.
        if src_count > 0 and not args.dry_run:
            with dst.begin() as dst_conn:
                dst_conn.execute(insert(table), [dict(r) for r in src_rows])

        # 3. Verify row count.
        with dst.connect() as dst_conn:
            dst_count = dst_conn.execute(select(func.count()).select_from(table)).scalar() or 0

        summary.append((table.name, src_count, dst_count))

        if not args.dry_run and src_count != dst_count:
            all_mismatches.append(f"{table.name}: row count mismatch — src={src_count}, dst={dst_count}")
            continue

        # 4. Content spot-check.
        if not args.dry_run and src_count > 0:
            all_mismatches.extend(_spot_check(table, src, dst, args.sample_size, rng))

    # Summary table.
    print(f"{'Table':<30} {'Source':>10} {'Target':>10}")
    print("-" * 52)
    for name, s, d in summary:
        marker = "" if s == d else "  ❌"
        print(f"{name:<30} {s:>10} {d:>10}{marker}")
    print()

    if all_mismatches:
        print(f"FAILED — {len(all_mismatches)} issue(s):", file=sys.stderr)
        for m in all_mismatches:
            print(f"  - {m}", file=sys.stderr)
        return 1

    print(f"OK — {len(summary)} tables migrated and verified.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
