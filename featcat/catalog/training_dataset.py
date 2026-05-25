"""Local training dataset validation foundation.

This module intentionally stops short of point-in-time joins and materialization.
It validates the local parquet inputs and join metadata needed by a future
training dataset builder.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

import pyarrow.parquet as pq

if TYPE_CHECKING:
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


def _issue(code: str, message: str, field: str | None = None) -> TrainingDatasetValidationIssue:
    return TrainingDatasetValidationIssue(code=code, message=message, field=field)


def _is_local_path(path: str) -> bool:
    return "://" not in path


def _parquet_columns(path: str) -> set[str]:
    schema = pq.ParquetFile(path).schema_arrow
    return {field.name for field in schema}


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
    """Validate local parquet inputs for a future training dataset build.

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

    if output_path is not None:
        warnings.append(
            _issue(
                "output_materialization_deferred",
                "output_path was accepted for future compatibility, but materialization "
                "and point-in-time joins are deferred.",
                "output_path",
            )
        )

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
        output_path=output_path,
    )
