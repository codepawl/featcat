"""Service helpers for materializing latest offline values into the online store."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

import pyarrow as pa
import pyarrow.parquet as pq

from .models import DataSource, OnlineFeatureWrite
from .online_store import write_online_features
from .scanner import detect_file_format
from .storage import is_s3_uri, parquet_filesystem_path, read_parquet_schema, s3_config_missing_fields

if TYPE_CHECKING:
    from .backend import CatalogBackend


@dataclass(frozen=True)
class MaterializationIssue:
    """Structured validation or write issue returned by materialization."""

    code: str
    message: str
    field: str | None = None


@dataclass(frozen=True)
class MaterializationResult:
    """Result of a latest-from-source materialization attempt."""

    is_valid: bool
    errors: list[MaterializationIssue] = field(default_factory=list)
    warnings: list[MaterializationIssue] = field(default_factory=list)
    source_name: str = ""
    source_path: str | None = None
    project: str = ""
    feature_view: str = ""
    entity_key: str | None = None
    event_timestamp_column: str | None = None
    created_timestamp_column: str | None = None
    feature_columns: list[str] = field(default_factory=list)
    entity_count: int = 0
    feature_count: int = 0
    requested: int = 0
    written: int = 0
    skipped_older: int = 0
    skipped_same_timestamp: int = 0


@dataclass(frozen=True)
class _LatestRow:
    values: dict[str, Any]
    event_timestamp: datetime
    created_timestamp: datetime | None
    row_index: int


def _issue(code: str, message: str, field: str | None = None) -> MaterializationIssue:
    return MaterializationIssue(code=code, message=message, field=field)


def _base_result(
    *,
    source_name: str,
    source: DataSource | None,
    project: str,
    feature_view: str,
    feature_columns: list[str],
    errors: list[MaterializationIssue],
    warnings: list[MaterializationIssue] | None = None,
) -> MaterializationResult:
    return MaterializationResult(
        is_valid=not errors,
        errors=errors,
        warnings=warnings or [],
        source_name=source_name,
        source_path=source.path if source else None,
        project=project,
        feature_view=feature_view,
        entity_key=source.entity_key if source else None,
        event_timestamp_column=source.event_timestamp_column if source else None,
        created_timestamp_column=source.created_timestamp_column if source else None,
        feature_columns=feature_columns,
        feature_count=len(feature_columns),
    )


def _s3_config_error(path: str) -> MaterializationIssue | None:
    if not is_s3_uri(path):
        return None
    try:
        missing = s3_config_missing_fields()
    except ValueError as exc:
        return _issue("invalid_s3_config", str(exc), "source_path")
    if missing:
        return _issue(
            "missing_s3_config",
            "S3-compatible data paths require configuration for: " + ", ".join(missing),
            "source_path",
        )
    return None


def _source_format(source: DataSource) -> str:
    return source.format or detect_file_format(source.path)


def _source_label(fmt: str) -> str:
    return "CSV source" if fmt == "csv" else "Parquet source"


def _source_schema(path: str, fmt: str) -> pa.Schema:
    import pyarrow.csv as pa_csv

    if fmt == "csv":
        if is_s3_uri(path):
            from .storage import _get_s3_filesystem, parse_s3_uri

            fs = _get_s3_filesystem()
            bucket, key = parse_s3_uri(path)
            with fs.open_input_file(f"{bucket}/{key}") as f:
                return pa_csv.read_csv(f).schema
        return pa_csv.read_csv(path).schema
    return read_parquet_schema(path)


def _read_source_table(path: str, columns: list[str], fmt: str) -> pa.Table:
    if fmt == "csv":
        import pyarrow.csv as pa_csv

        convert_options = pa_csv.ConvertOptions(include_columns=columns)
        if is_s3_uri(path):
            from .storage import _get_s3_filesystem, parse_s3_uri

            fs = _get_s3_filesystem()
            bucket, key = parse_s3_uri(path)
            with fs.open_input_file(f"{bucket}/{key}") as f:
                return pa_csv.read_csv(f, convert_options=convert_options)
        return pa_csv.read_csv(path, convert_options=convert_options)

    filesystem, parquet_path = parquet_filesystem_path(path)
    return pq.read_table(parquet_path, columns=columns, filesystem=filesystem)


def _coerce_utc_datetime(value: Any, *, field: str, row_index: int) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError(f"{field} at row {row_index} is not an ISO datetime") from exc
    else:
        raise ValueError(f"{field} at row {row_index} is not a datetime")

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_newer(left: _LatestRow, right: _LatestRow) -> bool:
    """Return true when left should replace right for a single entity."""
    if left.event_timestamp != right.event_timestamp:
        return left.event_timestamp > right.event_timestamp

    min_timestamp = datetime.min.replace(tzinfo=timezone.utc)
    left_created = left.created_timestamp or min_timestamp
    right_created = right.created_timestamp or min_timestamp
    if left_created != right_created:
        return left_created > right_created

    return left.row_index > right.row_index


def _latest_rows(
    rows: list[dict[str, Any]],
    *,
    entity_key: str,
    event_timestamp_column: str,
    created_timestamp_column: str | None,
) -> tuple[dict[Any, _LatestRow], list[MaterializationIssue]]:
    latest: dict[Any, _LatestRow] = {}
    errors: list[MaterializationIssue] = []

    for row_index, row in enumerate(rows):
        try:
            event_timestamp = _coerce_utc_datetime(
                row[event_timestamp_column],
                field=event_timestamp_column,
                row_index=row_index,
            )
            created_timestamp = (
                _coerce_utc_datetime(
                    row[created_timestamp_column],
                    field=created_timestamp_column,
                    row_index=row_index,
                )
                if created_timestamp_column and row[created_timestamp_column] is not None
                else None
            )
        except ValueError as exc:
            errors.append(_issue("invalid_timestamp", str(exc)))
            continue

        candidate = _LatestRow(
            values=row,
            event_timestamp=event_timestamp,
            created_timestamp=created_timestamp,
            row_index=row_index,
        )
        entity_value = row[entity_key]
        existing = latest.get(entity_value)
        if existing is None or _is_newer(candidate, existing):
            latest[entity_value] = candidate

    return latest, errors


def _value_dtype(schema: pa.Schema, column: str) -> str:
    return str(schema.field(column).type)


def materialize_latest_from_source(
    db: CatalogBackend,
    *,
    source_name: str,
    feature_columns: list[str],
    project: str = "",
    feature_view: str = "",
) -> MaterializationResult:
    """Materialize latest values from one registered Parquet or CSV source.

    The MVP supports a registered DataSource with one entity key column. It
    loads the full source file, selects the latest row per entity by event time,
    breaks same-event ties by created time when configured, and uses source row
    index as the final deterministic fallback.
    """
    selected_features = list(feature_columns)
    errors: list[MaterializationIssue] = []
    source = db.get_source_by_name(source_name)
    if source is None:
        errors.append(_issue("source_not_found", f"DataSource is not registered: {source_name}", "source_name"))
        return _base_result(
            source_name=source_name,
            source=None,
            project=project,
            feature_view=feature_view,
            feature_columns=selected_features,
            errors=errors,
        )

    if not source.path:
        errors.append(_issue("missing_source_path", "DataSource must have a path", "source_path"))
    fmt = _source_format(source)
    if fmt not in {"parquet", "csv"}:
        errors.append(
            _issue("unsupported_source_format", "Materialization requires a Parquet or CSV DataSource", "format")
        )
    if not source.entity_key:
        errors.append(_issue("missing_entity_key", "DataSource must have entity_key metadata", "entity_key"))
    if not source.event_timestamp_column:
        errors.append(
            _issue(
                "missing_event_timestamp_column",
                "DataSource must have event_timestamp_column metadata",
                "event_timestamp_column",
            )
        )
    if not selected_features:
        errors.append(_issue("missing_feature_columns", "feature_columns must be non-empty", "feature_columns"))

    if source.path:
        s3_error = _s3_config_error(source.path)
        if s3_error is not None:
            errors.append(s3_error)

    schema: pa.Schema | None = None
    if not errors:
        try:
            schema = _source_schema(source.path, fmt)
        except Exception as exc:  # noqa: BLE001 - surface storage failures as structured validation.
            errors.append(_issue("source_path_unreadable", str(exc), "source_path"))

    if schema is not None:
        source_label = _source_label(fmt)
        available_columns = {field.name for field in schema}
        required_columns = [source.entity_key, source.event_timestamp_column, source.created_timestamp_column]
        for column, field_name, code in [
            (source.entity_key, "entity_key", "missing_entity_key_column"),
            (source.event_timestamp_column, "event_timestamp_column", "missing_event_timestamp_column"),
            (source.created_timestamp_column, "created_timestamp_column", "missing_created_timestamp_column"),
        ]:
            if column and column not in available_columns:
                errors.append(_issue(code, f"{source_label} is missing column: {column}", field_name))
        for column in selected_features:
            if column not in available_columns:
                errors.append(
                    _issue("missing_feature_column", f"{source_label} is missing feature column: {column}", column)
                )
            elif db.get_feature_by_name(f"{source.name}.{column}") is None:
                errors.append(
                    _issue(
                        "unknown_feature_ref",
                        f"Feature is not registered: {source.name}.{column}",
                        "feature_columns",
                    )
                )
        read_columns = [column for column in [*required_columns, *selected_features] if column]
    else:
        read_columns = []

    if errors:
        return _base_result(
            source_name=source_name,
            source=source,
            project=project,
            feature_view=feature_view,
            feature_columns=selected_features,
            errors=errors,
        )

    assert schema is not None
    assert source.entity_key is not None
    assert source.event_timestamp_column is not None

    table = _read_source_table(source.path, columns=list(dict.fromkeys(read_columns)), fmt=fmt)
    latest, timestamp_errors = _latest_rows(
        table.to_pylist(),
        entity_key=source.entity_key,
        event_timestamp_column=source.event_timestamp_column,
        created_timestamp_column=source.created_timestamp_column,
    )
    if timestamp_errors:
        return _base_result(
            source_name=source_name,
            source=source,
            project=project,
            feature_view=feature_view,
            feature_columns=selected_features,
            errors=timestamp_errors,
        )

    writes = [
        OnlineFeatureWrite(
            entity_key={source.entity_key: latest_row.values[source.entity_key]},
            feature_ref=f"{source.name}.{feature_column}",
            value=latest_row.values[feature_column],
            value_dtype=_value_dtype(schema, feature_column),
            event_timestamp=latest_row.event_timestamp,
            created_timestamp=latest_row.created_timestamp,
            source_name=source.name,
            source_path=source.path,
        )
        for latest_row in latest.values()
        for feature_column in selected_features
    ]
    write_result = write_online_features(db, rows=writes, project=project, feature_view=feature_view)
    write_errors = [_issue(error.code, error.message, error.field) for error in write_result.errors]

    return MaterializationResult(
        is_valid=not write_errors,
        errors=write_errors,
        warnings=[],
        source_name=source_name,
        source_path=source.path,
        project=project,
        feature_view=feature_view,
        entity_key=source.entity_key,
        event_timestamp_column=source.event_timestamp_column,
        created_timestamp_column=source.created_timestamp_column,
        feature_columns=selected_features,
        entity_count=len(latest),
        feature_count=len(selected_features),
        requested=write_result.requested,
        written=write_result.written,
        skipped_older=write_result.skipped_older,
        skipped_same_timestamp=write_result.skipped_same_timestamp,
    )
