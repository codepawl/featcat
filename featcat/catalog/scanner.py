"""Auto-scan Parquet files to extract schema and basic statistics."""

from __future__ import annotations

import contextlib
from pathlib import Path

import pyarrow as pa

from .models import ColumnInfo
from .storage import (
    _get_s3_filesystem,
    is_s3_uri,
    parse_s3_uri,
    read_parquet_sample,
    read_parquet_schema,
    resolve_parquet_path,
)


def discover_parquet_files(path: str, recursive: bool = False) -> list[str]:
    """Walk a local directory or S3 prefix and return all ``.parquet`` paths.

    Args:
        path: Local directory path or S3 prefix (``s3://bucket/key/...``).
        recursive: Whether to walk sub-prefixes.

    Returns:
        Sorted list of paths as strings. Local paths come back absolute;
        S3 paths come back in ``s3://bucket/key.parquet`` form. The return
        type is ``list[str]`` (rather than ``list[Path]``) because
        ``pathlib.Path("s3://...")`` doesn't model an S3 URI meaningfully —
        callers handle both with ``str(p)`` / ``Path(p).stem``.

    Raises:
        NotADirectoryError: local ``path`` is not a directory.
        FileNotFoundError: S3 prefix doesn't exist.
        ValueError: S3 URI is malformed (empty bucket, missing scheme, etc.).
    """
    if is_s3_uri(path):
        return _discover_s3_parquet_files(path, recursive)
    root = Path(path).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")
    pattern = "**/*.parquet" if recursive else "*.parquet"
    return [str(p) for p in sorted(root.glob(pattern))]


def _discover_s3_parquet_files(uri: str, recursive: bool) -> list[str]:
    """Enumerate ``.parquet`` files under an S3 prefix via PyArrow's
    ``S3FileSystem.get_file_info``.

    The Phase 1 spike confirmed that ``FileInfo.path`` comes back as
    ``bucket/key/...`` (no ``s3://`` prefix), that ``recursive=True``
    interleaves Directory and File entries (so we filter by ``type``),
    and that PyArrow does not sort the response (so we sort here).
    """
    from pyarrow.fs import FileSelector, FileType

    bucket, prefix = parse_s3_uri(uri)
    fs = _get_s3_filesystem()
    selector_path = f"{bucket}/{prefix}" if prefix else bucket
    try:
        infos = fs.get_file_info(FileSelector(selector_path, recursive=recursive, allow_not_found=False))
    except FileNotFoundError as e:
        raise FileNotFoundError(f"S3 prefix not found: {uri}") from e
    parquet_files = [
        f"s3://{info.path}" for info in infos if info.type == FileType.File and info.path.endswith(".parquet")
    ]
    return sorted(parquet_files)


def scan_source(path: str) -> list[ColumnInfo]:
    """Scan a data source and return column info with stats.

    Supports both local paths and s3:// URIs.
    """
    resolved = resolve_parquet_path(path)

    # S3 paths go straight to read; local paths may be directories
    actual_path = resolved if is_s3_uri(resolved) else _find_parquet_file(resolved)

    schema = read_parquet_schema(actual_path)
    table = read_parquet_sample(actual_path)

    columns: list[ColumnInfo] = []
    for _i, field in enumerate(schema):
        col_array = table.column(field.name) if table.num_rows > 0 else None
        stats = _compute_stats(col_array, field.type) if col_array else {}
        columns.append(
            ColumnInfo(
                column_name=field.name,
                dtype=str(field.type),
                stats=stats,
            )
        )
    return columns


def _find_parquet_file(path: str) -> str:
    """If path is a directory, return the first .parquet file found."""
    p = Path(path)
    if p.is_dir():
        parquet_files = sorted(p.glob("*.parquet"))
        if not parquet_files:
            raise FileNotFoundError(f"No .parquet files found in {path}")
        return str(parquet_files[0])
    return path


def _compute_stats(col: pa.ChunkedArray, dtype: pa.DataType) -> dict:
    """Compute basic statistics for a single column."""
    import pyarrow.compute as pc

    total = len(col)
    null_count = col.null_count
    null_ratio = round(null_count / total, 4) if total > 0 else 0.0

    stats: dict = {
        "null_count": null_count,
        "null_ratio": null_ratio,
        "total_count": total,
    }

    # Unique count (works for all types)
    with contextlib.suppress(Exception):
        stats["unique_count"] = pc.count_distinct(col).as_py()

    # Numeric stats
    if pa.types.is_integer(dtype) or pa.types.is_floating(dtype):
        try:
            stats["min"] = pc.min(col).as_py()
            stats["max"] = pc.max(col).as_py()
            stats["mean"] = round(pc.mean(col).as_py(), 4) if pc.mean(col).as_py() is not None else None
            stats["std"] = round(pc.stddev(col).as_py(), 4) if pc.stddev(col).as_py() is not None else None
        except Exception:
            pass

    return stats
