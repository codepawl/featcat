"""Shared test fixtures."""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq
import pytest

from featcat.catalog.db import CatalogDB

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture()
def sample_parquet(tmp_path: Path) -> Path:
    """Create a small sample Parquet file for testing."""
    table = pa.table(
        {
            "user_id": pa.array([1, 2, 3, 4, 5], type=pa.int64()),
            "age": pa.array([25, 30, None, 22, 45], type=pa.int64()),
            "revenue": pa.array([100.5, 200.0, 150.3, None, 300.0], type=pa.float64()),
            "city": pa.array(["HCM", "HN", "DN", "HCM", None], type=pa.string()),
        }
    )
    path = tmp_path / "sample.parquet"
    pq.write_table(table, path)
    return path


@pytest.fixture()
def db(tmp_path: Path) -> CatalogDB:
    """Create a temporary catalog database."""
    db_path = str(tmp_path / "test_catalog.db")
    catalog = CatalogDB(db_path)
    catalog.init_db()
    yield catalog
    catalog.close()
