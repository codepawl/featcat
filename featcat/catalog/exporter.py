"""Feature data export: extract columns from source parquet files and merge."""

from __future__ import annotations

import csv
import os
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pyarrow as pa
import pyarrow.parquet as pq

if TYPE_CHECKING:
    from .backend import CatalogBackend


EXPORT_DIR = Path(os.environ.get("FEATCAT_EXPORT_DIR", "/tmp/featcat_exports"))


@dataclass
class ExportResult:
    export_id: str
    output_path: str
    feature_count: int
    row_count: int
    sources_used: list[str]
    join_column: str | None
    code_snippet: str
    warnings: list[str] = field(default_factory=list)
    file_size: int = 0


def _group_by_source(
    feature_specs: list[str], db: CatalogBackend,
) -> dict[str, list[str]]:
    """Group feature specs by source, returning {source_name: [column_names]}."""
    source_columns: dict[str, list[str]] = {}
    for spec in feature_specs:
        feature = db.get_feature_by_name(spec)
        if feature is None:
            continue
        source_name = spec.split(".")[0] if "." in spec else ""
        source_columns.setdefault(source_name, []).append(feature.column_name)
    return source_columns


def _find_common_columns(source_paths: dict[str, str]) -> list[str]:
    """Find columns present in ALL sources."""
    column_sets: list[set[str]] = []
    for path in source_paths.values():
        schema = pq.ParquetFile(path).schema_arrow
        column_sets.append({f.name for f in schema})
    if not column_sets:
        return []
    common = column_sets[0]
    for s in column_sets[1:]:
        common &= s
    return sorted(common)


def _read_source_columns(
    path: str, columns: list[str],
) -> pa.Table:
    """Read specific columns from a parquet file."""
    return pq.read_table(path, columns=columns)


def _generate_snippet(
    output_path: str,
    feature_specs: list[str],
    sources_used: list[str],
    fmt: str,
) -> str:
    """Generate a Python code snippet for loading the exported data."""
    fname = Path(output_path).name
    columns = [s.split(".")[-1] if "." in s else s for s in feature_specs]
    col_comment = ", ".join(columns)

    if fmt == "csv":
        return (
            f"import polars as pl\n\n"
            f'df = pl.read_csv("{fname}")\n'
            f"# Features: {col_comment}\n"
            f"print(df.shape)\n"
            f"df.head()"
        )

    if len(sources_used) == 1:
        source = sources_used[0]
        col_list = ", ".join(f'"{c}"' for c in columns)
        return (
            f"import polars as pl\n\n"
            f'df = pl.read_parquet("/path/to/{source}.parquet").select([\n'
            f"    {col_list}\n"
            f"])\n"
            f"print(df.shape)\n"
            f"df.head()"
        )

    return (
        f"import polars as pl\n\n"
        f'df = pl.read_parquet("{fname}")\n'
        f"# Features: {col_comment}\n"
        f"print(df.shape)\n"
        f"df.head()"
    )


def export_features(
    feature_specs: list[str],
    db: CatalogBackend,
    output_path: str | None = None,
    join_on: str | None = None,
    fmt: str = "parquet",
) -> ExportResult:
    """Export feature data from source parquet files.

    Groups features by source, reads only needed columns, merges if multi-source.
    """
    export_id = uuid.uuid4().hex[:12]
    warnings: list[str] = []

    if output_path is None:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        ext = "csv" if fmt == "csv" else "parquet"
        output_path = str(EXPORT_DIR / f"{export_id}.{ext}")

    # Group features by source
    source_columns = _group_by_source(feature_specs, db)
    if not source_columns:
        msg = "No valid features found for the given specs."
        raise ValueError(msg)

    # Resolve source paths
    source_paths: dict[str, str] = {}
    for source_name in source_columns:
        source = db.get_source_by_name(source_name)
        if source is None:
            warnings.append(f"Source not found: {source_name}")
            continue
        source_paths[source_name] = source.path

    if not source_paths:
        msg = "No source files found."
        raise ValueError(msg)

    sources_used = list(source_paths.keys())

    if len(source_paths) == 1:
        # Single source: just select columns
        source_name = sources_used[0]
        path = source_paths[source_name]
        columns = source_columns[source_name]
        table = _read_source_columns(path, columns)
    else:
        # Multi-source: need to join
        if join_on is None:
            common = _find_common_columns(source_paths)
            if len(common) == 0:
                warnings.append("No common columns found across sources. Cannot auto-join.")
                msg = "No common column for join. Use --join-on to specify."
                raise ValueError(msg)
            if len(common) > 1:
                warnings.append(
                    f"Multiple common columns: {', '.join(common)}. Using '{common[0]}'."
                )
            join_on = common[0]

        # Read each source with join column + feature columns
        tables: list[pa.Table] = []
        for source_name, path in source_paths.items():
            cols = list(set([join_on, *source_columns[source_name]]))
            tables.append(_read_source_columns(path, cols))

        # Join tables
        table = tables[0]
        for t in tables[1:]:
            try:
                import polars as pl

                left = pl.from_arrow(table)
                right = pl.from_arrow(t)
                merged = left.join(right, on=join_on, how="inner")
                table = merged.to_arrow()
            except ImportError:
                # Fallback: just concat columns (less accurate but works for same-length)
                warnings.append("polars not installed, using simple column merge.")
                for col_name in t.column_names:
                    if col_name != join_on and col_name not in table.column_names:
                        table = table.append_column(col_name, t.column(col_name))

    # Write output
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        # Write CSV using Python csv module via pyarrow's to_pydict
        data = table.to_pydict()
        with open(output_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(table.column_names)
            rows = zip(*[data[col] for col in table.column_names], strict=False)
            writer.writerows(rows)
    else:
        pq.write_table(table, output_path)

    file_size = Path(output_path).stat().st_size

    snippet = _generate_snippet(output_path, feature_specs, sources_used, fmt)

    return ExportResult(
        export_id=export_id,
        output_path=output_path,
        feature_count=len(feature_specs),
        row_count=table.num_rows,
        sources_used=sources_used,
        join_column=join_on,
        code_snippet=snippet,
        warnings=warnings,
        file_size=file_size,
    )
