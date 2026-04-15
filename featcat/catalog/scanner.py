"""Auto-scan Parquet files to extract schema and basic statistics."""

from __future__ import annotations

import contextlib
from pathlib import Path

import pyarrow as pa

from .models import ColumnInfo
from .storage import read_parquet_sample, read_parquet_schema, resolve_parquet_path


def discover_parquet_files(path: str, recursive: bool = False) -> list[Path]:
    """Walk a directory and return all .parquet file paths.

    Args:
        path: Directory path to search.
        recursive: If True, search subdirectories recursively.

    Returns:
        Sorted list of Path objects for .parquet files found.
    """
    root = Path(path).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")
    pattern = "**/*.parquet" if recursive else "*.parquet"
    return sorted(root.glob(pattern))


def scan_source(path: str) -> list[ColumnInfo]:
    """Scan a data source and return column info with stats.

    Supports both local paths and s3:// URIs.
    """
    resolved = resolve_parquet_path(path)

    # S3 paths go straight to read; local paths may be directories
    actual_path = resolved if resolved.startswith("s3://") else _find_parquet_file(resolved)

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
