"""Core service helpers for the PostgreSQL online feature store."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from .models import (
    OnlineFeatureWrite,
    OnlineFeatureWriteError,
    OnlineFeatureWriteResult,
)

if TYPE_CHECKING:
    from .backend import CatalogBackend

PrimitiveJson = str | int | float | bool | None


def _json_default(value: Any) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _json_dumps(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=_json_default)


def canonical_entity_key(entity_key: dict[str, Any]) -> str:
    """Return compact sorted JSON for an entity key.

    MVP entity keys must be JSON objects with primitive values. Nested arrays
    and objects are intentionally rejected so hashing and cross-language SDKs
    stay deterministic.
    """
    if not isinstance(entity_key, dict) or not entity_key:
        raise ValueError("entity_key must be a non-empty JSON object")
    for key, value in entity_key.items():
        if not isinstance(key, str) or not key:
            raise ValueError("entity_key field names must be non-empty strings")
        if isinstance(value, (list, tuple, dict)):
            raise ValueError("entity_key values must be primitive JSON values")
        if not isinstance(value, (str, int, float, bool)) and value is not None:
            raise ValueError("entity_key values must be primitive JSON values")
    return _json_dumps(entity_key)


def entity_key_hash(entity_key: dict[str, Any]) -> str:
    """Stable SHA-256 hash for a canonical entity key."""
    return hashlib.sha256(canonical_entity_key(entity_key).encode("utf-8")).hexdigest()


def deterministic_write_id(
    *,
    project: str,
    feature_view: str,
    write: OnlineFeatureWrite,
    entity_key_json: str,
    value_json: str,
) -> str:
    """Build a deterministic write id for same-timestamp tie-breaking."""
    payload = {
        "created_timestamp": write.created_timestamp.isoformat() if write.created_timestamp else None,
        "entity_key": entity_key_json,
        "event_timestamp": write.event_timestamp.isoformat(),
        "feature_ref": write.feature_ref,
        "feature_view": feature_view,
        "project": project,
        "value": value_json,
        "value_dtype": write.value_dtype,
    }
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def prepare_online_write_records(
    db: CatalogBackend,
    *,
    rows: list[OnlineFeatureWrite],
    project: str = "",
    feature_view: str = "",
) -> tuple[list[dict[str, Any]], list[OnlineFeatureWriteError]]:
    """Validate writes and return DB-ready records plus per-row errors."""
    known_features: dict[str, bool] = {}
    records: list[dict[str, Any]] = []
    errors: list[OnlineFeatureWriteError] = []

    for index, row in enumerate(rows):
        try:
            entity_json = canonical_entity_key(row.entity_key)
            entity_hash = hashlib.sha256(entity_json.encode("utf-8")).hexdigest()
        except ValueError as exc:
            errors.append(
                OnlineFeatureWriteError(
                    index=index,
                    code="invalid_entity_key",
                    message=str(exc),
                    field="entity_key",
                )
            )
            continue

        if row.feature_ref not in known_features:
            known_features[row.feature_ref] = db.get_feature_by_name(row.feature_ref) is not None
        if not known_features[row.feature_ref]:
            errors.append(
                OnlineFeatureWriteError(
                    index=index,
                    code="unknown_feature_ref",
                    message=f"Feature is not registered: {row.feature_ref}",
                    field="feature_ref",
                )
            )
            continue

        try:
            value_json = _json_dumps(row.value)
        except TypeError as exc:
            errors.append(
                OnlineFeatureWriteError(
                    index=index,
                    code="invalid_feature_value",
                    message=str(exc),
                    field="value",
                )
            )
            continue

        write_id = row.write_id or deterministic_write_id(
            project=project,
            feature_view=feature_view,
            write=row,
            entity_key_json=entity_json,
            value_json=value_json,
        )
        records.append(
            {
                "project": project,
                "feature_view": feature_view,
                "feature_ref": row.feature_ref,
                "entity_key_hash": entity_hash,
                "entity_key_json": entity_json,
                "value_json": value_json,
                "value_dtype": row.value_dtype,
                "event_timestamp": row.event_timestamp,
                "created_timestamp": row.created_timestamp,
                "source_name": row.source_name,
                "source_path": row.source_path,
                "written_at": datetime.now(timezone.utc),
                "write_id": write_id,
            }
        )

    return records, errors


def write_online_features(
    db: CatalogBackend,
    *,
    rows: list[OnlineFeatureWrite],
    project: str = "",
    feature_view: str = "",
) -> OnlineFeatureWriteResult:
    """Validate and write latest online feature values through a backend."""
    return db.write_online_features(rows, project=project, feature_view=feature_view)


def get_online_features(
    db: CatalogBackend,
    *,
    entity_keys: list[dict[str, Any]],
    feature_refs: list[str],
    project: str = "",
    feature_view: str = "",
) -> Any:
    """Read latest online feature values through a backend."""
    return db.get_online_features(
        entity_keys=entity_keys,
        feature_refs=feature_refs,
        project=project,
        feature_view=feature_view,
    )
