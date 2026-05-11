"""Storage backends for reading metadata from local or S3 paths."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

# ---------------------------------------------------------------------------
# URI helpers
# ---------------------------------------------------------------------------


def is_s3_uri(path: str) -> bool:
    """True if ``path`` looks like an S3 URI (``s3://`` scheme).

    Single source of truth for the local-vs-S3 routing decision; callers
    elsewhere in the codebase should use this helper instead of inlining
    ``path.startswith("s3://")`` so the rule stays consistent.
    """
    return path.startswith("s3://")


def parse_s3_uri(uri: str) -> tuple[str, str]:
    """Split ``s3://bucket/key/...`` into ``(bucket, key_prefix)``.

    Returns the bucket and the (possibly empty) key prefix. Raises ``ValueError``
    on malformed input — used by callers that need bucket / prefix separately
    for the PyArrow ``S3FileSystem`` (which speaks ``bucket/key`` paths, not
    ``s3://`` URIs).
    """
    if not is_s3_uri(uri):
        raise ValueError(f"not an S3 URI: {uri!r}")
    rest = uri[len("s3://") :]
    if not rest:
        raise ValueError(f"malformed S3 URI (empty bucket): {uri!r}")
    if "/" not in rest:
        return rest, ""
    bucket, prefix = rest.split("/", 1)
    if not bucket:
        raise ValueError(f"malformed S3 URI (empty bucket): {uri!r}")
    return bucket, prefix


# ---------------------------------------------------------------------------
# Local storage
# ---------------------------------------------------------------------------


def resolve_parquet_path(path: str) -> str:
    """Validate and resolve a data source path.

    For local paths, checks existence. For S3 URIs, returns as-is.
    """
    if is_s3_uri(path):
        return path
    p = Path(path).resolve()
    if not p.exists():
        raise FileNotFoundError(f"Path does not exist: {path}")
    return str(p)


def read_parquet_schema(path: str) -> pa.Schema:
    """Read only the schema from a Parquet file (no data loaded)."""
    if is_s3_uri(path):
        return _s3_read_schema(path)
    pf = pq.ParquetFile(path)
    return pf.schema_arrow


def read_parquet_sample(path: str, n_rows: int = 10_000) -> pa.Table:
    """Read the first n_rows from a Parquet file for stats computation."""
    if is_s3_uri(path):
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


def _get_s3_filesystem() -> pa.fs.S3FileSystem:
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
