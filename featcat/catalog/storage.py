"""Storage backends for reading metadata from local or S3 paths."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import pyarrow as pa
import pyarrow.parquet as pq


# ---------------------------------------------------------------------------
# Local storage
# ---------------------------------------------------------------------------

def resolve_parquet_path(path: str) -> str:
    """Validate and resolve a data source path.

    For local paths, checks existence. For S3 URIs, returns as-is.
    """
    if path.startswith("s3://"):
        return path
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    return str(p)


def read_parquet_schema(path: str) -> pa.Schema:
    """Read only the schema from a Parquet file (no data loaded)."""
    if path.startswith("s3://"):
        return _s3_read_schema(path)
    pf = pq.ParquetFile(path)
    return pf.schema_arrow


def read_parquet_sample(path: str, n_rows: int = 10_000) -> pa.Table:
    """Read the first n_rows from a Parquet file for stats computation."""
    if path.startswith("s3://"):
        return _s3_read_sample(path, n_rows)
    pf = pq.ParquetFile(path)
    batches = []
    total = 0
    for batch in pf.iter_batches(batch_size=min(n_rows, 10_000)):
        remaining = n_rows - total
        if remaining <= 0:
            break
        if batch.num_rows > remaining:
            batch = batch.slice(0, remaining)
        batches.append(batch)
        total += batch.num_rows
    if not batches:
        return pa.table({})
    return pa.Table.from_batches(batches, schema=pf.schema_arrow)


# ---------------------------------------------------------------------------
# S3 storage
# ---------------------------------------------------------------------------

def _get_s3_filesystem() -> "pyarrow.fs.S3FileSystem":
    """Create a PyArrow S3FileSystem from featcat settings."""
    from ..config import load_settings

    settings = load_settings()

    kwargs: dict = {}
    if settings.s3_endpoint_url:
        kwargs["endpoint_override"] = settings.s3_endpoint_url
    if settings.s3_access_key and settings.s3_secret_key:
        kwargs["access_key"] = settings.s3_access_key
        kwargs["secret_key"] = settings.s3_secret_key
    if settings.s3_region:
        kwargs["region"] = settings.s3_region

    # For MinIO/self-hosted: disable SSL if http://
    if settings.s3_endpoint_url and settings.s3_endpoint_url.startswith("http://"):
        kwargs["scheme"] = "http"
        # Strip scheme from endpoint_override for pyarrow
        kwargs["endpoint_override"] = settings.s3_endpoint_url.replace("http://", "")

    from pyarrow.fs import S3FileSystem
    return S3FileSystem(**kwargs)


def _s3_uri_to_path(uri: str) -> str:
    """Convert s3://bucket/key to bucket/key for PyArrow fs."""
    return uri.replace("s3://", "", 1)


def _s3_read_schema(path: str) -> pa.Schema:
    """Read schema from an S3 Parquet file."""
    fs = _get_s3_filesystem()
    s3_path = _s3_uri_to_path(path)
    pf = pq.ParquetFile(s3_path, filesystem=fs)
    return pf.schema_arrow


def _s3_read_sample(path: str, n_rows: int = 10_000) -> pa.Table:
    """Read a sample from an S3 Parquet file."""
    fs = _get_s3_filesystem()
    s3_path = _s3_uri_to_path(path)
    pf = pq.ParquetFile(s3_path, filesystem=fs)
    batches = []
    total = 0
    for batch in pf.iter_batches(batch_size=min(n_rows, 10_000)):
        remaining = n_rows - total
        if remaining <= 0:
            break
        if batch.num_rows > remaining:
            batch = batch.slice(0, remaining)
        batches.append(batch)
        total += batch.num_rows
    if not batches:
        return pa.table({})
    return pa.Table.from_batches(batches, schema=pf.schema_arrow)
