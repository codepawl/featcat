"""Local point-in-time training dataset builder."""

from __future__ import annotations

import warnings
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pyarrow.parquet as pq

if TYPE_CHECKING:
    import polars as pl

    from .models import DataSource


@dataclass(frozen=True)
class TrainingDatasetValidationIssue:
    """Structured validation issue returned by the dataset builder."""

    code: str
    message: str
    field: str | None = None


@dataclass(frozen=True)
class TrainingDatasetBuildResult:
    """Result of local training dataset validation."""

    is_valid: bool
    errors: list[TrainingDatasetValidationIssue] = field(default_factory=list)
    warnings: list[TrainingDatasetValidationIssue] = field(default_factory=list)
    entity_df_path: str | None = None
    source_path: str | None = None
    entity_key: str | None = None
    entity_timestamp_column: str | None = None
    source_event_timestamp_column: str | None = None
    feature_columns: list[str] = field(default_factory=list)
    output_path: str | None = None
    row_count: int = 0
    feature_count: int = 0
    unresolved_row_count: int = 0
    missing_feature_value_count: int = 0
    dataframe: pl.DataFrame | None = None


def _issue(code: str, message: str, field: str | None = None) -> TrainingDatasetValidationIssue:
    return TrainingDatasetValidationIssue(code=code, message=message, field=field)


def training_dataset_result_to_dict(result: TrainingDatasetBuildResult) -> dict:
    """Serialize a build result without the in-memory dataframe."""
    return {
        "is_valid": result.is_valid,
        "errors": [{"code": issue.code, "message": issue.message, "field": issue.field} for issue in result.errors],
        "warnings": [{"code": issue.code, "message": issue.message, "field": issue.field} for issue in result.warnings],
        "entity_df_path": result.entity_df_path,
        "source_path": result.source_path,
        "entity_key": result.entity_key,
        "entity_timestamp_column": result.entity_timestamp_column,
        "source_event_timestamp_column": result.source_event_timestamp_column,
        "feature_columns": result.feature_columns,
        "output_path": result.output_path,
        "row_count": result.row_count,
        "feature_count": result.feature_count,
        "unresolved_row_count": result.unresolved_row_count,
        "missing_feature_value_count": result.missing_feature_value_count,
    }


def _is_local_path(path: str) -> bool:
    return "://" not in path


def _parquet_columns(path: str) -> set[str]:
    schema = pq.ParquetFile(path).schema_arrow
    return {field.name for field in schema}


def _row_index_column(existing_columns: set[str]) -> str:
    column = "__featcat_entity_row"
    suffix = 1
    while column in existing_columns:
        column = f"__featcat_entity_row_{suffix}"
        suffix += 1
    return column


def _build_point_in_time_frame(
    *,
    entity_df_path: str,
    source_path: str,
    entity_key: str,
    entity_timestamp_column: str,
    source_event_timestamp_column: str,
    feature_columns: list[str],
) -> pl.DataFrame:
    import polars as pl

    source_columns = [entity_key, source_event_timestamp_column, *feature_columns]
    entity = pl.read_parquet(entity_df_path)
    entity_columns = list(entity.columns)
    row_index_column = _row_index_column(set(entity_columns) | set(source_columns))
    entity = entity.with_row_index(row_index_column)
    source = pl.read_parquet(source_path, columns=list(dict.fromkeys(source_columns)))

    with warnings.catch_warnings():
        warnings.simplefilter("ignore", UserWarning)
        joined = entity.sort([entity_timestamp_column, entity_key]).join_asof(
            source.sort([source_event_timestamp_column, entity_key]),
            left_on=entity_timestamp_column,
            right_on=source_event_timestamp_column,
            by=entity_key,
            strategy="backward",
        )

    return joined.sort(row_index_column).select([*entity_columns, *feature_columns])


def _missing_feature_value_count(frame: pl.DataFrame, feature_columns: list[str]) -> int:
    return sum(frame[column].null_count() for column in feature_columns)


def _unresolved_row_count(frame: pl.DataFrame, feature_columns: list[str]) -> int:
    import polars as pl

    if not feature_columns:
        return 0
    return frame.select(pl.all_horizontal([pl.col(column).is_null() for column in feature_columns]).sum()).item()


