"""Redis-backed online feature store.

Key schema
----------
``featcat:online:{project}:{feature_view}:{entity_key_hash}:{feature_ref}``

Value schema (JSON-encoded hash fields stored as a Redis HASH)
--------------------------------------------------------------
- ``value_json``        — serialised feature value (JSON string)
- ``value_dtype``       — dtype tag
- ``event_timestamp``   — ISO-8601 string
- ``created_timestamp`` — ISO-8601 string (or empty)
- ``source_name``       — origin data source name (or empty)
- ``source_path``       — origin file path (or empty)
- ``written_at``        — ISO-8601 write wallclock
- ``write_id``          — deterministic SHA-256 for tie-breaking

Conflict resolution
-------------------
Exactly mirrors the SQL backend in ``local.py``:

1. If ``event_timestamp`` of the incoming write is **older** than the stored
   value → skip (``skipped_older``).
2. If ``event_timestamp`` is **newer** → overwrite.
3. If **equal**, compare ``created_timestamp`` (newer wins).
4. If still equal, compare ``write_id`` lexicographically (larger wins) to
   give a fully deterministic, cross-replica tie-break.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

from .models import (
    OnlineFeatureReadMetadata,
    OnlineFeatureReadResult,
    OnlineFeatureReadRow,
    OnlineFeatureWrite,
    OnlineFeatureWriteError,
    OnlineFeatureWriteResult,
)
from .online_store import canonical_entity_key, deterministic_write_id, entity_key_hash

logger = logging.getLogger(__name__)

# ─── Key helpers ─────────────────────────────────────────────────────────────

_PREFIX = "featcat:online"


def _redis_key(project: str, feature_view: str, entity_hash: str, feature_ref: str) -> str:
    """Return the canonical Redis hash key for a single (entity, feature) slot."""
    return f"{_PREFIX}:{project}:{feature_view}:{entity_hash}:{feature_ref}"


# ─── Datetime helpers ─────────────────────────────────────────────────────────


def _parse_ts(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, AttributeError):
        return None


def _fmt_ts(dt: datetime | None) -> str:
    if dt is None:
        return ""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat()


# ─── Conflict resolution ──────────────────────────────────────────────────────

_SKIP_OLDER = "older_event"
_SKIP_SAME = "same_timestamp"


def _should_overwrite(stored: dict[str, str], incoming: dict[str, Any]) -> tuple[bool, str]:
    """Return (should_write, reason) mirroring LocalBackend._should_overwrite_online_value."""
    stored_event = _parse_ts(stored.get("event_timestamp"))
    incoming_event = incoming["event_timestamp"]
    if isinstance(incoming_event, str):
        incoming_event = _parse_ts(incoming_event)
    if incoming_event is None or stored_event is None:
        return True, ""

    if incoming_event < stored_event:
        return False, _SKIP_OLDER
    if incoming_event > stored_event:
        return True, ""

    # Equal event timestamps → compare created_timestamp
    stored_created = _parse_ts(stored.get("created_timestamp"))
    incoming_created = incoming.get("created_timestamp")
    if isinstance(incoming_created, str):
        incoming_created = _parse_ts(incoming_created)

    if incoming_created is not None and stored_created is not None:
        if incoming_created > stored_created:
            return True, ""
        if incoming_created < stored_created:
            return False, _SKIP_SAME

    # Final tie-break: lexicographic write_id (larger = more recent)
    stored_wid = stored.get("write_id", "")
    incoming_wid = str(incoming.get("write_id", ""))
    if incoming_wid > stored_wid:
        return True, ""
    return False, _SKIP_SAME


# ─── Public helpers ───────────────────────────────────────────────────────────


def get_redis_client(redis_url: str) -> Any:
    """Return a synchronous ``redis.Redis`` client.

    We import ``redis`` lazily so the package is optional — only needed when
    ``FEATCAT_ONLINE_STORE_BACKEND=redis``.
    """
    try:
        import redis as _redis
    except ImportError as exc:
        raise ImportError(
            "The 'redis' package is required for the Redis online store. Install it with: pip install redis"
        ) from exc

    client = _redis.from_url(redis_url, decode_responses=True, socket_connect_timeout=2)
    client.ping()  # fast fail on misconfiguration
    return client


# ─── Write ────────────────────────────────────────────────────────────────────


def write_online_features_redis(
    redis_client: Any,
    *,
    rows: list[OnlineFeatureWrite],
    project: str = "",
    feature_view: str = "",
) -> OnlineFeatureWriteResult:
    """Write feature values to Redis with deterministic conflict resolution.

    Uses a Redis pipeline to batch reads + writes efficiently.  Each
    (entity_key_hash, feature_ref) slot is a Redis HASH containing all
    metadata fields so we can apply the same conflict-resolution logic as
    the SQL backend.
    """
    import json as _json

    result = OnlineFeatureWriteResult(requested=len(rows), errors=[])
    if not rows:
        return result

    # ── Validate rows and build records ──────────────────────────────────────
    records: list[dict[str, Any]] = []
    errors: list[OnlineFeatureWriteError] = []

    for index, row in enumerate(rows):
        if not isinstance(row, OnlineFeatureWrite):
            row = OnlineFeatureWrite.model_validate(row)

        try:
            entity_json = canonical_entity_key(row.entity_key)
            entity_hash = entity_key_hash(row.entity_key)
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

        try:
            value_json = _json.dumps(row.value, sort_keys=True, separators=(",", ":"))
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
                "index": index,
                "redis_key": _redis_key(project, feature_view, entity_hash, row.feature_ref),
                "value_json": value_json,
                "value_dtype": row.value_dtype or "",
                "event_timestamp": _fmt_ts(row.event_timestamp),
                "created_timestamp": _fmt_ts(row.created_timestamp),
                "source_name": row.source_name or "",
                "source_path": row.source_path or "",
                "written_at": _fmt_ts(datetime.now(timezone.utc)),
                "write_id": write_id,
            }
        )

    result.errors = errors

    if not records:
        return result

    # ── Batch fetch existing values ───────────────────────────────────────────
    pipe = redis_client.pipeline(transaction=False)
    for rec in records:
        pipe.hgetall(rec["redis_key"])
    existing_list: list[dict[str, str]] = pipe.execute()

    # ── Apply conflict resolution and write winners ───────────────────────────
    write_pipe = redis_client.pipeline(transaction=False)
    any_write = False

    for rec, existing in zip(records, existing_list, strict=False):
        if not existing:
            # New slot — write unconditionally
            write_pipe.hset(rec["redis_key"], mapping={k: v for k, v in rec.items() if k not in ("index", "redis_key")})
            result.written += 1
            any_write = True
            continue

        should_write, reason = _should_overwrite(existing, rec)
        if not should_write:
            if reason == _SKIP_OLDER:
                result.skipped_older += 1
            else:
                result.skipped_same_timestamp += 1
            continue

        write_pipe.hset(rec["redis_key"], mapping={k: v for k, v in rec.items() if k not in ("index", "redis_key")})
        result.written += 1
        any_write = True

    if any_write:
        write_pipe.execute()

    return result


# ─── Read ─────────────────────────────────────────────────────────────────────


def get_online_features_redis(
    redis_client: Any,
    *,
    entity_keys: list[dict[str, Any]],
    feature_refs: list[str],
    project: str = "",
    feature_view: str = "",
) -> OnlineFeatureReadResult:
    """Read latest online feature values from Redis.

    Issues a single pipelined HGET per (entity, feature_ref) pair for
    minimum round-trip latency.
    """
    from .online_store import canonical_entity_key as _canonical
    from .online_store import entity_key_hash as _hash

    canonical_entities: list[tuple[dict, str, str]] = []
    for entity_key in entity_keys:
        try:
            canonical_entities.append((entity_key, _canonical(entity_key), _hash(entity_key)))
        except ValueError as exc:
            raise exc

    if not canonical_entities or not feature_refs:
        return OnlineFeatureReadResult(
            rows=[
                OnlineFeatureReadRow(
                    entity_key=ek,
                    features={fr: None for fr in feature_refs},
                    metadata={fr: OnlineFeatureReadMetadata(found=False) for fr in feature_refs},
                )
                for ek, _, _ in canonical_entities
            ]
        )

    # Build ordered list of (entity_idx, feature_ref) → redis_key
    lookups: list[tuple[int, str, str]] = []
    for idx, (_ek, _ej, eh) in enumerate(canonical_entities):
        for fr in feature_refs:
            lookups.append((idx, fr, _redis_key(project, feature_view, eh, fr)))

    # Single pipeline fetch
    pipe = redis_client.pipeline(transaction=False)
    for _idx, _fr, rkey in lookups:
        pipe.hgetall(rkey)
    fetched: list[dict[str, str]] = pipe.execute()

    # Build results
    by_entity_feature: dict[tuple[int, str], dict[str, str] | None] = {}
    for (idx, fr, _rkey), stored in zip(lookups, fetched, strict=False):
        by_entity_feature[(idx, fr)] = stored if stored else None

    result_rows: list[OnlineFeatureReadRow] = []
    for entity_idx, (entity_key, _ej, _eh) in enumerate(canonical_entities):
        features: dict[str, Any] = {}
        metadata: dict[str, OnlineFeatureReadMetadata] = {}
        for fr in feature_refs:
            stored_value = by_entity_feature.get((entity_idx, fr))
            if stored_value is None:
                features[fr] = None
                metadata[fr] = OnlineFeatureReadMetadata(found=False)
                continue

            raw_value = stored_value.get("value_json")
            try:
                features[fr] = json.loads(raw_value) if raw_value is not None else None
            except (json.JSONDecodeError, TypeError):
                features[fr] = raw_value

            metadata[fr] = OnlineFeatureReadMetadata(
                found=True,
                event_timestamp=_parse_ts(stored_value.get("event_timestamp")),
            )

        result_rows.append(OnlineFeatureReadRow(entity_key=entity_key, features=features, metadata=metadata))

    return OnlineFeatureReadResult(rows=result_rows)
