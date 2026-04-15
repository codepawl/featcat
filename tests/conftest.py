"""Shared test fixtures."""

from __future__ import annotations

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
def sample_parquet_dir(tmp_path: Path) -> Path:
    """Create a directory with multiple Parquet files for bulk scan testing."""
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    # File 1
    t1 = pa.table({"user_id": pa.array([1, 2, 3]), "score": pa.array([0.5, 0.8, 0.3])})
    pq.write_table(t1, data_dir / "users.parquet")
    # File 2
    t2 = pa.table({"item_id": pa.array([10, 20]), "price": pa.array([9.99, 19.99])})
    pq.write_table(t2, data_dir / "items.parquet")
    # Nested file
    sub = data_dir / "sub"
    sub.mkdir()
    t3 = pa.table({"event": pa.array(["click", "view"]), "ts": pa.array([1000, 2000])})
    pq.write_table(t3, sub / "events.parquet")
    return data_dir


@pytest.fixture()
def db(tmp_path: Path) -> CatalogDB:
    """Create a temporary catalog database."""
    db_path = str(tmp_path / "test_catalog.db")
    catalog = CatalogDB(db_path)
    catalog.init_db()
    yield catalog
    catalog.close()
