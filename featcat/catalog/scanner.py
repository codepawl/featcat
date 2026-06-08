"""Auto-scan Parquet and CSV files to extract schema and basic statistics.

File format is auto-detected from the file extension:
- ``.parquet`` → PyArrow Parquet reader (existing behaviour).
- ``.csv``     → PyArrow CSV reader (new in this version).

Both local paths and ``s3://`` URIs are supported for all formats.
"""

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

# ─── Format detection ─────────────────────────────────────────────────────────

_PARQUET_EXTS = {".parquet", ".pq"}
_CSV_EXTS = {".csv", ".tsv", ".txt"}


def detect_file_format(path: str) -> str:
    """Return 'parquet' or 'csv' based on the file extension.

    For paths without a recognisable extension we default to 'parquet' so
    the original behaviour is preserved.
    """
    suffix = Path(path.split("?")[0]).suffix.lower()  # strip query params for S3
    if suffix in _CSV_EXTS:
        return "csv"
    return "parquet"


# ─── File discovery ───────────────────────────────────────────────────────────


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


def discover_files(path: str, recursive: bool = False, formats: tuple[str, ...] = ("parquet", "csv")) -> list[str]:
    """Walk a local directory or S3 prefix and return files for the given formats.

    Args:
        path: Local directory path or S3 prefix.
        recursive: Whether to recurse into sub-directories / S3 prefixes.
        formats: Tuple of format names to include. Defaults to both
            ``("parquet", "csv")``.

    Returns:
        Sorted, deduplicated list of matching file paths (absolute local or
        ``s3://`` URIs).
    """
    extensions: set[str] = set()
    if "parquet" in formats:
        extensions.update(_PARQUET_EXTS)
    if "csv" in formats:
        extensions.update(_CSV_EXTS)

    if is_s3_uri(path):
        return _discover_s3_files(path, recursive, extensions)

    root = Path(path).resolve()
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {path}")
    results: list[Path] = []
    for ext in sorted(extensions):
        pattern = f"**/*{ext}" if recursive else f"*{ext}"
        results.extend(root.glob(pattern))
    return [str(p) for p in sorted(set(results))]


def _discover_s3_parquet_files(uri: str, recursive: bool) -> list[str]:
    """Enumerate ``.parquet`` files under an S3 prefix via PyArrow's
    ``S3FileSystem.get_file_info``.

    The Phase 1 spike confirmed that ``FileInfo.path`` comes back as
    ``bucket/key/...`` (no ``s3://`` prefix), that ``recursive=True``
    interleaves Directory and File entries (so we filter by ``type``),
    and that PyArrow does not sort the response (so we sort here).
    """
    return _discover_s3_files(uri, recursive, _PARQUET_EXTS)


def _discover_s3_files(uri: str, recursive: bool, extensions: set[str]) -> list[str]:
    """Generic S3 file discovery filtering by a set of extensions."""
    from pyarrow.fs import FileSelector, FileType

    bucket, prefix = parse_s3_uri(uri)
    fs = _get_s3_filesystem()
    selector_path = f"{bucket}/{prefix}" if prefix else bucket
    try:
        infos = fs.get_file_info(FileSelector(selector_path, recursive=recursive, allow_not_found=False))
    except FileNotFoundError as e:
        raise FileNotFoundError(f"S3 prefix not found: {uri}") from e
    matching = [
        f"s3://{info.path}"
        for info in infos
        if info.type == FileType.File and Path(info.path).suffix.lower() in extensions
    ]
    return sorted(matching)


# ─── Scanning ─────────────────────────────────────────────────────────────────


def scan_source(path: str) -> list[ColumnInfo]:
    """Scan a data source and return column info with stats.

    Supports both local paths and s3:// URIs, and auto-detects the file
    format from the extension (``.parquet`` or ``.csv``).
    """
    fmt = detect_file_format(path)
    if fmt == "csv":
        return _scan_csv_source(path)
    return _scan_parquet_source(path)


def _scan_parquet_source(path: str) -> list[ColumnInfo]:
    """Scan a Parquet file (local or S3)."""
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


def _scan_csv_source(path: str) -> list[ColumnInfo]:
    """Scan a CSV file (local or S3) and return column info with stats.

    Uses PyArrow's CSV reader so it shares the same type-inference pipeline
    as the Parquet path.  For large files we sample the first 10 000 rows
    to keep startup latency low.
    """
    import pyarrow.csv as pa_csv

    sample_rows = 10_000

    if is_s3_uri(path):
        fs = _get_s3_filesystem()
        bucket, key = parse_s3_uri(path)
        with fs.open_input_file(f"{bucket}/{key}") as f:
            reader = pa_csv.open_csv(f)
            batches = []
            row_count = 0
            for batch in reader:
                batches.append(batch)
                row_count += batch.num_rows
                if row_count >= sample_rows:
                    break
            table = pa.Table.from_batches(batches) if batches else reader.read_all()
    else:
        p = Path(path)
        if not p.exists():
            raise FileNotFoundError(f"CSV file not found: {path}")
        reader = pa_csv.open_csv(str(p))
        batches = []
        row_count = 0
        for batch in reader:
            batches.append(batch)
            row_count += batch.num_rows
            if row_count >= sample_rows:
                break
        table = pa.Table.from_batches(batches) if batches else reader.read_all()

    schema = table.schema
    columns: list[ColumnInfo] = []
    for field in schema:
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