def build_training_dataset(
    entity_df_path: str,
    source_path: str | None = None,
    entity_key: str | None = None,
    entity_timestamp_column: str | None = None,
    source_event_timestamp_column: str | None = None,
    feature_columns: list[str] | None = None,
    output_path: str | None = None,
    *,
    data_source: DataSource | None = None,
) -> TrainingDatasetBuildResult:
    """Build a local point-in-time training dataset from parquet inputs.

    ``data_source`` is optional so callers can validate a registered source
    without duplicating path and join metadata. When a registered source is
    provided, its join metadata must be present.
    """
    errors: list[TrainingDatasetValidationIssue] = []
    warnings: list[TrainingDatasetValidationIssue] = []
    features = list(feature_columns or [])

    resolved_source_path = source_path or (data_source.path if data_source is not None else None)
    resolved_entity_key = entity_key or (data_source.entity_key if data_source is not None else None)
    resolved_source_event_ts = source_event_timestamp_column or (
        data_source.event_timestamp_column if data_source is not None else None
    )
    resolved_entity_ts = entity_timestamp_column or resolved_source_event_ts

    if data_source is not None and not data_source.entity_key:
        errors.append(
            _issue(
                "missing_entity_key_metadata",
                "DataSource must define entity_key for training dataset validation.",
                "data_source.entity_key",
            )
        )
    if data_source is not None and not data_source.event_timestamp_column:
        errors.append(
            _issue(
                "missing_event_timestamp_column_metadata",
                "DataSource must define event_timestamp_column for training dataset validation.",
                "data_source.event_timestamp_column",
            )
        )

    if not resolved_entity_key:
        errors.append(
            _issue(
                "missing_entity_key",
                "entity_key is required when no registered DataSource entity_key is available.",
                "entity_key",
            )
        )
    if not resolved_source_event_ts:
        errors.append(
            _issue(
                "missing_source_event_timestamp_column",
                "source_event_timestamp_column is required when no registered DataSource "
                "event_timestamp_column is available.",
                "source_event_timestamp_column",
            )
        )
    if not resolved_entity_ts:
        errors.append(
            _issue(
                "missing_entity_timestamp_column",
                "entity_timestamp_column is required when it cannot be inferred from the "
                "source event timestamp column.",
                "entity_timestamp_column",
            )
        )

    entity_columns: set[str] | None = None
    if not _is_local_path(entity_df_path):
        errors.append(
            _issue(
                "unsupported_entity_path_scheme",
                "Only local parquet entity dataframe paths are supported.",
                "entity_df_path",
            )
        )
    elif not Path(entity_df_path).exists():
        errors.append(
            _issue(
                "missing_entity_dataframe",
                f"Entity dataframe file does not exist: {entity_df_path}",
                "entity_df_path",
            )
        )
    else:
        entity_columns = _parquet_columns(entity_df_path)

    source_columns: set[str] | None = None
    if resolved_source_path is None:
        errors.append(
            _issue(
                "missing_source_path",
                "source_path or data_source.path is required.",
                "source_path",
            )
        )
    elif not _is_local_path(resolved_source_path):
        errors.append(
            _issue(
                "unsupported_source_path_scheme",
                "Only local parquet source dataframe paths are supported.",
                "source_path",
            )
        )
    elif not Path(resolved_source_path).exists():
        errors.append(
            _issue(
                "missing_source_dataframe",
                f"Source dataframe file does not exist: {resolved_source_path}",
                "source_path",
            )
        )
    else:
        source_columns = _parquet_columns(resolved_source_path)

    if entity_columns is not None:
        if resolved_entity_key and resolved_entity_key not in entity_columns:
            errors.append(
                _issue(
                    "entity_dataframe_missing_entity_key",
                    f"Entity dataframe is missing entity key column: {resolved_entity_key}",
                    "entity_key",
                )
            )
        if resolved_entity_ts and resolved_entity_ts not in entity_columns:
            errors.append(
                _issue(
                    "entity_dataframe_missing_timestamp",
                    f"Entity dataframe is missing timestamp column: {resolved_entity_ts}",
                    "entity_timestamp_column",
                )
            )
        feature_collisions = [column for column in features if column in entity_columns]
        if feature_collisions:
            errors.append(
                _issue(
                    "feature_column_collides_with_entity_dataframe",
                    f"Requested feature columns already exist in entity dataframe: {', '.join(feature_collisions)}",
                    "feature_columns",
                )
            )

    if source_columns is not None:
        if resolved_entity_key and resolved_entity_key not in source_columns:
            errors.append(
                _issue(
                    "source_dataframe_missing_entity_key",
                    f"Source dataframe is missing entity key column: {resolved_entity_key}",
                    "entity_key",
                )
            )
        if resolved_source_event_ts and resolved_source_event_ts not in source_columns:
            errors.append(
                _issue(
                    "source_dataframe_missing_event_timestamp",
                    f"Source dataframe is missing event timestamp column: {resolved_source_event_ts}",
                    "source_event_timestamp_column",
                )
            )

        missing_features = [column for column in features if column not in source_columns]
        if missing_features:
            errors.append(
                _issue(
                    "requested_feature_columns_missing",
                    f"Requested feature columns are missing from source dataframe: {', '.join(missing_features)}",
                    "feature_columns",
                )
            )

    if output_path is not None and not _is_local_path(output_path):
        errors.append(
            _issue(
                "unsupported_output_path_scheme",
                "Only local parquet output paths are supported.",
                "output_path",
            )
        )

    dataframe: pl.DataFrame | None = None
    row_count = 0
    unresolved_row_count = 0
    missing_feature_value_count = 0
    written_output_path: str | None = None

    if not errors:
        assert resolved_source_path is not None  # noqa: S101
        assert resolved_entity_key is not None  # noqa: S101
        assert resolved_entity_ts is not None  # noqa: S101
        assert resolved_source_event_ts is not None  # noqa: S101
        dataframe = _build_point_in_time_frame(
            entity_df_path=entity_df_path,
            source_path=resolved_source_path,
            entity_key=resolved_entity_key,
            entity_timestamp_column=resolved_entity_ts,
            source_event_timestamp_column=resolved_source_event_ts,
            feature_columns=features,
        )
        row_count = dataframe.height
        unresolved_row_count = _unresolved_row_count(dataframe, features)
        missing_feature_value_count = _missing_feature_value_count(dataframe, features)
        if output_path is not None:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            dataframe.write_parquet(output_path)
            written_output_path = output_path

    return TrainingDatasetBuildResult(
        is_valid=not errors,
        errors=errors,
        warnings=warnings,
        entity_df_path=entity_df_path,
        source_path=resolved_source_path,
        entity_key=resolved_entity_key,
        entity_timestamp_column=resolved_entity_ts,
        source_event_timestamp_column=resolved_source_event_ts,
        feature_columns=features,
        output_path=written_output_path,
        row_count=row_count,
        feature_count=len(features),
        unresolved_row_count=unresolved_row_count,
        missing_feature_value_count=missing_feature_value_count,
        dataframe=dataframe if not errors else None,
    )
