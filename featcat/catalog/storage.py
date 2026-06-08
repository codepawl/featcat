"""Storage backends for reading metadata from local or S3 paths."""

from __future__ import annotations

from pathlib import Path

import pyarrow as pa
import pyarrow.parquet as pq

_ORIGINAL_S3_FILESYSTEM = pa.fs.S3FileSystem
S3FileSystem = _ORIGINAL_S3_FILESYSTEM

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


def validate_path_input(raw: str) -> str:
    """Normalize and validate a user-supplied path string at the API boundary.

    Accepts:
    - ``s3://bucket/...`` URIs (delegates shape check to :func:`parse_s3_uri`)
    - Absolute local paths

    Rejects:
    - Empty / whitespace-only strings
    - Control characters (defense against header / log injection)
    - Non-``s3://`` URI schemes (``http://``, ``file://``, etc.)
    - Relative local paths (server context can't safely interpret cwd)

    Returns the normalized path (whitespace stripped, local paths un-resolved
    so the caller can decide whether existence-check failure is fatal).
    """
    if not isinstance(raw, str):
        raise ValueError("path must be a string")
    s = raw.strip()
    if not s:
        raise ValueError("path must not be empty")
    if any(ord(c) < 32 for c in s):
        raise ValueError("path contains control characters")
    if is_s3_uri(s):
        parse_s3_uri(s)  # raises on malformed
        return s
    if "://" in s:
        scheme = s.split("://", 1)[0]
        raise ValueError(f"unsupported URI scheme: {scheme!r}; only s3:// or absolute local paths are accepted")
    p = Path(s)
    if not p.is_absolute():
        raise ValueError(f"local path must be absolute: {raw!r}")
    return str(p)


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
    """Create a PyArrow S3FileSystem from featcat settings.

    Credential resolution order:
      1. ``FEATCAT_S3_ACCESS_KEY`` + ``FEATCAT_S3_SECRET_KEY``
         (+ optional ``FEATCAT_S3_SESSION_TOKEN`` for STS / role-assume).
         Both keys must be set together — the Settings model_validator
         enforces this; partial config raises at load time.
      2. PyArrow's default chain (when our keys are unset): standard
         ``AWS_ACCESS_KEY_ID`` / ``AWS_SECRET_ACCESS_KEY`` env vars,
         ``~/.aws/credentials`` profiles, IAM role on EC2/ECS/EKS.

    Always passes timeouts and region so behavior is deterministic
    regardless of the underlying default.
    """
    from ..config import load_settings

    settings = load_settings()

    kwargs: dict = {
        "region": settings.s3_region,
        "connect_timeout": settings.s3_connect_timeout_ms / 1000.0,
        "request_timeout": settings.s3_request_timeout_ms / 1000.0,
    }

    # Explicit FEATCAT_S3_* creds take precedence; partial config is caught
    # by the Settings validator, so reaching here with both set or both
    # unset is the only possibility.
    access_key = settings.s3_access_key_id or settings.s3_access_key
    secret_key = settings.s3_secret_access_key or settings.s3_secret_key
    if access_key and secret_key:
        kwargs["access_key"] = access_key
        kwargs["secret_key"] = secret_key
        if settings.s3_session_token:
            kwargs["session_token"] = settings.s3_session_token

    kwargs["force_virtual_addressing"] = not settings.s3_force_path_style

    if settings.s3_endpoint_url:
        kwargs["endpoint_override"] = settings.s3_endpoint_url
        # MinIO / self-hosted: PyArrow expects the scheme split out.
        if settings.s3_endpoint_url.startswith("http://"):
            kwargs["scheme"] = "http"
            kwargs["endpoint_override"] = settings.s3_endpoint_url.replace("http://", "")

    constructor = S3FileSystem if S3FileSystem is not _ORIGINAL_S3_FILESYSTEM else pa.fs.S3FileSystem
    return constructor(**kwargs)


def _s3_uri_to_path(uri: str) -> str:
    """Convert s3://bucket/key to bucket/key for PyArrow fs."""
    return uri.replace("s3://", "", 1)


def s3_config_missing_fields() -> list[str]:
    """Return required S3-compatible settings that are not configured."""
    from ..config import load_settings

    settings = load_settings()
    missing: list[str] = []
    if not settings.s3_endpoint_url:
        missing.append("FEATCAT_S3_ENDPOINT_URL")
    if not (settings.s3_access_key_id or settings.s3_access_key):
        missing.append("FEATCAT_S3_ACCESS_KEY_ID")
    if not (settings.s3_secret_access_key or settings.s3_secret_key):
        missing.append("FEATCAT_S3_SECRET_ACCESS_KEY")
    return missing


def parquet_filesystem_path(path: str) -> tuple[pa.fs.FileSystem | None, str]:
    """Return a PyArrow filesystem and path for local or S3 parquet IO."""
    if is_s3_uri(path):
        return _get_s3_filesystem(), _s3_uri_to_path(path)
    return None, path


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
