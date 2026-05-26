"""Audit helpers for online materialization requests."""

from __future__ import annotations

from typing import TYPE_CHECKING

from .dataset_audit import sanitize_audit_path

if TYPE_CHECKING:
    from .backend import CatalogBackend
    from .materialization import MaterializationIssue, MaterializationResult


def _issue_to_dict(issue: MaterializationIssue) -> dict[str, str | None]:
    return {"code": issue.code, "message": issue.message, "field": issue.field}


def materialization_status(result: MaterializationResult) -> str:
    return "success" if result.is_valid else "validation_failed"


def record_materialization_audit(
    db: CatalogBackend,
    *,
    result: MaterializationResult,
    actor: str | None,
) -> str:
    """Persist an audit row for a completed materialization request."""
    return db.record_materialization_audit(
        status=materialization_status(result),
        source_name=result.source_name,
        source_path=sanitize_audit_path(result.source_path),
        project=result.project,
        feature_view=result.feature_view,
        entity_key=result.entity_key,
        event_timestamp_column=result.event_timestamp_column,
        created_timestamp_column=result.created_timestamp_column,
        feature_columns=result.feature_columns,
        entity_count=result.entity_count,
        feature_count=result.feature_count,
        requested=result.requested,
        written=result.written,
        skipped_older=result.skipped_older,
        skipped_same_timestamp=result.skipped_same_timestamp,
        errors=[_issue_to_dict(issue) for issue in result.errors],
        warnings=[_issue_to_dict(issue) for issue in result.warnings],
        actor=actor,
    )


def record_materialization_error_audit(
    db: CatalogBackend,
    *,
    source_name: str,
    source_path: str | None = None,
    project: str = "",
    feature_view: str = "",
    entity_key: str | None = None,
    event_timestamp_column: str | None = None,
    created_timestamp_column: str | None = None,
    feature_columns: list[str] | None = None,
    error: Exception,
    actor: str | None,
) -> str:
    """Persist an audit row for an unexpected materialization error."""
    return db.record_materialization_audit(
        status="error",
        source_name=source_name,
        source_path=sanitize_audit_path(source_path),
        project=project,
        feature_view=feature_view,
        entity_key=entity_key,
        event_timestamp_column=event_timestamp_column,
        created_timestamp_column=created_timestamp_column,
        feature_columns=feature_columns or [],
        errors=[{"code": "materialization_error", "message": str(error), "field": None}],
        actor=actor,
    )
