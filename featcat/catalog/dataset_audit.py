"""Audit helpers for training dataset build requests."""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.parse import urlsplit, urlunsplit

if TYPE_CHECKING:
    from .backend import CatalogBackend
    from .training_dataset import TrainingDatasetBuildResult, TrainingDatasetValidationIssue


def sanitize_audit_path(path: str | None) -> str | None:
    """Remove URI userinfo before persisting paths in audit rows."""
    if path is None or "://" not in path:
        return path
    try:
        parsed = urlsplit(path)
    except ValueError:
        return path
    if not parsed.hostname:
        return path
    netloc = parsed.hostname
    if parsed.port is not None:
        netloc = f"{netloc}:{parsed.port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path, parsed.query, parsed.fragment))


def issue_to_dict(issue: TrainingDatasetValidationIssue) -> dict[str, str | None]:
    return {"code": issue.code, "message": issue.message, "field": issue.field}


def dataset_build_status(result: TrainingDatasetBuildResult) -> str:
    return "success" if result.is_valid else "validation_failed"


def record_dataset_build_audit(
    db: CatalogBackend,
    *,
    result: TrainingDatasetBuildResult,
    source_name: str | None,
    actor: str | None,
    requested_source_path: str | None = None,
    requested_output_path: str | None = None,
) -> str:
    """Persist an audit row for a completed dataset build request."""
    return db.record_dataset_build_audit(
        status=dataset_build_status(result),
        entity_df_path=sanitize_audit_path(result.entity_df_path) or "",
        source_path=sanitize_audit_path(result.source_path or requested_source_path),
        source_name=source_name,
        output_path=sanitize_audit_path(result.output_path or requested_output_path),
        entity_key=result.entity_key,
        entity_timestamp_column=result.entity_timestamp_column,
        source_event_timestamp_column=result.source_event_timestamp_column,
        feature_columns=result.feature_columns,
        row_count=result.row_count,
        feature_count=result.feature_count,
        unresolved_row_count=result.unresolved_row_count,
        missing_feature_value_count=result.missing_feature_value_count,
        errors=[issue_to_dict(issue) for issue in result.errors],
        warnings=[issue_to_dict(issue) for issue in result.warnings],
        actor=actor,
    )


def record_dataset_build_error_audit(
    db: CatalogBackend,
    *,
    entity_df_path: str,
    source_path: str | None,
    source_name: str | None,
    output_path: str | None,
    entity_key: str | None,
    entity_timestamp_column: str | None,
    source_event_timestamp_column: str | None,
    feature_columns: list[str],
    error: Exception,
    actor: str | None,
) -> str:
    """Persist an audit row for an unexpected dataset build error."""
    return db.record_dataset_build_audit(
        status="error",
        entity_df_path=sanitize_audit_path(entity_df_path) or "",
        source_path=sanitize_audit_path(source_path),
        source_name=source_name,
        output_path=sanitize_audit_path(output_path),
        entity_key=entity_key,
        entity_timestamp_column=entity_timestamp_column,
        source_event_timestamp_column=source_event_timestamp_column,
        feature_columns=feature_columns,
        errors=[{"code": "dataset_build_error", "message": str(error), "field": None}],
        actor=actor,
    )
