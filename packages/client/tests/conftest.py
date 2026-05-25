"""Shared fixtures for featcat-client tests."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

CLIENT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(CLIENT_SRC) not in sys.path:
    sys.path.insert(0, str(CLIENT_SRC))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@pytest.fixture
def feature_payload() -> dict[str, Any]:
    """A typical feature response from ``GET /api/features/by-name``."""
    return {
        "id": "f-uuid-1",
        "name": "user_behavior.session_count_30d",
        "data_source_id": "src-uuid-1",
        "column_name": "session_count_30d",
        "dtype": "int64",
        "description": "30-day session count",
        "tags": ["churn", "behavior"],
        "owner": "data-team",
        "stats": {"mean": 12.4, "p99": 245},
        "definition": None,
        "definition_type": None,
        "generation_hints": None,
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        # Server-side enrichments that should be stripped by ``extra="ignore"``:
        "has_doc": True,
        "health_score": 85,
        "health_grade": "B",
    }


@pytest.fixture
def source_payload() -> dict[str, Any]:
    return {
        "id": "src-uuid-1",
        "name": "user_behavior",
        "path": "/data/user_behavior.parquet",
        "storage_type": "local",
        "format": "parquet",
        "description": "",
        "entity_key": "user_id",
        "event_timestamp_column": "event_ts",
        "created_timestamp_column": "created_at",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
    }


@pytest.fixture
def group_payload(feature_payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": "grp-uuid-1",
        "name": "churn_v2",
        "description": "Churn model v2 features",
        "project": "ml-team",
        "owner": "ml-team",
        "created_at": _now_iso(),
        "updated_at": _now_iso(),
        "members": [feature_payload],
    }
