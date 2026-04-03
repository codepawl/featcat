"""Import initial feature sets from the DS team.

Idempotent: re-running will update existing features rather than duplicate them.

Usage:
    python scripts/import_initial.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from featcat.catalog.db import CatalogDB
from featcat.catalog.models import DataSource, Feature
from featcat.catalog.scanner import scan_source

# --- Configuration ---

OWNER = "ds-team"

SOURCES = [
    {
        "name": "device_performance",
        "path": "/data/features/device_performance.parquet",
        "description": "Device performance metrics collected from network devices",
    },
    {
        "name": "user_behavior_30d",
        "path": "/data/features/user_behavior_30d.parquet",
        "description": "User behavior aggregated over 30-day rolling windows",
    },
]

# Tag mapping: column_name -> list of tags
TAG_RULES: dict[str, list[str]] = {
    # device_performance columns
    "device_id": ["device", "identifier"],
    "cpu_usage": ["device", "performance", "infra"],
    "memory_usage": ["device", "performance", "infra"],
    "latency_ms": ["device", "performance", "network"],
    "error_count": ["device", "reliability", "alert"],
    "region": ["device", "geo"],
    # user_behavior_30d columns
    "user_id": ["user", "identifier"],
    "session_count": ["user", "behavior", "30d"],
    "data_usage_gb": ["user", "behavior", "usage", "30d"],
    "complaint_count": ["user", "behavior", "churn", "30d"],
    "avg_session_duration": ["user", "behavior", "engagement", "30d"],
    "churn_label": ["user", "target", "churn"],
    # common
    "timestamp": ["temporal"],
}


def get_tags(column_name: str) -> list[str]:
    """Look up tags for a column name, with a sensible default."""
    return TAG_RULES.get(column_name, ["untagged"])


def main() -> None:
    db = CatalogDB("catalog.db")
    db.init_db()

    for src_cfg in SOURCES:
        name = src_cfg["name"]
        path = src_cfg["path"]

        # Check if source already exists
        existing = db.get_source_by_name(name)
        if existing:
            print(f"Source '{name}' already registered, skipping add.")
            source = existing
        else:
            source = DataSource(
                name=name,
                path=path,
                description=src_cfg.get("description", ""),
            )
            db.add_source(source)
            print(f"Registered source: {name} -> {path}")

        # Scan and register features
        print(f"Scanning: {path}")
        try:
            columns = scan_source(path)
        except FileNotFoundError:
            print(f"  WARNING: Path not found: {path}. Skipping scan.")
            print("  (Update the path in this script to match your actual data location)")
            continue

        for col in columns:
            feature_name = f"{name}.{col.column_name}"
            tags = get_tags(col.column_name)
            feature = Feature(
                name=feature_name,
                data_source_id=source.id,
                column_name=col.column_name,
                dtype=col.dtype,
                stats=col.stats,
                tags=tags,
                owner=OWNER,
            )
            db.upsert_feature(feature)
            print(f"  Feature: {feature_name} ({col.dtype}) tags={tags}")

        print(f"  Done: {len(columns)} features from '{name}'")

    db.close()
    print("\nImport complete. Verify with:")
    print("  featcat feature list")
    print("  featcat feature info device_performance.cpu_usage")


if __name__ == "__main__":
    main()
