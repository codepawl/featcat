"""Catalog backend — SQLAlchemy-based, runs on SQLite or PostgreSQL.

Phase history:

- Phase 1 introduced SQLAlchemy + Alembic for engine/schema management.
- Phase 2 wired PostgreSQL via ``FEATCAT_DB_BACKEND=postgres`` plus the
  migration script and Docker compose service.
- Phase 2.5 ported the ~60 catalog query methods off the raw ``sqlite3``
  connection to portable ``Session.execute(text(...))`` queries.
- **Phase 3 (this file)** ports the remaining ~30 raw-conn callers in
  scheduler, routes, and CLI; removes the legacy ``self.conn`` raw
  ``sqlite3.Connection`` exposure entirely; drops the
  ``_NoRawConnInPostgresMode`` sentinel (no callers); drops the
  module-level ``sqlite3.register_adapter``/``register_converter`` hooks
  (only fired on the legacy raw conn). LocalBackend is now a single
  SA-engine-driven path that runs identically on either backend.

``ResponseCache`` (``featcat/utils/cache.py``) keeps its own raw sqlite3
connection — that's an intentional local-only cache, not part of the
catalog DB.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import bindparam, text
from sqlalchemy.exc import OperationalError

from ..db.connection import make_engine, make_session_factory, resolve_backend
from ..db.models import Base
from .backend import CatalogBackend
from .models import DataSource, Feature, FeatureGroup, FeatureGroupVersion, ScanLog, _new_id

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

DEFAULT_DB = "catalog.db"


def _name_tokens(name: str) -> set[str]:
    return {t for t in name.replace(".", "_").split("_") if t}


def _jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def _parse_stats(raw: Any) -> dict:
    """Normalize a feature's ``stats`` column into a dict.

    The column may be a JSON string, an already-parsed dict, or absent. Returns
    ``{}`` for any unparseable / missing input so downstream callers can do
    ``.get("mean")`` without guarding.
    """
    if isinstance(raw, str) and raw:
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    if isinstance(raw, dict):
        return raw
    return {}


def _compute_pair_reasons(
    name_a: str,
    dtype_a: str | None,
    stats_a: dict,
    name_b: str,
    dtype_b: str | None,
    stats_b: dict,
    score: float,
) -> list[dict]:
    """Build the reason-code breakdown for a pair of features.

    Always emits ``semantic_match`` (the TF-IDF cosine score). Adds
    ``name_similarity`` when name-token Jaccard ≥ 0.5, ``schema_match`` when
    dtypes match, and ``distribution_match`` when both features carry numeric
    mean+std within 10% relative tolerance. Pre-parsed ``stats_a`` / ``stats_b``
    avoid re-parsing the JSON column on every pair.
    """
    reasons: list[dict] = [{"code": "semantic_match", "detail": f"TF-IDF cosine {round(score, 3)}"}]
    tokens_a = _name_tokens(name_a)
    tokens_b = _name_tokens(name_b)
    if _jaccard(tokens_a, tokens_b) >= 0.5:
        shared = sorted(tokens_a & tokens_b)
        reasons.append({"code": "name_similarity", "detail": "shared tokens: " + ", ".join(shared)})
    if dtype_a and dtype_a == dtype_b:
        reasons.append({"code": "schema_match", "detail": f"both {dtype_a}"})
    mean_a, mean_b = stats_a.get("mean"), stats_b.get("mean")
    std_a, std_b = stats_a.get("std"), stats_b.get("std")
    if (
        isinstance(mean_a, (int, float))
        and isinstance(mean_b, (int, float))
        and isinstance(std_a, (int, float))
        and isinstance(std_b, (int, float))
    ):

        def _rel_delta(x: float, y: float) -> float:
            denom = max(abs(x), abs(y), 1e-9)
            return abs(x - y) / denom

        m_delta = _rel_delta(float(mean_a), float(mean_b))
        s_delta = _rel_delta(float(std_a), float(std_b))
        if m_delta <= 0.10 and s_delta <= 0.10:
            reasons.append(
                {
                    "code": "distribution_match",
                    "detail": f"mean Δ={m_delta:.0%}, std Δ={s_delta:.0%}",
                }
            )
    return reasons


# Override sqlite3's built-in datetime adapter (deprecated in Python 3.12+).
# SA's sqlite dialect bind-converts datetime → str via this adapter when
# inserting; without an explicit registration each datetime bind emits a
# ``DeprecationWarning: The default datetime adapter is deprecated``.
# ``isoformat()`` matches SA's read-side parser so tz-aware datetimes round-trip
# correctly (postgres' TIMESTAMPTZ preserves tz natively).
def _adapt_datetime_iso(val: datetime) -> str:
    return val.isoformat()


sqlite3.register_adapter(datetime, _adapt_datetime_iso)


def _row_to_feature(row: Any) -> Feature:
    """Convert a row to a Feature.

    Accepts ``sqlite3.Row``, SQLAlchemy ``RowMapping``, or plain dict — all
    support ``dict(row)`` conversion. Typed as ``Any`` to avoid pulling
    SQLAlchemy types into the public surface.
    """
    d = dict(row)
    d["tags"] = json.loads(d["tags"]) if isinstance(d.get("tags"), str) else (d.get("tags") or [])
    d["stats"] = json.loads(d["stats"]) if isinstance(d.get("stats"), str) else (d.get("stats") or {})
    # Provide defaults for required fields that might be None from schema mismatches
    d.setdefault("id", "")
    d.setdefault("name", "")
    d.setdefault("data_source_id", "")
    d.setdefault("column_name", "")
    d.setdefault("dtype", "unknown")
    d.setdefault("description", "")
    d.setdefault("owner", "")
    if d.get("dtype") is None:
        d["dtype"] = "unknown"
    if d.get("description") is None:
        d["description"] = ""
    if d.get("owner") is None:
        d["owner"] = ""
    # Filter out any extra columns not in the Feature model (e.g. from ALTER TABLE)
    valid_fields = Feature.model_fields
    d = {k: v for k, v in d.items() if k in valid_fields}
    return Feature(**d)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class LocalBackend(CatalogBackend):
    """Catalog backend backed by SQLite (default) or PostgreSQL."""

    def __init__(self, db_path: str = DEFAULT_DB) -> None:
        self.db_path = db_path
        # Backend resolution — driven by FEATCAT_DB_BACKEND env var. Tests and
        # default dev/CI runs leave it unset → "sqlite". Production deploys set
        # "postgres".
        self.backend = resolve_backend()
        self.engine = make_engine(backend=self.backend, db_path=db_path)
        self.session_factory = make_session_factory(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """Yield a SQLAlchemy Session bound to this backend's engine.

        Caller is responsible for committing; the context manager closes the
        session on exit. All ported methods below use this internally.
        """
        s = self.session_factory()
        try:
            yield s
        finally:
            s.close()

    def init_db(self) -> None:
        Base.metadata.create_all(self.engine, checkfirst=True)
        # Backward-compat ALTER TABLE migrations for sqlite catalogs created
        # before these columns existed. Sqlite-only — postgres has no legacy
        # schema (operators bring up postgres via Alembic). Each ALTER is
        # idempotent: ``OperationalError`` fires when the column already exists.
        if self.backend != "sqlite":
            return
        legacy_alters = (
            "ALTER TABLE data_sources ADD COLUMN auto_refresh INTEGER DEFAULT 0",
            "ALTER TABLE features ADD COLUMN definition TEXT",
            "ALTER TABLE features ADD COLUMN definition_type TEXT",
            "ALTER TABLE features ADD COLUMN definition_updated_at TIMESTAMP",
            "ALTER TABLE features ADD COLUMN generation_hints TEXT",
            # T3.1 lifecycle status — fields land on existing rows with
            # 'draft' so /api/features/stats/status-counts doesn't 500 on
            # legacy catalogs.
            "ALTER TABLE features ADD COLUMN status TEXT NOT NULL DEFAULT 'draft'",
            "ALTER TABLE features ADD COLUMN status_changed_at TIMESTAMP",
            "ALTER TABLE features ADD COLUMN status_notes TEXT",
            "ALTER TABLE feature_docs ADD COLUMN hints_used TEXT",
            "ALTER TABLE feature_docs ADD COLUMN context_features TEXT",
            "ALTER TABLE feature_versions ADD COLUMN change_type TEXT DEFAULT 'metadata'",
            "ALTER TABLE feature_versions ADD COLUMN previous_value TEXT",
            "ALTER TABLE feature_versions ADD COLUMN new_value TEXT",
            # T1.1 lineage widening — parent can be a raw source column instead
            # of (or in addition to) another feature. detected_method tracks how
            # the row was recorded. Without these, /api/lineage/full 500s.
            "ALTER TABLE feature_lineage ADD COLUMN parent_type TEXT NOT NULL DEFAULT 'feature'",
            "ALTER TABLE feature_lineage ADD COLUMN parent_source_id TEXT",
            "ALTER TABLE feature_lineage ADD COLUMN parent_column TEXT",
            "ALTER TABLE feature_lineage ADD COLUMN transform TEXT NOT NULL DEFAULT ''",
            "ALTER TABLE feature_lineage ADD COLUMN detected_method TEXT NOT NULL DEFAULT 'manual'",
            "ALTER TABLE monitoring_checks ADD COLUMN llm_analysis_json TEXT",
            # Per-check metrics for the multi-metric feature chart. Legacy rows
            # stay NULL; only post-migration checks populate these.
            "ALTER TABLE monitoring_checks ADD COLUMN null_ratio REAL",
            "ALTER TABLE monitoring_checks ADD COLUMN mean_z_score REAL",
            "ALTER TABLE monitoring_checks ADD COLUMN sample_size INTEGER",
            # Composite indexes for chart queries (feature timeline, catalog
            # drift-rate). CREATE INDEX IF NOT EXISTS is itself idempotent but
            # the suppress(OperationalError) wrapper covers older sqlites.
            "CREATE INDEX IF NOT EXISTS idx_monitoring_checks_feature_date "
            "ON monitoring_checks(feature_id, checked_at)",
            "CREATE INDEX IF NOT EXISTS idx_monitoring_checks_date_severity ON monitoring_checks(checked_at, severity)",
        )
        with self.engine.begin() as conn:
            for stmt in legacy_alters:
                with contextlib.suppress(OperationalError):
                    conn.execute(text(stmt))

    def close(self) -> None:
        self.engine.dispose()

    # --- Sources ---

    def add_source(self, source: DataSource) -> DataSource:
        with self.session() as s:
            s.execute(
                text(
                    "INSERT INTO data_sources (id, name, path, storage_type, format, description, "
                    "created_at, updated_at) "
                    "VALUES (:id, :name, :path, :storage_type, :format, :description, :created_at, :updated_at)"
                ),
                {
                    "id": source.id,
                    "name": source.name,
                    "path": source.path,
                    "storage_type": source.storage_type,
                    "format": source.format,
                    "description": source.description,
                    "created_at": source.created_at,
                    "updated_at": source.updated_at,
                },
            )
            s.commit()
        return source

    def get_source_by_name(self, name: str) -> DataSource | None:
        with self.session() as s:
            row = s.execute(text("SELECT * FROM data_sources WHERE name = :name"), {"name": name}).mappings().first()
            return DataSource(**dict(row)) if row else None

    def list_sources(self) -> list[DataSource]:
        with self.session() as s:
            rows = s.execute(text("SELECT * FROM data_sources ORDER BY created_at DESC")).mappings().all()
            return [DataSource(**dict(r)) for r in rows]

    def get_source_by_path(self, path: str) -> DataSource | None:
        with self.session() as s:
            row = s.execute(text("SELECT * FROM data_sources WHERE path = :path"), {"path": path}).mappings().first()
            return DataSource(**dict(row)) if row else None

    def update_source(
        self,
        name: str,
        *,
        description: str | None = None,
        format: str | None = None,  # noqa: A002 — mirrors DataSource.format
    ) -> DataSource:
        """Update mutable metadata. Path/storage_type/name are immutable —
        renaming would invalidate every dependent feature's name prefix.

        Raises ``KeyError`` if the source doesn't exist; returns the
        refreshed model on success.
        """
        source = self.get_source_by_name(name)
        if source is None:
            raise KeyError(f"Source not found: {name}")
        sets: list[str] = []
        params: dict[str, Any] = {"id": source.id, "now": _utcnow()}
        if description is not None:
            sets.append("description = :description")
            params["description"] = description
        if format is not None:
            sets.append("format = :format")
            params["format"] = format
        if not sets:
            return source  # no-op
        sets.append("updated_at = :now")
        with self.session() as s:
            s.execute(text(f"UPDATE data_sources SET {', '.join(sets)} WHERE id = :id"), params)
            s.commit()
        # Re-read so caller sees the persisted row (and the new updated_at).
        refreshed = self.get_source_by_name(name)
        assert refreshed is not None  # we just verified existence above
        return refreshed

    def delete_source(self, name: str) -> int:
        """Hard-delete a source and cascade-remove its features.

        Reuses :meth:`bulk_delete_features` which already cleans every
        non-cascade child table (feature_docs, monitoring_baselines,
        monitoring_checks, usage_log) and lets the FK-cascade tables
        (feature_versions, feature_group_members, feature_lineage,
        action_items) clean themselves. Once features are gone the
        ``data_sources`` row deletes cleanly. Returns the number of
        features removed; raises ``KeyError`` if the source is missing.
        """
        source = self.get_source_by_name(name)
        if source is None:
            raise KeyError(f"Source not found: {name}")
        with self.session() as s:
            feature_ids = [
                r[0]
                for r in s.execute(
                    text("SELECT id FROM features WHERE data_source_id = :sid"),
                    {"sid": source.id},
                ).all()
            ]
        # bulk_delete_features handles its own session + the non-cascade
        # child cleanup. Calling it here keeps the cascade logic in one place.
        removed = self.bulk_delete_features(feature_ids) if feature_ids else 0
        with self.session() as s:
            s.execute(text("DELETE FROM data_sources WHERE id = :id"), {"id": source.id})
            s.commit()
        return removed

    def get_source_impact(self, name: str) -> dict:
        """Compute pre-delete impact: feature count + groups using those features.

        Returns ``{features_count, groups: [{name, feature_count}]}``. The
        UI's delete-confirmation modal renders these so the user sees the
        blast radius before confirming.
        """
        source = self.get_source_by_name(name)
        if source is None:
            return {"features_count": 0, "groups": []}
        with self.session() as s:
            features_count = int(
                s.execute(
                    text("SELECT COUNT(*) FROM features WHERE data_source_id = :sid"),
                    {"sid": source.id},
                ).scalar()
                or 0
            )
            group_rows = (
                s.execute(
                    text(
                        "SELECT g.name AS name, COUNT(*) AS feature_count "
                        "FROM feature_group_members gm "
                        "JOIN features f ON f.id = gm.feature_id "
                        "JOIN feature_groups g ON g.id = gm.group_id "
                        "WHERE f.data_source_id = :sid "
                        "GROUP BY g.id, g.name "
                        "ORDER BY g.name"
                    ),
                    {"sid": source.id},
                )
                .mappings()
                .all()
            )
        return {
            "features_count": features_count,
            "groups": [{"name": r["name"], "feature_count": int(r["feature_count"])} for r in group_rows],
        }

    def record_scan_log(
        self,
        source_id: str,
        *,
        started_at: datetime,
        finished_at: datetime,
        duration_seconds: float,
        status: str,
        files_scanned: int = 0,
        features_added: int = 0,
        features_updated: int = 0,
        features_removed: int = 0,
        error_message: str | None = None,
        triggered_by: str = "api",
    ) -> str:
        """Insert one scan-attempt audit row. Returns the new log id."""
        log_id = _new_id()
        with self.session() as s:
            s.execute(
                text(
                    "INSERT INTO scan_logs (id, source_id, started_at, finished_at, "
                    " duration_seconds, files_scanned, features_added, features_updated, "
                    " features_removed, status, error_message, triggered_by) "
                    "VALUES (:id, :source_id, :started_at, :finished_at, "
                    "        :duration_seconds, :files_scanned, :features_added, "
                    "        :features_updated, :features_removed, :status, "
                    "        :error_message, :triggered_by)"
                ),
                {
                    "id": log_id,
                    "source_id": source_id,
                    "started_at": started_at,
                    "finished_at": finished_at,
                    "duration_seconds": duration_seconds,
                    "files_scanned": files_scanned,
                    "features_added": features_added,
                    "features_updated": features_updated,
                    "features_removed": features_removed,
                    "status": status,
                    "error_message": error_message,
                    "triggered_by": triggered_by,
                },
            )
            s.commit()
        return log_id

    def list_scan_logs(self, source_id: str, limit: int = 10) -> list[ScanLog]:
        """Return scan-attempt rows for a source, newest first."""
        with self.session() as s:
            rows = (
                s.execute(
                    text("SELECT * FROM scan_logs WHERE source_id = :sid ORDER BY started_at DESC LIMIT :limit"),
                    {"sid": source_id, "limit": limit},
                )
                .mappings()
                .all()
            )
        return [ScanLog(**dict(r)) for r in rows]

    # --- Features ---

    def upsert_feature(self, feature: Feature) -> Feature:
        with self.session() as s:
            existing = s.execute(
                text("SELECT id FROM features WHERE data_source_id = :sid AND column_name = :col"),
                {"sid": feature.data_source_id, "col": feature.column_name},
            ).first()
            is_new = existing is None
            s.execute(
                text(
                    "INSERT INTO features "
                    "(id, name, data_source_id, column_name, dtype, description, tags, owner, stats, "
                    " created_at, updated_at) "
                    "VALUES (:id, :name, :sid, :col, :dtype, :description, :tags, :owner, :stats, "
                    "        :created_at, :updated_at) "
                    "ON CONFLICT(data_source_id, column_name) DO UPDATE SET "
                    "  dtype = excluded.dtype, "
                    "  stats = excluded.stats, "
                    "  updated_at = excluded.updated_at"
                ),
                {
                    "id": feature.id,
                    "name": feature.name,
                    "sid": feature.data_source_id,
                    "col": feature.column_name,
                    "dtype": feature.dtype,
                    "description": feature.description,
                    "tags": json.dumps(feature.tags),
                    "owner": feature.owner,
                    "stats": json.dumps(feature.stats),
                    "created_at": feature.created_at,
                    "updated_at": feature.updated_at,
                },
            )
            s.commit()

        if is_new:
            source_name = feature.name.split(".")[0] if "." in feature.name else ""
            self._snapshot_feature(
                feature.id,
                {"source": ("", source_name), "column": ("", feature.column_name), "dtype": ("", feature.dtype)},
                changed_by=feature.owner or "system",
                change_type="metadata",
            )
            with self.session() as s:
                s.execute(
                    text(
                        "UPDATE feature_versions SET change_summary = :summary WHERE feature_id = :fid AND version = 1"
                    ),
                    {"summary": "Initial registration via scan", "fid": feature.id},
                )
                s.commit()

        return feature

    # Allowlist for sort + order — guards against SQL injection on the f-string
    # below (the values come from query params).
    _SORT_COLUMNS = frozenset({"name", "created_at", "updated_at", "dtype"})
    _SORT_ORDERS = frozenset({"asc", "desc"})

    def _features_filter_clauses(
        self,
        *,
        source_name: str | None,
        dtype: str | None,
        owner: str | None,
        tag: str | None,
        search: str | None,
        has_doc: bool | None,
    ) -> tuple[list[str], dict[str, Any]]:
        """Build WHERE clauses + params shared by list_features and count_features."""
        clauses: list[str] = []
        params: dict[str, Any] = {}
        join_sources = source_name is not None
        if source_name:
            clauses.append("ds.name = :source_name")
            params["source_name"] = source_name
        if dtype:
            clauses.append("f.dtype = :dtype")
            params["dtype"] = dtype
        if owner:
            clauses.append("f.owner = :owner")
            params["owner"] = owner
        if tag:
            clauses.append("f.tags LIKE :tag_pattern")
            params["tag_pattern"] = f'%"{tag}"%'
        if search:
            clauses.append(
                "(f.name LIKE :search OR f.description LIKE :search "
                "OR f.tags LIKE :search OR f.column_name LIKE :search)"
            )
            params["search"] = f"%{search}%"
        if has_doc is True:
            clauses.append(
                "EXISTS (SELECT 1 FROM feature_docs fd WHERE fd.feature_id = f.id "
                "AND fd.short_description IS NOT NULL AND fd.short_description != '')"
            )
        elif has_doc is False:
            clauses.append(
                "NOT EXISTS (SELECT 1 FROM feature_docs fd WHERE fd.feature_id = f.id "
                "AND fd.short_description IS NOT NULL AND fd.short_description != '')"
            )
        # Always join data_sources when source_name filter is in play; otherwise
        # the FROM clause stays single-table for the query planner.
        params["_join_sources"] = join_sources  # signal to caller (popped before binding)
        return clauses, params

    def list_features(
        self,
        source_name: str | None = None,
        *,
        dtype: str | None = None,
        owner: str | None = None,
        tag: str | None = None,
        search: str | None = None,
        has_doc: bool | None = None,
        sort: str = "name",
        order: str = "asc",
        limit: int | None = None,
        offset: int = 0,
    ) -> list[Feature]:
        """Return features matching the given filters with optional pagination.

        Backward-compat: called with no kwargs, returns the full sorted list as
        before. ``limit=None`` means "no LIMIT" — caller handles pagination by
        passing ``limit=N, offset=M``.

        ``sort`` / ``order`` are validated against the allowlist defined above
        and interpolated as identifiers; do NOT pass user-supplied values
        directly through other paths.
        """
        if sort not in self._SORT_COLUMNS:
            raise ValueError(f"sort must be one of {sorted(self._SORT_COLUMNS)}, got {sort!r}")
        if order not in self._SORT_ORDERS:
            raise ValueError(f"order must be one of {sorted(self._SORT_ORDERS)}, got {order!r}")
        clauses, params = self._features_filter_clauses(
            source_name=source_name, dtype=dtype, owner=owner, tag=tag, search=search, has_doc=has_doc
        )
        join_sources = params.pop("_join_sources")
        join_clause = "JOIN data_sources ds ON f.data_source_id = ds.id" if join_sources else ""
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        limit_clause = ""
        if limit is not None:
            limit_clause = "LIMIT :limit OFFSET :offset"
            params["limit"] = int(limit)
            params["offset"] = int(offset)
        sql = (
            f"SELECT f.* FROM features f {join_clause} {where_clause} "  # noqa: S608
            f"ORDER BY f.{sort} {order.upper()} {limit_clause}"
        )
        with self.session() as s:
            rows = s.execute(text(sql), params).mappings().all()
            return [_row_to_feature(r) for r in rows]

    def count_features(
        self,
        source_name: str | None = None,
        *,
        dtype: str | None = None,
        owner: str | None = None,
        tag: str | None = None,
        search: str | None = None,
        has_doc: bool | None = None,
    ) -> int:
        """Count features matching the same filters as ``list_features``.

        Used by paginated endpoints to populate the ``total`` envelope field
        without round-tripping the full result set.
        """
        clauses, params = self._features_filter_clauses(
            source_name=source_name, dtype=dtype, owner=owner, tag=tag, search=search, has_doc=has_doc
        )
        join_sources = params.pop("_join_sources")
        join_clause = "JOIN data_sources ds ON f.data_source_id = ds.id" if join_sources else ""
        where_clause = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT COUNT(*) FROM features f {join_clause} {where_clause}"  # noqa: S608
        with self.session() as s:
            return int(s.execute(text(sql), params).scalar() or 0)

    def get_feature_by_name(self, name: str) -> Feature | None:
        with self.session() as s:
            row = s.execute(text("SELECT * FROM features WHERE name = :name"), {"name": name}).mappings().first()
            return _row_to_feature(row) if row else None

    _VERSIONED_FIELDS = frozenset({"description", "tags", "owner", "dtype", "column_name", "data_source_id"})

    def _snapshot_feature(
        self,
        feature_id: str,
        changes: dict[str, tuple],
        changed_by: str = "",
        change_type: str = "metadata",
    ) -> None:
        with self.session() as s:
            row = s.execute(text("SELECT * FROM features WHERE id = :id"), {"id": feature_id}).mappings().first()
            if row is None:
                return
            snapshot = dict(row)
            raw_tags = snapshot.get("tags")
            snapshot["tags"] = json.loads(raw_tags) if isinstance(raw_tags, str) else (raw_tags or [])
            raw_stats = snapshot.get("stats")
            snapshot["stats"] = json.loads(raw_stats) if isinstance(raw_stats, str) else (raw_stats or {})
            for k, v in snapshot.items():
                if isinstance(v, datetime):
                    snapshot[k] = v.isoformat()
            next_version = s.execute(
                text("SELECT COALESCE(MAX(version), 0) + 1 FROM feature_versions WHERE feature_id = :fid"),
                {"fid": feature_id},
            ).scalar()
            parts = [f"{field}: {old!r} -> {new!r}" for field, (old, new) in changes.items()]
            prev_val = {field: old for field, (old, _new) in changes.items()}
            new_val = {field: new for field, (_old, new) in changes.items()}
            s.execute(
                text(
                    "INSERT INTO feature_versions "
                    "(id, feature_id, version, snapshot, change_summary, changed_by, created_at, "
                    " change_type, previous_value, new_value) "
                    "VALUES (:id, :fid, :version, :snapshot, :summary, :changed_by, :created_at, "
                    "        :change_type, :prev, :new)"
                ),
                {
                    "id": _new_id(),
                    "fid": feature_id,
                    "version": next_version,
                    "snapshot": json.dumps(snapshot),
                    "summary": "; ".join(parts),
                    "changed_by": changed_by,
                    "created_at": _utcnow(),
                    "change_type": change_type,
                    "prev": json.dumps(prev_val, default=str),
                    "new": json.dumps(new_val, default=str),
                },
            )
            s.commit()

    def update_feature_metadata(self, feature_id: str, _rollback_version: int | None = None, **kwargs) -> None:
        with self.session() as s:
            row = s.execute(text("SELECT * FROM features WHERE id = :id"), {"id": feature_id}).mappings().first()
            if row is None:
                return
            current = dict(row)
            raw_tags = current.get("tags")
            current["tags"] = json.loads(raw_tags) if isinstance(raw_tags, str) else (raw_tags or [])
            changes: dict[str, tuple] = {}
            for field in self._VERSIONED_FIELDS:
                if field not in kwargs:
                    continue
                old_val = current.get(field)
                new_val = kwargs[field]
                if old_val != new_val:
                    changes[field] = (old_val, new_val)
            if not changes:
                return

        # Snapshot uses its own session; do it before the update so the version
        # row records the pre-update state.
        ct = "tags" if set(changes) == {"tags"} else "metadata"
        self._snapshot_feature(
            feature_id,
            changes,
            changed_by=kwargs.get("owner") or current.get("owner") or "",
            change_type=ct,
        )

        with self.session() as s:
            if _rollback_version is not None:
                s.execute(
                    text(
                        "UPDATE feature_versions "
                        "SET change_summary = 'rollback to v' || :ver || ': ' || change_summary "
                        "WHERE feature_id = :fid "
                        "  AND version = (SELECT MAX(version) FROM feature_versions WHERE feature_id = :fid)"
                    ),
                    {"ver": str(_rollback_version), "fid": feature_id},
                )
            sets: list[str] = []
            params: dict[str, Any] = {"id": feature_id}
            for k, v in kwargs.items():
                if k.startswith("_"):
                    continue
                if k == "tags":
                    sets.append("tags = :tags")
                    params["tags"] = json.dumps(v)
                elif k in self._VERSIONED_FIELDS:
                    sets.append(f"{k} = :{k}")
                    params[k] = v
            if sets:
                sets.append("updated_at = :updated_at")
                params["updated_at"] = _utcnow()
                s.execute(text(f"UPDATE features SET {', '.join(sets)} WHERE id = :id"), params)  # noqa: S608
            s.commit()

    def update_feature_tags(self, feature_id: str, tags: list[str]) -> None:
        self.update_feature_metadata(feature_id, tags=tags)

    def full_text_search(
        self,
        query: str,
        *,
        source: str | None = None,
        tag: str | None = None,
        dtype: str | None = None,
        has_doc: bool | None = None,
        limit: int = 50,
    ) -> list[dict]:
        """Postgres tsvector + ranking on postgres; LIKE fallback on sqlite (T2.2a).

        Returns ``[{id, name, dtype, source, rank, snippet}]`` sorted by
        relevance descending. ``rank`` is ``ts_rank`` value on postgres
        (higher = better) or a synthetic 0..1 score on sqlite based on
        how many of the query tokens appear in the searchable text.

        Filters all push down to SQL on both backends.
        """
        if not query.strip():
            return []
        if self.backend == "postgres":
            return self._fts_postgres(query, source, tag, dtype, has_doc, limit)
        return self._fts_sqlite(query, source, tag, dtype, has_doc, limit)

    def _fts_postgres(
        self,
        q: str,
        source: str | None,
        tag: str | None,
        dtype: str | None,
        has_doc: bool | None,
        limit: int,
    ) -> list[dict]:
        clauses = ["f.search_vector @@ plainto_tsquery('simple', :q)"]
        params: dict[str, Any] = {"q": q, "lim": limit}
        joins = "JOIN data_sources ds ON f.data_source_id = ds.id"
        if source:
            clauses.append("ds.name = :source")
            params["source"] = source
        if tag:
            clauses.append("f.tags LIKE :tagp")
            params["tagp"] = f'%"{tag}"%'
        if dtype:
            clauses.append("f.dtype = :dtype")
            params["dtype"] = dtype
        if has_doc is True:
            clauses.append(
                "EXISTS (SELECT 1 FROM feature_docs fd WHERE fd.feature_id = f.id "
                "AND fd.short_description IS NOT NULL AND fd.short_description != '')"
            )
        elif has_doc is False:
            clauses.append(
                "NOT EXISTS (SELECT 1 FROM feature_docs fd WHERE fd.feature_id = f.id "
                "AND fd.short_description IS NOT NULL AND fd.short_description != '')"
            )
        where = " AND ".join(clauses)
        sql = (
            f"SELECT f.id, f.name, f.dtype, ds.name AS source_name, "  # noqa: S608
            f"       ts_rank(f.search_vector, plainto_tsquery('simple', :q)) AS rank "
            f"FROM features f {joins} WHERE {where} "
            f"ORDER BY rank DESC LIMIT :lim"
        )
        with self.session() as s:
            rows = s.execute(text(sql), params).mappings().all()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "dtype": r["dtype"],
                "source": r["source_name"],
                "rank": float(r["rank"]),
            }
            for r in rows
        ]

    def _fts_sqlite(
        self,
        q: str,
        source: str | None,
        tag: str | None,
        dtype: str | None,
        has_doc: bool | None,
        limit: int,
    ) -> list[dict]:
        """Sqlite fallback — tokenizes the query and counts matches across
        name/description/tags/column_name to produce a synthetic rank. Slower
        than postgres FTS but doesn't require a special index."""
        tokens = [t for t in q.lower().split() if t]
        if not tokens:
            return []
        # Reuse list_features filter pushdown for source/dtype/has_doc, then
        # rank in Python. Pull source name via join.
        feats = self.list_features(source_name=source, dtype=dtype, has_doc=has_doc, tag=tag, limit=None)
        scored: list[tuple[float, Feature]] = []
        for f in feats:
            haystack = " ".join(
                [
                    f.name.lower(),
                    f.description.lower(),
                    " ".join(f.tags).lower(),
                    f.column_name.lower(),
                ]
            )
            hits = sum(1 for tok in tokens if tok in haystack)
            if hits == 0:
                continue
            # Higher = better. Bonus when the name contains the query verbatim.
            score = hits / len(tokens)
            if q.lower() in f.name.lower():
                score += 0.5
            scored.append((score, f))
        scored.sort(key=lambda pair: pair[0], reverse=True)
        results: list[dict] = []
        for score, f in scored[:limit]:
            results.append(
                {
                    "id": f.id,
                    "name": f.name,
                    "dtype": f.dtype,
                    "source": f.name.split(".")[0] if "." in f.name else "",
                    "rank": round(score, 4),
                }
            )
        return results

    def search_facets(
        self,
        query: str | None = None,
        *,
        source: str | None = None,
        tag: str | None = None,
        dtype: str | None = None,
        has_doc: bool | None = None,
    ) -> dict[str, Any]:
        """Faceted counts for the search UI sidebar (T2.2a).

        Returns ``{sources: [{name, count}], tags: [...], dtypes: [...],
        has_doc: {true, false}}``. Each facet is computed against the same
        filter set as the search itself (so applying a filter narrows the
        other facet counts as expected).
        """
        feats = (
            self.full_text_search(
                query,
                source=source,
                tag=tag,
                dtype=dtype,
                has_doc=has_doc,
                limit=10_000,  # facets need full set, not paginated slice
            )
            if query
            else [
                {"id": f.id, "name": f.name, "dtype": f.dtype, "source": f.name.split(".")[0]}
                for f in self.list_features(source_name=source, dtype=dtype, tag=tag, has_doc=has_doc, limit=None)
            ]
        )
        ids = [f["id"] for f in feats]
        from collections import Counter

        # Source + dtype facets we already have on the rows.
        src_counts = Counter(f["source"] for f in feats if f.get("source"))
        dtype_counts = Counter(f["dtype"] for f in feats if f.get("dtype"))
        # Tag + has_doc facets need a second look at the full feature rows.
        tags_counter: Counter = Counter()
        has_doc_counts = {"true": 0, "false": 0}
        if ids:
            from sqlalchemy import bindparam

            with self.session() as s:
                rows = (
                    s.execute(
                        text(
                            "SELECT f.id, f.tags, "
                            "       (CASE WHEN EXISTS ("
                            "         SELECT 1 FROM feature_docs fd "
                            "         WHERE fd.feature_id = f.id "
                            "           AND fd.short_description IS NOT NULL "
                            "           AND fd.short_description != ''"
                            "       ) THEN 1 ELSE 0 END) AS has_doc "
                            "FROM features f WHERE f.id IN :ids"
                        ).bindparams(bindparam("ids", expanding=True)),
                        {"ids": ids},
                    )
                    .mappings()
                    .all()
                )
            for r in rows:
                raw = r["tags"]
                if isinstance(raw, str) and raw:
                    try:
                        for t in json.loads(raw):
                            tags_counter[t] += 1
                    except json.JSONDecodeError:
                        pass
                has_doc_counts["true" if r["has_doc"] else "false"] += 1
        return {
            "sources": [{"name": k, "count": v} for k, v in src_counts.most_common()],
            "tags": [{"name": k, "count": v} for k, v in tags_counter.most_common()],
            "dtypes": [{"name": k, "count": v} for k, v in dtype_counts.most_common()],
            "has_doc": has_doc_counts,
        }

    def search_features(self, query: str) -> list[Feature]:
        pattern = f"%{query}%"
        with self.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT * FROM features "
                        "WHERE name LIKE :p OR description LIKE :p OR tags LIKE :p OR column_name LIKE :p "
                        "ORDER BY name"
                    ),
                    {"p": pattern},
                )
                .mappings()
                .all()
            )
            return [_row_to_feature(r) for r in rows]

    @staticmethod
    def _parse_version_row(d: dict) -> dict:
        """Parse JSON fields in a feature_versions row."""
        d["snapshot"] = json.loads(d["snapshot"]) if isinstance(d.get("snapshot"), str) else d.get("snapshot", {})
        d["previous_value"] = (
            json.loads(d["previous_value"]) if isinstance(d.get("previous_value"), str) else d.get("previous_value")
        )
        d["new_value"] = json.loads(d["new_value"]) if isinstance(d.get("new_value"), str) else d.get("new_value")
        d.setdefault("change_type", "metadata")
        return d

    def list_feature_versions(self, feature_id: str) -> list[dict]:
        with self.session() as s:
            rows = (
                s.execute(
                    text("SELECT * FROM feature_versions WHERE feature_id = :fid ORDER BY version DESC"),
                    {"fid": feature_id},
                )
                .mappings()
                .all()
            )
            return [self._parse_version_row(dict(r)) for r in rows]

    def get_feature_version(self, feature_id: str, version: int) -> dict | None:
        with self.session() as s:
            row = (
                s.execute(
                    text("SELECT * FROM feature_versions WHERE feature_id = :fid AND version = :v"),
                    {"fid": feature_id, "v": version},
                )
                .mappings()
                .first()
            )
            return self._parse_version_row(dict(row)) if row else None

    def get_recent_versions(self, limit: int = 20, days: int = 7) -> list[dict]:
        """Return recent version changes across all features for audit log."""
        cutoff = _utcnow() - timedelta(days=days)
        with self.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT fv.*, f.name as feature_name "
                        "FROM feature_versions fv "
                        "JOIN features f ON fv.feature_id = f.id "
                        "WHERE fv.created_at >= :cutoff "
                        "ORDER BY fv.created_at DESC "
                        "LIMIT :lim"
                    ),
                    {"cutoff": cutoff, "lim": limit},
                )
                .mappings()
                .all()
            )
            return [self._parse_version_row(dict(r)) for r in rows]

    def rollback_feature(self, feature_id: str, version: int) -> dict:
        v = self.get_feature_version(feature_id, version)
        if v is None:
            msg = f"Version {version} not found for feature {feature_id}"
            raise ValueError(msg)
        snapshot = v["snapshot"]
        updates = {k: snapshot[k] for k in ("description", "tags", "owner", "dtype") if k in snapshot}
        self.update_feature_metadata(feature_id, _rollback_version=version, **updates)
        with self.session() as s:
            row = s.execute(text("SELECT * FROM features WHERE id = :id"), {"id": feature_id}).mappings().first()
            return dict(row) if row else {}

    # --- Feature Docs ---

    def get_feature_doc(self, feature_id: str) -> dict | None:
        with self.session() as s:
            row = (
                s.execute(text("SELECT * FROM feature_docs WHERE feature_id = :fid"), {"fid": feature_id})
                .mappings()
                .first()
            )
            return dict(row) if row else None

    def save_feature_doc(
        self,
        feature_id: str,
        doc: dict,
        model_used: str = "unknown",
        hints_used: str | None = None,
        context_features: list[str] | None = None,
    ) -> None:
        def _str(val: object) -> str:
            if isinstance(val, list):
                return "; ".join(str(v) for v in val)
            return str(val) if val else ""

        old_doc = self.get_feature_doc(feature_id)
        old_short = old_doc.get("short_description", "") if old_doc else ""
        new_short = _str(doc.get("short_description", ""))

        with self.session() as s:
            s.execute(text("DELETE FROM feature_docs WHERE feature_id = :fid"), {"fid": feature_id})
            s.execute(
                text(
                    "INSERT INTO feature_docs "
                    "(feature_id, short_description, long_description, expected_range, potential_issues, "
                    " generated_at, model_used, hints_used, context_features) "
                    "VALUES (:fid, :short, :long, :exp, :issues, :now, :model, :hints, :ctx)"
                ),
                {
                    "fid": feature_id,
                    "short": new_short,
                    "long": _str(doc.get("long_description", "")),
                    "exp": _str(doc.get("expected_range", "")),
                    "issues": _str(doc.get("potential_issues", "")),
                    "now": _utcnow(),
                    "model": model_used,
                    "hints": hints_used,
                    "ctx": json.dumps(context_features) if context_features else None,
                },
            )
            s.commit()

        from .usage import resolve_user

        changes = {"short_description": (old_short, new_short)}
        summary = "Updated short_description" if old_short else "Generated documentation"
        self._snapshot_feature(
            feature_id,
            changes,
            changed_by=resolve_user(),
            change_type="doc",
        )
        with self.session() as s:
            s.execute(
                text(
                    "UPDATE feature_versions SET change_summary = :summary "
                    "WHERE feature_id = :fid "
                    "  AND version = (SELECT MAX(version) FROM feature_versions WHERE feature_id = :fid)"
                ),
                {"summary": summary, "fid": feature_id},
            )
            s.commit()

    def list_undocumented_features(self) -> list[Feature]:
        with self.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT f.* FROM features f "
                        "LEFT JOIN feature_docs fd ON f.id = fd.feature_id "
                        "WHERE fd.feature_id IS NULL "
                        "   OR (fd.short_description IS NULL OR fd.short_description = '') "
                        "   OR f.updated_at > fd.generated_at"
                    )
                )
                .mappings()
                .all()
            )
            return [_row_to_feature(r) for r in rows]

    def get_doc_stats(self) -> dict:
        with self.session() as s:
            total = s.execute(text("SELECT COUNT(*) FROM features")).scalar() or 0
            documented = (
                s.execute(
                    text(
                        "SELECT COUNT(DISTINCT feature_id) FROM feature_docs "
                        "WHERE short_description IS NOT NULL AND short_description != ''"
                    )
                ).scalar()
                or 0
            )
            with_hints = (
                s.execute(
                    text("SELECT COUNT(*) FROM features WHERE generation_hints IS NOT NULL AND generation_hints != ''")
                ).scalar()
                or 0
            )
            return {
                "total_features": total,
                "documented": documented,
                "documented_features": documented,
                "features_with_hints": with_hints,
                "undocumented": total - documented,
                "coverage": round(documented / total * 100, 1) if total > 0 else 0.0,
            }

    def get_all_feature_docs(self) -> dict[str, dict]:
        with self.session() as s:
            rows = (
                s.execute(
                    text("SELECT * FROM feature_docs WHERE short_description IS NOT NULL AND short_description != ''")
                )
                .mappings()
                .all()
            )
            return {row["feature_id"]: dict(row) for row in rows}

    # --- Monitoring Baselines ---

    def get_baseline(self, feature_id: str) -> dict | None:
        with self.session() as s:
            row = s.execute(
                text("SELECT baseline_stats FROM monitoring_baselines WHERE feature_id = :fid"),
                {"fid": feature_id},
            ).first()
            if row is None:
                return None
            stats = row[0]
            return json.loads(stats) if isinstance(stats, str) else stats

    def save_baseline(self, feature_id: str, stats: dict) -> None:
        with self.session() as s:
            s.execute(text("DELETE FROM monitoring_baselines WHERE feature_id = :fid"), {"fid": feature_id})
            s.execute(
                text(
                    "INSERT INTO monitoring_baselines (feature_id, baseline_stats, computed_at) "
                    "VALUES (:fid, :stats, :now)"
                ),
                {"fid": feature_id, "stats": json.dumps(stats), "now": _utcnow()},
            )
            s.commit()

    # --- Stats ---

    def get_catalog_stats(self) -> dict:
        sources = len(self.list_sources())
        features = len(self.list_features())
        doc_stats = self.get_doc_stats()
        return {"sources": sources, "features": features, **doc_stats}

    # --- Feature Groups ---

    def create_group(self, group: FeatureGroup) -> FeatureGroup:
        with self.session() as s:
            s.execute(
                text(
                    "INSERT INTO feature_groups (id, name, description, project, owner, created_at, updated_at) "
                    "VALUES (:id, :name, :description, :project, :owner, :created_at, :updated_at)"
                ),
                {
                    "id": group.id,
                    "name": group.name,
                    "description": group.description,
                    "project": group.project,
                    "owner": group.owner,
                    "created_at": group.created_at,
                    "updated_at": group.updated_at,
                },
            )
            s.commit()
        return group

    def get_group_by_name(self, name: str) -> FeatureGroup | None:
        with self.session() as s:
            row = s.execute(text("SELECT * FROM feature_groups WHERE name = :name"), {"name": name}).mappings().first()
            return FeatureGroup(**dict(row)) if row else None

    def list_groups(self, project: str | None = None) -> list[FeatureGroup]:
        with self.session() as s:
            if project:
                rows = (
                    s.execute(
                        text("SELECT * FROM feature_groups WHERE project = :p ORDER BY name"),
                        {"p": project},
                    )
                    .mappings()
                    .all()
                )
            else:
                rows = s.execute(text("SELECT * FROM feature_groups ORDER BY name")).mappings().all()
            return [FeatureGroup(**dict(r)) for r in rows]

    def update_group(self, group_id: str, **kwargs: object) -> None:
        allowed = {"description", "project", "owner"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        sets = [f"{k} = :{k}" for k in updates]
        sets.append("updated_at = :updated_at")
        params: dict[str, Any] = dict(updates)
        params["updated_at"] = _utcnow()
        params["id"] = group_id
        with self.session() as s:
            s.execute(text(f"UPDATE feature_groups SET {', '.join(sets)} WHERE id = :id"), params)  # noqa: S608
            s.commit()

    def delete_group(self, group_id: str) -> None:
        with self.session() as s:
            s.execute(text("DELETE FROM feature_groups WHERE id = :id"), {"id": group_id})
            s.commit()

    def add_group_members(self, group_id: str, feature_ids: list[str]) -> int:
        """Add features to a group. Returns count of newly added members.

        Uses ``ON CONFLICT DO NOTHING`` so duplicate inserts are silently
        skipped — portable across SQLite (3.24+) and PostgreSQL.
        """
        if not feature_ids:
            return 0
        added = 0
        now = _utcnow()
        with self.session() as s:
            for fid in feature_ids:
                result = s.execute(
                    text(
                        "INSERT INTO feature_group_members (group_id, feature_id, added_at) "
                        "VALUES (:gid, :fid, :now) "
                        "ON CONFLICT (group_id, feature_id) DO NOTHING"
                    ),
                    {"gid": group_id, "fid": fid, "now": now},
                )
                if result.rowcount > 0:  # type: ignore[attr-defined]
                    added += 1
            s.commit()
        return added

    def remove_group_member(self, group_id: str, feature_id: str) -> None:
        with self.session() as s:
            s.execute(
                text("DELETE FROM feature_group_members WHERE group_id = :gid AND feature_id = :fid"),
                {"gid": group_id, "fid": feature_id},
            )
            s.commit()

    def list_group_members(self, group_id: str) -> list[Feature]:
        with self.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT f.* FROM features f "
                        "JOIN feature_group_members gm ON f.id = gm.feature_id "
                        "WHERE gm.group_id = :gid "
                        "ORDER BY f.name"
                    ),
                    {"gid": group_id},
                )
                .mappings()
                .all()
            )
            return [_row_to_feature(r) for r in rows]

    def count_group_members(self, group_id: str) -> int:
        with self.session() as s:
            return int(
                s.execute(
                    text("SELECT COUNT(*) FROM feature_group_members WHERE group_id = :gid"),
                    {"gid": group_id},
                ).scalar()
                or 0
            )

    # --- Feature Group Versions (freeze + export) ---

    def freeze_group(self, group_id: str, note: str = "", frozen_by: str = "") -> FeatureGroupVersion:
        """Snapshot the group's current members into a new version row.

        Joins ``features`` with ``data_sources`` so the snapshot captures
        the source path/format at freeze time — sources can be re-pointed
        or deleted later without invalidating the snapshot. Stats and tag
        list are JSON-decoded once here so the snapshot is a clean nested
        document rather than a string-of-strings.
        """
        group = next((g for g in self.list_groups() if g.id == group_id), None)
        if group is None:
            raise KeyError(f"Group not found: {group_id}")

        frozen_at = _utcnow()
        with self.session() as s:
            next_version = int(
                s.execute(
                    text(
                        "SELECT COALESCE(MAX(version_number), 0) + 1 FROM feature_group_versions WHERE group_id = :gid"
                    ),
                    {"gid": group_id},
                ).scalar()
                or 1
            )

            member_rows = (
                s.execute(
                    text(
                        "SELECT f.id, f.name, f.dtype, f.description, f.tags, f.owner, f.stats, "
                        "       f.definition, f.definition_type, f.column_name, "
                        "       ds.path AS source_path, ds.format AS source_format, ds.name AS source_name "
                        "FROM features f "
                        "JOIN feature_group_members gm ON f.id = gm.feature_id "
                        "LEFT JOIN data_sources ds ON ds.id = f.data_source_id "
                        "WHERE gm.group_id = :gid "
                        "ORDER BY f.name"
                    ),
                    {"gid": group_id},
                )
                .mappings()
                .all()
            )

            features: list[dict[str, Any]] = []
            for r in member_rows:
                tags_raw = r.get("tags")
                stats_raw = r.get("stats")
                features.append(
                    {
                        "id": r["id"],
                        "name": r["name"],
                        "dtype": r.get("dtype") or "",
                        "description": r.get("description") or "",
                        "tags": json.loads(tags_raw) if isinstance(tags_raw, str) and tags_raw else [],
                        "owner": r.get("owner") or "",
                        "stats": json.loads(stats_raw) if isinstance(stats_raw, str) and stats_raw else {},
                        "definition": r.get("definition"),
                        "definition_type": r.get("definition_type"),
                        "column_name": r.get("column_name") or "",
                        "source_path": r.get("source_path") or "",
                        "source_format": r.get("source_format") or "",
                        "source_name": r.get("source_name") or "",
                    }
                )

            snapshot = {
                "group": {
                    "id": group.id,
                    "name": group.name,
                    "description": group.description,
                    "project": group.project,
                    "owner": group.owner,
                },
                "version_number": next_version,
                "frozen_at": frozen_at.isoformat(),
                "frozen_by": frozen_by,
                "note": note,
                "features": features,
            }
            snapshot_json = json.dumps(snapshot, ensure_ascii=False, sort_keys=False)

            version = FeatureGroupVersion(
                group_id=group_id,
                version_number=next_version,
                snapshot_json=snapshot_json,
                note=note,
                frozen_by=frozen_by,
                frozen_at=frozen_at,
            )
            s.execute(
                text(
                    "INSERT INTO feature_group_versions "
                    "(id, group_id, version_number, snapshot_json, note, frozen_by, frozen_at) "
                    "VALUES (:id, :gid, :vn, :sj, :note, :by, :at)"
                ),
                {
                    "id": version.id,
                    "gid": group_id,
                    "vn": next_version,
                    "sj": snapshot_json,
                    "note": note,
                    "by": frozen_by,
                    "at": frozen_at,
                },
            )
            s.commit()
            return version

    def list_group_versions(self, group_id: str) -> list[FeatureGroupVersion]:
        with self.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT id, group_id, version_number, snapshot_json, note, frozen_by, frozen_at "
                        "FROM feature_group_versions WHERE group_id = :gid "
                        "ORDER BY version_number DESC"
                    ),
                    {"gid": group_id},
                )
                .mappings()
                .all()
            )
            return [FeatureGroupVersion(**dict(r)) for r in rows]

    def get_group_version(self, group_id: str, version_number: int) -> FeatureGroupVersion | None:
        with self.session() as s:
            row = (
                s.execute(
                    text(
                        "SELECT id, group_id, version_number, snapshot_json, note, frozen_by, frozen_at "
                        "FROM feature_group_versions WHERE group_id = :gid AND version_number = :vn"
                    ),
                    {"gid": group_id, "vn": version_number},
                )
                .mappings()
                .first()
            )
            return FeatureGroupVersion(**dict(row)) if row else None

    # --- Feature Definitions ---

    def set_feature_definition(self, feature_id: str, definition: str, definition_type: str) -> None:
        from .usage import resolve_user

        old_def = self.get_feature_definition(feature_id)
        with self.session() as s:
            now = _utcnow()
            s.execute(
                text(
                    "UPDATE features SET definition = :def, definition_type = :dt, "
                    "  definition_updated_at = :now, updated_at = :now WHERE id = :id"
                ),
                {"def": definition, "dt": definition_type, "now": now, "id": feature_id},
            )
            s.commit()
        old_val = old_def.get("definition") if old_def else None
        old_dtype = old_def.get("definition_type") if old_def else None
        self._snapshot_feature(
            feature_id,
            {"definition": (old_val, definition), "definition_type": (old_dtype, definition_type)},
            changed_by=resolve_user(),
            change_type="definition",
        )

    def get_feature_definition(self, feature_id: str) -> dict | None:
        with self.session() as s:
            row = (
                s.execute(
                    text("SELECT definition, definition_type, definition_updated_at FROM features WHERE id = :id"),
                    {"id": feature_id},
                )
                .mappings()
                .first()
            )
            if row is None or row["definition"] is None:
                return None
            return dict(row)

    def clear_feature_definition(self, feature_id: str) -> None:
        from .usage import resolve_user

        old_def = self.get_feature_definition(feature_id)
        with self.session() as s:
            now = _utcnow()
            s.execute(
                text(
                    "UPDATE features SET definition = NULL, definition_type = NULL, "
                    "  definition_updated_at = NULL, updated_at = :now WHERE id = :id"
                ),
                {"now": now, "id": feature_id},
            )
            s.commit()
        if old_def and old_def.get("definition"):
            self._snapshot_feature(
                feature_id,
                {"definition": (old_def["definition"], None)},
                changed_by=resolve_user(),
                change_type="definition",
            )

    # --- Usage Tracking ---

    def log_usage(self, feature_id: str, action: str, user: str = "", context: str = "") -> None:
        with self.session() as s:
            s.execute(
                text(
                    # "user" is a reserved keyword in PostgreSQL — must be double-quoted.
                    # SQLite tolerates the quotes, so this is portable.
                    'INSERT INTO usage_log (id, feature_id, action, "user", context, created_at) '
                    "VALUES (:id, :fid, :action, :user, :ctx, :now)"
                ),
                {
                    "id": _new_id(),
                    "fid": feature_id,
                    "action": action,
                    "user": user,
                    "ctx": context,
                    "now": _utcnow(),
                },
            )
            s.commit()

    def get_top_features(self, limit: int = 10, days: int = 30) -> list[dict]:
        cutoff = _utcnow() - timedelta(days=days)
        with self.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT f.name, "
                        "  SUM(CASE WHEN ul.action = 'view' THEN 1 ELSE 0 END) as view_count, "
                        "  SUM(CASE WHEN ul.action = 'query' THEN 1 ELSE 0 END) as query_count, "
                        "  COUNT(*) as total_count, "
                        "  MAX(ul.created_at) as last_seen, "
                        "  f.created_at, "
                        "  ds.name as source "
                        "FROM usage_log ul "
                        "JOIN features f ON ul.feature_id = f.id "
                        "JOIN data_sources ds ON f.data_source_id = ds.id "
                        "WHERE ul.created_at >= :cutoff "
                        "GROUP BY ul.feature_id, f.name, f.created_at, ds.name "
                        "ORDER BY total_count DESC "
                        "LIMIT :lim"
                    ),
                    {"cutoff": cutoff, "lim": limit},
                )
                .mappings()
                .all()
            )
            return [dict(r) for r in rows]

    def get_orphaned_features(self, days: int = 30) -> list[dict]:
        cutoff = _utcnow() - timedelta(days=days)
        with self.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT f.name, "
                        "  (SELECT MAX(ul2.created_at) FROM usage_log ul2 WHERE ul2.feature_id = f.id) as last_seen "
                        "FROM features f "
                        "LEFT JOIN usage_log ul ON f.id = ul.feature_id AND ul.created_at >= :cutoff "
                        "WHERE ul.id IS NULL "
                        "ORDER BY f.name"
                    ),
                    {"cutoff": cutoff},
                )
                .mappings()
                .all()
            )
            return [dict(r) for r in rows]

    def get_usage_activity(self, days: int = 7) -> list[dict]:
        """Per-day usage activity. Aggregation done in Python for portability —
        SQLite's ``DATE(col)`` and Postgres' ``col::date`` aren't a clean
        cross-dialect equivalent.
        """
        cutoff = _utcnow() - timedelta(days=days)
        with self.session() as s:
            rows = (
                s.execute(
                    text("SELECT created_at, action, feature_id FROM usage_log WHERE created_at >= :cutoff"),
                    {"cutoff": cutoff},
                )
                .mappings()
                .all()
            )

        buckets: dict[str, dict[str, Any]] = defaultdict(
            lambda: {"view_count": 0, "query_count": 0, "_features": set(), "total": 0}
        )
        for r in rows:
            ts = r["created_at"]
            day = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
            b = buckets[day]
            if r["action"] == "view":
                b["view_count"] += 1
            elif r["action"] == "query":
                b["query_count"] += 1
            b["_features"].add(r["feature_id"])
            b["total"] += 1
        result = []
        for day in sorted(buckets.keys(), reverse=True):
            b = buckets[day]
            result.append(
                {
                    "date": day,
                    "view_count": b["view_count"],
                    "query_count": b["query_count"],
                    "unique_features": len(b["_features"]),
                    "total": b["total"],
                }
            )
        return result

    def get_feature_usage(self, feature_id: str, days: int = 30) -> dict:
        cutoff = _utcnow() - timedelta(days=days)
        cutoff_7 = _utcnow() - timedelta(days=7)
        with self.session() as s:
            row = (
                s.execute(
                    text(
                        "SELECT "
                        "  SUM(CASE WHEN action = 'view' THEN 1 ELSE 0 END) as views, "
                        "  SUM(CASE WHEN action = 'query' THEN 1 ELSE 0 END) as queries, "
                        "  COUNT(*) as total, "
                        "  MAX(created_at) as last_seen "
                        "FROM usage_log "
                        "WHERE feature_id = :fid AND created_at >= :cutoff"
                    ),
                    {"fid": feature_id, "cutoff": cutoff},
                )
                .mappings()
                .first()
            )
            daily_rows = (
                s.execute(
                    text("SELECT created_at FROM usage_log WHERE feature_id = :fid AND created_at >= :cutoff7"),
                    {"fid": feature_id, "cutoff7": cutoff_7},
                )
                .mappings()
                .all()
            )

        # Aggregate daily counts in Python (portable across sqlite/postgres).
        daily_counts: dict[str, int] = defaultdict(int)
        for r in daily_rows:
            ts = r["created_at"]
            day = ts.date().isoformat() if hasattr(ts, "date") else str(ts)[:10]
            daily_counts[day] += 1
        daily = [{"date": d, "count": daily_counts[d]} for d in sorted(daily_counts.keys())]
        return {
            "views": (row["views"] if row else 0) or 0,
            "queries": (row["queries"] if row else 0) or 0,
            "total": (row["total"] if row else 0) or 0,
            "last_seen": row["last_seen"] if row else None,
            "daily": daily,
        }

    # --- Generation Hints ---

    def set_feature_hint(self, feature_id: str, hint: str) -> None:
        from .usage import resolve_user

        old_hint = self.get_feature_hint(feature_id)
        with self.session() as s:
            now = _utcnow()
            s.execute(
                text("UPDATE features SET generation_hints = :hint, updated_at = :now WHERE id = :id"),
                {"hint": hint, "now": now, "id": feature_id},
            )
            s.commit()
        self._snapshot_feature(
            feature_id,
            {"generation_hints": (old_hint, hint)},
            changed_by=resolve_user(),
            change_type="hints",
        )

    def get_feature_hint(self, feature_id: str) -> str | None:
        with self.session() as s:
            row = s.execute(text("SELECT generation_hints FROM features WHERE id = :id"), {"id": feature_id}).first()
            return row[0] if row else None

    def clear_feature_hint(self, feature_id: str) -> None:
        from .usage import resolve_user

        old_hint = self.get_feature_hint(feature_id)
        with self.session() as s:
            now = _utcnow()
            s.execute(
                text("UPDATE features SET generation_hints = NULL, updated_at = :now WHERE id = :id"),
                {"now": now, "id": feature_id},
            )
            s.commit()
        if old_hint:
            self._snapshot_feature(
                feature_id,
                {"generation_hints": (old_hint, None)},
                changed_by=resolve_user(),
                change_type="hints",
            )

    # --- Visualization Queries ---

    def get_doc_debt(self) -> list[dict]:
        with self.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT "
                        "  COALESCE(NULLIF(f.owner, ''), 'unassigned') as owner, "
                        "  ds.name as source, "
                        "  COUNT(*) as total, "
                        "  COUNT(*) - COUNT( "
                        "    CASE WHEN fd.short_description IS NOT NULL AND fd.short_description != '' "
                        "         THEN fd.feature_id END "
                        "  ) as undocumented "
                        "FROM features f "
                        "JOIN data_sources ds ON f.data_source_id = ds.id "
                        "LEFT JOIN feature_docs fd ON f.id = fd.feature_id "
                        "GROUP BY f.owner, ds.name "
                        "ORDER BY undocumented DESC"
                    )
                )
                .mappings()
                .all()
            )
        result = []
        for r in rows:
            d = dict(r)
            d["pct_undocumented"] = round(d["undocumented"] / d["total"] * 100, 1) if d["total"] > 0 else 0.0
            result.append(d)
        return result

    def get_monitoring_history(self, feature_name: str, days: int = 30) -> list[dict]:
        cutoff = _utcnow() - timedelta(days=days)
        with self.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT checked_at, psi, severity FROM monitoring_checks "
                        "WHERE feature_name = :name AND checked_at >= :cutoff "
                        "ORDER BY checked_at ASC"
                    ),
                    {"name": feature_name, "cutoff": cutoff},
                )
                .mappings()
                .all()
            )
            return [dict(r) for r in rows]

    def get_latest_severity(self, feature_id: str) -> str | None:
        """Return the severity of the most recent monitoring_check for a feature.

        Helper used by routes and CLI that want a single feature's drift status
        without joining the whole monitoring_checks table.
        """
        with self.session() as s:
            row = s.execute(
                text("SELECT severity FROM monitoring_checks WHERE feature_id = :fid ORDER BY checked_at DESC LIMIT 1"),
                {"fid": feature_id},
            ).first()
            return row[0] if row else None

    def save_monitoring_result(
        self,
        feature_id: str,
        feature_name: str,
        psi: float | None,
        severity: str,
        *,
        null_ratio: float | None = None,
        mean_z_score: float | None = None,
        sample_size: int | None = None,
    ) -> None:
        with self.session() as s:
            s.execute(
                text(
                    "INSERT INTO monitoring_checks "
                    "(id, feature_id, feature_name, psi, severity, checked_at, "
                    " null_ratio, mean_z_score, sample_size) "
                    "VALUES (:id, :fid, :name, :psi, :sev, :now, :nr, :mz, :ss)"
                ),
                {
                    "id": _new_id(),
                    "fid": feature_id,
                    "name": feature_name,
                    "psi": psi,
                    "sev": severity,
                    "now": _utcnow(),
                    "nr": null_ratio,
                    "mz": mean_z_score,
                    "ss": sample_size,
                },
            )
            s.commit()

    def get_feature_metric_history(self, feature_name: str, days: int = 30) -> list[dict]:
        """Per-check metric history including auxiliary metrics added later.

        Legacy rows return NULL for null_ratio / mean_z_score / sample_size;
        the frontend uses connectNulls=false to surface the gap visibly.
        """
        cutoff = _utcnow() - timedelta(days=days)
        with self.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT checked_at, psi, severity, null_ratio, mean_z_score, sample_size "
                        "FROM monitoring_checks "
                        "WHERE feature_name = :name AND checked_at >= :cutoff "
                        "ORDER BY checked_at ASC"
                    ),
                    {"name": feature_name, "cutoff": cutoff},
                )
                .mappings()
                .all()
            )
            return [dict(r) for r in rows]

    # Severity priority used to sort features in the group heatmap so the
    # most-alarming features land at the top of the truncated 200-row view.
    _SEVERITY_PRIORITY = {"critical": 0, "warning": 1, "healthy": 2, "unknown": 3, "error": 0}

    def get_group_drift_matrix(self, group_id: str, days: int = 30) -> dict:
        """Build a (feature × day) severity matrix for the group.

        Worst severity per (feature, day) wins when multiple checks land on
        the same calendar day. Date keys are ISO date strings (YYYY-MM-DD)
        so the JSON shape is reproducible without timezone math.
        """
        today = _utcnow().date()
        date_range = [today - timedelta(days=days - 1 - i) for i in range(days)]
        date_set = {d.isoformat() for d in date_range}

        with self.session() as s:
            members = (
                s.execute(
                    text(
                        "SELECT f.id, f.name, f.data_source_id, "
                        "       COALESCE(ds.name, '') AS source_name "
                        "FROM features f "
                        "JOIN feature_group_members gm ON f.id = gm.feature_id "
                        "LEFT JOIN data_sources ds ON ds.id = f.data_source_id "
                        "WHERE gm.group_id = :gid"
                    ),
                    {"gid": group_id},
                )
                .mappings()
                .all()
            )
            if not members:
                return {
                    "date_range": [d.isoformat() for d in date_range],
                    "features": [],
                    "truncated": False,
                    "total_count": 0,
                }

            feature_ids = [m["id"] for m in members]
            cutoff_dt = _utcnow() - timedelta(days=days - 1)

            checks = (
                s.execute(
                    text(
                        "SELECT feature_id, severity, psi, checked_at "
                        "FROM monitoring_checks "
                        "WHERE feature_id IN :fids AND checked_at >= :cutoff"
                    ).bindparams(bindparam("fids", expanding=True)),
                    {"fids": feature_ids, "cutoff": cutoff_dt},
                )
                .mappings()
                .all()
            )

        # Pivot in Python: { (feature_id, date_iso): {severity, psi} }, taking
        # the worst severity per cell. SQLite's GROUP BY semantics for "worst
        # severity" need a CASE rank — easier to reduce in Python and stay
        # backend-portable.
        cell_map: dict[tuple[str, str], dict[str, Any]] = {}
        latest_severity: dict[str, str] = {}
        latest_checked: dict[str, datetime] = {}
        for row in checks:
            checked_at: datetime = row["checked_at"]
            if isinstance(checked_at, str):
                # SQLite returns string for TIMESTAMP without converter; parse defensively.
                checked_at = datetime.fromisoformat(checked_at)
            day_iso = checked_at.date().isoformat()
            if day_iso not in date_set:
                continue
            severity = row["severity"] or "unknown"
            key = (row["feature_id"], day_iso)
            existing = cell_map.get(key)
            if existing is None or self._SEVERITY_PRIORITY.get(severity, 3) < self._SEVERITY_PRIORITY.get(
                existing["severity"], 3
            ):
                cell_map[key] = {"severity": severity, "psi": row["psi"]}

            # Track per-feature latest check for sort ordering below.
            prev = latest_checked.get(row["feature_id"])
            if prev is None or checked_at > prev:
                latest_checked[row["feature_id"]] = checked_at
                latest_severity[row["feature_id"]] = severity

        sorted_members = sorted(
            members,
            key=lambda m: (
                self._SEVERITY_PRIORITY.get(latest_severity.get(m["id"], "unknown"), 3),
                m["name"],
            ),
        )

        cap = 200
        truncated = len(sorted_members) > cap
        capped = sorted_members[:cap]

        features_out: list[dict[str, Any]] = []
        for m in capped:
            daily: list[dict[str, Any]] = []
            for d in date_range:
                key = (m["id"], d.isoformat())
                cell = cell_map.get(key)
                if cell is None:
                    daily.append({"date": d.isoformat(), "severity": "unknown", "psi": None})
                else:
                    daily.append({"date": d.isoformat(), "severity": cell["severity"], "psi": cell["psi"]})
            features_out.append(
                {
                    "id": m["id"],
                    "name": m["name"],
                    "source": m["source_name"],
                    "daily": daily,
                }
            )

        return {
            "date_range": [d.isoformat() for d in date_range],
            "features": features_out,
            "truncated": truncated,
            "total_count": len(members),
        }

    def get_catalog_drift_trend(self, days: int = 90) -> list[dict]:
        """Per-day critical/warning percentage across the catalog.

        For each day in the window, take each feature's latest check
        on-or-before that day and bucket by severity. The denominator is
        the number of features that have *any* monitoring check on or
        before that day (so the percentage isn't diluted by features
        that were never monitored).
        """
        today = _utcnow().date()
        date_range = [today - timedelta(days=days - 1 - i) for i in range(days)]
        # Pull everything in window plus a generous lookback so "latest check
        # on-or-before day D" is correct even for features not checked recently.
        # Window = days + 365 keeps the query bounded; older legacy rows are dropped.
        cutoff_dt = _utcnow() - timedelta(days=days + 365)

        with self.session() as s:
            checks = (
                s.execute(
                    text(
                        "SELECT feature_id, severity, checked_at FROM monitoring_checks "
                        "WHERE checked_at >= :cutoff "
                        "ORDER BY feature_id, checked_at"
                    ),
                    {"cutoff": cutoff_dt},
                )
                .mappings()
                .all()
            )

        # For each feature, build a sorted list of (datetime, severity).
        per_feature: dict[str, list[tuple[datetime, str]]] = defaultdict(list)
        for row in checks:
            checked_at = row["checked_at"]
            if isinstance(checked_at, str):
                checked_at = datetime.fromisoformat(checked_at)
            per_feature[row["feature_id"]].append((checked_at, row["severity"] or "unknown"))

        series: list[dict[str, Any]] = []
        for d in date_range:
            day_end = datetime.combine(d, datetime.max.time(), tzinfo=timezone.utc)
            critical = warning = total = 0
            for feature_history in per_feature.values():
                latest_severity: str | None = None
                for checked_at, severity in feature_history:
                    if checked_at <= day_end:
                        latest_severity = severity
                    else:
                        break
                if latest_severity is None:
                    continue
                total += 1
                if latest_severity == "critical":
                    critical += 1
                elif latest_severity == "warning":
                    warning += 1
            critical_pct = round((critical / total) * 100, 2) if total else 0.0
            warning_pct = round((warning / total) * 100, 2) if total else 0.0
            series.append(
                {
                    "date": d.isoformat(),
                    "critical_pct": critical_pct,
                    "warning_pct": warning_pct,
                    "total_features": total,
                }
            )
        return series

    def get_baseline_for_feature(self, feature_name: str) -> dict | None:
        with self.session() as s:
            row = (
                s.execute(
                    text(
                        "SELECT mb.baseline_stats, mb.computed_at, f.name as feature_spec "
                        "FROM monitoring_baselines mb "
                        "JOIN features f ON mb.feature_id = f.id "
                        "WHERE f.name = :name"
                    ),
                    {"name": feature_name},
                )
                .mappings()
                .first()
            )
            if row is None:
                return None
            stats = row["baseline_stats"]
            computed_at = row["computed_at"]
            return {
                "feature_spec": row["feature_spec"],
                "baseline_stats": json.loads(stats) if isinstance(stats, str) else stats,
                "computed_at": computed_at.isoformat() if computed_at else None,
            }

    def get_stats_by_source(self) -> list[dict]:
        with self.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT "
                        "  ds.name as source_name, "
                        "  ds.path, "
                        "  COUNT(DISTINCT f.id) as feature_count, "
                        "  COUNT(DISTINCT "
                        "    CASE WHEN fd.short_description IS NOT NULL AND fd.short_description != '' "
                        "         THEN f.id END "
                        "  ) as documented_count, "
                        "  ds.updated_at as last_scanned "
                        "FROM data_sources ds "
                        "LEFT JOIN features f ON f.data_source_id = ds.id "
                        "LEFT JOIN feature_docs fd ON f.id = fd.feature_id "
                        "GROUP BY ds.id, ds.name, ds.path, ds.updated_at "
                        "ORDER BY ds.name"
                    )
                )
                .mappings()
                .all()
            )

            latest_checks = (
                s.execute(
                    text(
                        "SELECT mc.feature_name, mc.severity, mc.psi "
                        "FROM monitoring_checks mc "
                        "INNER JOIN ( "
                        "  SELECT feature_name, MAX(checked_at) as max_checked "
                        "  FROM monitoring_checks GROUP BY feature_name "
                        ") latest ON mc.feature_name = latest.feature_name "
                        "       AND mc.checked_at = latest.max_checked"
                    )
                )
                .mappings()
                .all()
            )

        source_alerts: dict[str, list[dict]] = {}
        for c in latest_checks:
            src = c["feature_name"].split(".")[0] if "." in c["feature_name"] else ""
            source_alerts.setdefault(src, []).append(dict(c))

        result = []
        for r in rows:
            src = r["source_name"]
            checks = source_alerts.get(src, [])
            drift = [c for c in checks if c["severity"] not in ("healthy",)]
            critical = [c for c in checks if c["severity"] in ("critical", "error")]
            top_drift = max(checks, key=lambda c: c["psi"] or 0, default=None)
            ls = r["last_scanned"]
            result.append(
                {
                    "source_name": src,
                    "path": r["path"],
                    "feature_count": r["feature_count"],
                    "documented_count": r["documented_count"],
                    "drift_alerts": len(drift),
                    "critical_alerts": len(critical),
                    "last_scanned": ls.isoformat() if hasattr(ls, "isoformat") else ls,
                    "top_drifting_feature": (
                        top_drift["feature_name"] if top_drift and (top_drift["psi"] or 0) > 0.1 else None
                    ),
                }
            )
        return result

    # --- Similarity (T1.2b) ---

    def find_similar_features(self, feature_id: str, top_k: int = 10) -> list[dict]:
        """Return up to ``top_k`` features most similar to ``feature_id``.

        Routing:
        - **postgres + embedding present**: pgvector top-K cosine via the
          ``<=>`` operator on the HNSW index. Sub-100ms target even at 5k+
          features.
        - **anything else** (sqlite mode, missing embedding, postgres without
          the embedding for this feature): falls back to a Python-side
          TF-IDF cosine over feature names + descriptions across the catalog.
          Slower but always works.

        Each result: ``{name, dtype, similarity}`` where ``similarity`` is
        in ``[0, 1]`` (cosine).
        """
        if self.backend == "postgres":
            with self.session() as s:
                row = s.execute(
                    text("SELECT embedding IS NOT NULL AS has_emb FROM features WHERE id = :id"),
                    {"id": feature_id},
                ).first()
            if row is not None and row[0]:
                return self._find_similar_pgvector(feature_id, top_k)
        return self._find_similar_tfidf(feature_id, top_k)

    def _find_similar_pgvector(self, feature_id: str, top_k: int) -> list[dict]:
        """pgvector ``<=>`` (cosine distance) top-K. Postgres-only."""
        with self.session() as s:
            rows = (
                s.execute(
                    text(
                        "SELECT f.id, f.name, f.dtype, "
                        "       1 - (f.embedding <=> ref.embedding) AS similarity "
                        "FROM features f, "
                        "     (SELECT embedding FROM features WHERE id = :id) AS ref "
                        "WHERE f.id != :id AND f.embedding IS NOT NULL "
                        "ORDER BY f.embedding <=> ref.embedding "
                        "LIMIT :k"
                    ),
                    {"id": feature_id, "k": top_k},
                )
                .mappings()
                .all()
            )
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "dtype": r["dtype"],
                "similarity": float(r["similarity"]) if r["similarity"] is not None else 0.0,
            }
            for r in rows
        ]

    def search_by_embedding(self, query_vec: list[float], top_k: int = 50) -> list[dict]:
        """pgvector top-K cosine search by an arbitrary query vector (T1.2c).

        Used by the NL query embeds-first path: caller embeds the user's
        natural-language query, then this returns the closest features for
        the LLM to rerank/explain. Postgres-only — sqlite has no pgvector
        operator. Returns ``[]`` on non-postgres backends so callers can
        fall through to a different retrieval path without branching.

        Each result: ``{id, name, dtype, similarity}`` — same shape as
        ``find_similar_features`` for consistency.
        """
        if self.backend != "postgres":
            return []
        from sqlalchemy import bindparam

        from ..db.embedding_type import Embedding
        from ..db.models import EMBEDDING_DIM

        stmt = text(
            "SELECT id, name, dtype, "
            "       1 - (embedding <=> :vec) AS similarity "
            "FROM features "
            "WHERE embedding IS NOT NULL "
            "ORDER BY embedding <=> :vec "
            "LIMIT :k"
        ).bindparams(bindparam("vec", type_=Embedding(EMBEDDING_DIM)))
        with self.session() as s:
            rows = s.execute(stmt, {"vec": query_vec, "k": top_k}).mappings().all()
        return [
            {
                "id": r["id"],
                "name": r["name"],
                "dtype": r["dtype"],
                "similarity": float(r["similarity"]) if r["similarity"] is not None else 0.0,
            }
            for r in rows
        ]

    def _build_corpus(self, rows: list[dict]) -> tuple[Any, Any, list[str]]:
        """Build a TF-IDF corpus over the given feature rows.

        Shared between ``_find_similar_tfidf``, ``find_duplicate_pairs``, and
        ``recommend_by_text`` so the corpus construction stays in one place.
        Each row must carry at least ``id``, ``name``, ``description`` (str
        or None), and ``tags`` (JSON string or list).

        Returns ``(vectorizer, matrix, ids)``. The ``vectorizer`` is fitted and
        reusable for ``transform()`` on follow-up queries (e.g. a use-case
        string in ``recommend_by_text``).
        """
        from sklearn.feature_extraction.text import TfidfVectorizer

        ids: list[str] = []
        corpus: list[str] = []
        for r in rows:
            ids.append(r["id"])
            text_blob = r["name"].replace("_", " ").replace(".", " ")
            tags = r["tags"]
            if isinstance(tags, str) and tags:
                with contextlib.suppress(json.JSONDecodeError):
                    text_blob += " " + " ".join(json.loads(tags))
            elif isinstance(tags, list):
                text_blob += " " + " ".join(str(t) for t in tags)
            if r.get("description"):
                text_blob += " " + r["description"]
            corpus.append(text_blob)

        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        matrix = vectorizer.fit_transform(corpus)
        return vectorizer, matrix, ids

    def _find_similar_tfidf(self, feature_id: str, top_k: int) -> list[dict]:
        """Fallback: TF-IDF cosine over the catalog when embeddings aren't usable.

        Reads every feature into memory and does sklearn TF-IDF cosine — the
        existing similarity-graph code path uses the same approach. Acceptable
        for sub-1k catalogs; postgres+embeddings is the answer at scale.
        """
        with self.session() as s:
            rows = s.execute(text("SELECT id, name, dtype, description, tags FROM features")).mappings().all()
        if len(rows) < 2:
            return []

        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity

        row_list = [dict(r) for r in rows]
        _, matrix, ids = self._build_corpus(row_list)
        try:
            ref_idx = ids.index(feature_id)
        except ValueError:
            return []

        ref_row = matrix[ref_idx : ref_idx + 1]
        sims = cosine_similarity(ref_row, matrix)[0]
        order = np.argsort(-sims)
        result: list[dict] = []
        for idx in order:
            if idx == ref_idx:
                continue
            sim = float(sims[idx])
            if sim <= 0:
                break  # cosine of zero-vector pair → unrelated; stop early
            row = row_list[idx]
            result.append({"id": row["id"], "name": row["name"], "dtype": row["dtype"], "similarity": sim})
            if len(result) >= top_k:
                break
        return result

    # --- Duplicate pairs (T-similarity-refactor) ---

    DUPLICATES_MAX_FEATURES = 2000  # in-memory cosine matrix scale cap

    def find_duplicate_pairs(
        self,
        threshold: float,
        limit: int,
        sources: list[str] | None = None,
    ) -> tuple[list[dict], int, str | None]:
        """Return ``(pairs, total_before_limit, summary_message)``.

        ``pairs`` is a list of dicts ``{a, b, score, reasons}`` where ``a`` and
        ``b`` are :class:`FeatureBrief`-shaped dicts and ``reasons`` is a list
        of ``{code, detail}`` entries.

        ``sources`` filters BOTH sides of every pair to the given source-name
        set. ``None`` or ``[]`` → no source filter (cross-source pairs are
        included, which is the primary dedup workflow).

        Sort: score desc, secondary by number-of-reasons desc.

        Scale cap: when ``len(features) > DUPLICATES_MAX_FEATURES`` the method
        returns an empty list with a non-empty ``summary_message`` explaining
        why — callers should surface this to the user.
        """
        import logging

        from sklearn.metrics.pairwise import cosine_similarity

        # Pull only the columns we actually use; keep this query lean since the
        # scale cap is the real bottleneck above ~2k features anyway.
        with self.session() as s:
            rows = s.execute(text("SELECT id, name, dtype, description, tags, stats FROM features")).mappings().all()

        # Optional source filter (applied before corpus build so the matrix
        # never carries excluded features).
        source_set = set(sources) if sources else None
        if source_set:
            rows = [r for r in rows if r["name"].split(".")[0] in source_set]

        n = len(rows)
        if n > self.DUPLICATES_MAX_FEATURES:
            logging.getLogger(__name__).warning(
                "find_duplicate_pairs skipped: catalog has %d features (cap=%d)",
                n,
                self.DUPLICATES_MAX_FEATURES,
            )
            return (
                [],
                0,
                f"Catalog too large for in-memory duplicate detection ({n} features). "
                f"Future work: batched cosine or FAISS index.",
            )
        if n < 2:
            return [], 0, None

        # has_doc lookup (a feature has a doc if its id is in feature_docs).
        all_docs = self.get_all_feature_docs()

        row_dicts = [dict(r) for r in rows]
        _, matrix, ids = self._build_corpus(row_dicts)
        sim_matrix = cosine_similarity(matrix)

        # Pre-parse stats once per feature so the per-pair reason builder
        # doesn't re-parse JSON for every candidate.
        parsed_stats = [_parse_stats(r.get("stats")) for r in row_dicts]

        # Upper-triangle scan.
        candidates: list[tuple[float, int, int]] = []
        for i in range(n):
            for j in range(i + 1, n):
                score = float(sim_matrix[i, j])
                if score >= threshold:
                    candidates.append((score, i, j))
        total_before_limit = len(candidates)

        def _brief(idx: int) -> dict:
            r = row_dicts[idx]
            src = r["name"].split(".")[0] if "." in r["name"] else ""
            return {
                "id": r["id"],
                "name": r["name"],
                "dtype": r["dtype"] or "",
                "source": src,
                "has_doc": r["id"] in all_docs,
            }

        pairs: list[dict] = []
        for score, i, j in candidates:
            row_a, row_b = row_dicts[i], row_dicts[j]
            pairs.append(
                {
                    "a": _brief(i),
                    "b": _brief(j),
                    "score": round(score, 4),
                    "reasons": _compute_pair_reasons(
                        row_a["name"],
                        row_a["dtype"],
                        parsed_stats[i],
                        row_b["name"],
                        row_b["dtype"],
                        parsed_stats[j],
                        score,
                    ),
                }
            )

        # Sort: score desc, then number-of-reasons desc. Stable.
        pairs.sort(key=lambda p: (-p["score"], -len(p["reasons"])))

        return pairs[:limit], total_before_limit, None

    # --- Similarity matrix (caller-selected feature subset) ---

    SIMILARITY_MATRIX_MAX_FEATURES = 100  # caller-side filter cap; matches the UI cap

    def compute_similarity_matrix(
        self,
        feature_ids: list[str],
        threshold: float,
    ) -> tuple[list[dict], list[dict]]:
        """Score the upper triangle of an N×N similarity matrix over a caller-
        selected feature subset.

        Returns ``(features, cells)`` where ``features`` is a list of
        :class:`FeatureBrief`-shaped dicts in the same order the caller passed
        them in (so the UI can index ``cells.a`` / ``cells.b`` directly), and
        ``cells`` is ``[{a: int, b: int, score: float}, …]`` — upper triangle
        only (``a < b``), filtered to ``score >= threshold``. Diagonal cells
        are not returned (always 1.0; UI renders them locally).

        Raises:
            ValueError: when ``feature_ids`` is empty, contains duplicates, or
                exceeds :attr:`SIMILARITY_MATRIX_MAX_FEATURES`.
            KeyError: when one or more ids are not present in the catalog.
        """
        from sklearn.metrics.pairwise import cosine_similarity

        if not feature_ids:
            raise ValueError("feature_ids must not be empty")
        if len(set(feature_ids)) != len(feature_ids):
            raise ValueError("feature_ids must be unique")
        if len(feature_ids) > self.SIMILARITY_MATRIX_MAX_FEATURES:
            raise ValueError(f"feature_ids length {len(feature_ids)} exceeds cap {self.SIMILARITY_MATRIX_MAX_FEATURES}")

        # Single round-trip; preserve the caller's order via a manual lookup
        # since SQL ``IN`` returns whatever order the engine prefers.
        with self.session() as s:
            rows = (
                s.execute(
                    text("SELECT id, name, dtype, description, tags, stats FROM features WHERE id IN :ids").bindparams(
                        bindparam("ids", expanding=True)
                    ),
                    {"ids": feature_ids},
                )
                .mappings()
                .all()
            )
        by_id = {r["id"]: dict(r) for r in rows}
        missing = [fid for fid in feature_ids if fid not in by_id]
        if missing:
            raise KeyError(missing)
        ordered = [by_id[fid] for fid in feature_ids]

        all_docs = self.get_all_feature_docs()

        def _brief(idx: int) -> dict:
            r = ordered[idx]
            src = r["name"].split(".")[0] if "." in r["name"] else ""
            return {
                "id": r["id"],
                "name": r["name"],
                "dtype": r["dtype"] or "",
                "source": src,
                "has_doc": r["id"] in all_docs,
            }

        features = [_brief(i) for i in range(len(ordered))]

        # Two features and below: no off-diagonal pair possible besides (0,1).
        if len(ordered) < 2:
            return features, []

        _, matrix, _ = self._build_corpus(ordered)
        sim_matrix = cosine_similarity(matrix)

        cells: list[dict] = []
        n = len(ordered)
        for i in range(n):
            for j in range(i + 1, n):
                score = float(sim_matrix[i, j])
                if score >= threshold:
                    cells.append({"a": i, "b": j, "score": round(score, 4)})
        return features, cells

    def compute_pair_reasons(self, a_id: str, b_id: str) -> tuple[dict, dict, float, list[dict]]:
        """Score a single pair and return its reason-code breakdown.

        Used by the matrix view's cell-click panel: keeps the matrix payload
        small (scores only) while still allowing on-demand reason inspection
        per pair. The reason-code structure matches what
        :meth:`find_duplicate_pairs` returns so the UI can render both
        identically.

        Returns ``(brief_a, brief_b, score, reasons)``.

        Raises:
            ValueError: when ``a_id == b_id``.
            KeyError: when either id is not in the catalog.
        """
        from sklearn.metrics.pairwise import cosine_similarity

        if a_id == b_id:
            raise ValueError("a_id and b_id must differ")

        with self.session() as s:
            rows = (
                s.execute(
                    text("SELECT id, name, dtype, description, tags, stats FROM features WHERE id IN :ids").bindparams(
                        bindparam("ids", expanding=True)
                    ),
                    {"ids": [a_id, b_id]},
                )
                .mappings()
                .all()
            )
        by_id = {r["id"]: dict(r) for r in rows}
        missing = [fid for fid in (a_id, b_id) if fid not in by_id]
        if missing:
            raise KeyError(missing)

        row_a, row_b = by_id[a_id], by_id[b_id]
        _, matrix, _ = self._build_corpus([row_a, row_b])
        score = float(cosine_similarity(matrix[0:1], matrix[1:2])[0, 0])

        all_docs = self.get_all_feature_docs()

        def _brief(r: dict) -> dict:
            src = r["name"].split(".")[0] if "." in r["name"] else ""
            return {
                "id": r["id"],
                "name": r["name"],
                "dtype": r["dtype"] or "",
                "source": src,
                "has_doc": r["id"] in all_docs,
            }

        reasons = _compute_pair_reasons(
            row_a["name"],
            row_a["dtype"],
            _parse_stats(row_a.get("stats")),
            row_b["name"],
            row_b["dtype"],
            _parse_stats(row_b.get("stats")),
            score,
        )
        return _brief(row_a), _brief(row_b), round(score, 4), reasons

    # --- Recommend by use-case text (T-similarity-refactor) ---

    def recommend_by_text(self, use_case: str, top_k: int = 10) -> list[tuple[Feature, float]]:
        """Rank features by TF-IDF cosine against ``use_case`` text.

        Deterministic fallback for the recommend endpoint when the LLM path
        is unavailable or times out. Returns ``[(Feature, score), …]`` sorted
        by score desc, capped at ``top_k`` and filtered to ``score > 0.05``.
        """
        import numpy as np
        from sklearn.metrics.pairwise import cosine_similarity

        with self.session() as s:
            rows = s.execute(text("SELECT id, name, dtype, description, tags FROM features")).mappings().all()
        if not rows:
            return []

        row_dicts = [dict(r) for r in rows]
        vectorizer, matrix, ids = self._build_corpus(row_dicts)
        query_vec = vectorizer.transform([use_case])
        sims = cosine_similarity(query_vec, matrix)[0]

        order = np.argsort(-sims)
        results: list[tuple[Feature, float]] = []
        for idx in order:
            score = float(sims[idx])
            if score <= 0.05:
                break
            fid = ids[idx]
            feat = self.get_feature_by_name_or_id(fid)
            if feat is None:
                continue
            results.append((feat, score))
            if len(results) >= top_k:
                break
        return results

    # --- Feature lifecycle status (T3.1) ---

    VALID_STATUSES = frozenset({"draft", "reviewed", "certified", "deprecated"})

    def get_feature_by_name_or_id(self, key: str) -> Feature | None:
        """Look up by id, fall back to name. Used by status routes/CLI so
        callers can use whichever feels natural."""
        with self.session() as s:
            row = s.execute(text("SELECT * FROM features WHERE id = :k"), {"k": key}).mappings().first()
            if row is None:
                row = s.execute(text("SELECT * FROM features WHERE name = :k"), {"k": key}).mappings().first()
            return _row_to_feature(row) if row else None

    def check_certification_readiness(self, feature_id: str) -> dict:
        """Return ``{ready: bool, missing: list[str]}`` for a feature.

        Checklist (per spec): doc + source-link + baseline + owner +
        (group membership OR explicit ``standalone`` tag). ``standalone`` is
        recorded in ``feature.tags`` since we don't have a dedicated column.
        """
        feat = self.get_feature_by_name_or_id(feature_id)
        if feat is None:
            return {"ready": False, "missing": ["feature_not_found"]}
        missing: list[str] = []
        doc = self.get_feature_doc(feat.id)
        if not doc or not (doc.get("short_description") or "").strip():
            missing.append("documentation")
        if not feat.data_source_id:
            missing.append("data_source")
        if self.get_baseline(feat.id) is None:
            missing.append("baseline")
        if not (feat.owner or "").strip():
            missing.append("owner")
        with self.session() as s:
            in_group = s.execute(
                text("SELECT 1 FROM feature_group_members WHERE feature_id = :id LIMIT 1"),
                {"id": feat.id},
            ).first()
        if not in_group and "standalone" not in (feat.tags or []):
            missing.append("group_membership_or_standalone")
        return {"ready": not missing, "missing": missing}

    def set_feature_status(self, feature_id: str, status: str, notes: str | None = None) -> dict:
        """Transition a feature's lifecycle status.

        Only ``certified`` is gated by the readiness checklist; other
        transitions are unconditional. Snapshots through ``feature_versions``
        with ``change_type='status'`` so the audit log captures every transition.

        Returns ``{ok, status, missing}``. ``ok=False`` (with the missing
        items) when the certified gate fails; the feature's status is
        unchanged in that case.
        """
        if status not in self.VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(self.VALID_STATUSES)}, got {status!r}")
        feat = self.get_feature_by_name_or_id(feature_id)
        if feat is None:
            raise ValueError(f"Feature not found: {feature_id}")
        if status == "certified":
            readiness = self.check_certification_readiness(feat.id)
            if not readiness["ready"]:
                return {"ok": False, "status": feat.status, "missing": readiness["missing"]}
        old_status = feat.status
        now = _utcnow()
        with self.session() as s:
            s.execute(
                text(
                    "UPDATE features SET status = :status, status_changed_at = :now, "
                    "status_notes = :notes, updated_at = :now WHERE id = :id"
                ),
                {"status": status, "now": now, "notes": notes, "id": feat.id},
            )
            s.commit()
        if old_status != status:
            from .usage import resolve_user

            self._snapshot_feature(
                feat.id,
                {"status": (old_status, status)},
                changed_by=resolve_user(),
                change_type="status",
            )
        return {"ok": True, "status": status, "missing": []}

    def list_features_by_status(self, status: str) -> list[Feature]:
        if status not in self.VALID_STATUSES:
            raise ValueError(f"status must be one of {sorted(self.VALID_STATUSES)}, got {status!r}")
        with self.session() as s:
            rows = (
                s.execute(
                    text("SELECT * FROM features WHERE status = :status ORDER BY name"),
                    {"status": status},
                )
                .mappings()
                .all()
            )
        return [_row_to_feature(r) for r in rows]

    def get_status_counts(self) -> dict:
        """Return per-status feature counts via a single ``GROUP BY status``.

        Cheaper than ``list_features() -> count`` at 5k+ features (Dashboard
        certification tile is the primary caller). Unknown / NULL status
        values fall through into ``draft`` to match the default-on-insert
        semantics so the dashboard never silently drops rows.
        """
        counts: dict[str, int] = {"draft": 0, "reviewed": 0, "certified": 0, "deprecated": 0}
        with self.session() as s:
            rows = s.execute(text("SELECT status, COUNT(*) AS n FROM features GROUP BY status")).mappings().all()
        for r in rows:
            status = r["status"]
            if status in counts:
                counts[status] += int(r["n"] or 0)
            else:
                # NULL or unexpected status string — fold into draft, matching
                # the column default so the totals stay consistent with what
                # the Features list shows.
                counts["draft"] += int(r["n"] or 0)
        counts["total"] = sum(counts.values())
        return counts

    # --- In-app notifications (T2.1, in-web only) ---

    def create_notification(
        self,
        kind: str,
        title: str,
        body: str = "",
        severity: str = "info",
        feature_id: str | None = None,
        link: str | None = None,
    ) -> str:
        """Insert an in-app notification. Returns the new id.

        Caller-style: best-effort fire-and-forget. Hook sites (monitoring,
        action items) wrap this in ``contextlib.suppress(Exception)`` so a
        notifications-table outage never breaks the parent operation.
        """
        nid = _new_id()
        with self.session() as s:
            s.execute(
                text(
                    "INSERT INTO notifications "
                    "(id, kind, title, body, severity, feature_id, link, created_at, read_at) "
                    "VALUES (:id, :kind, :title, :body, :severity, :fid, :link, :now, NULL)"
                ),
                {
                    "id": nid,
                    "kind": kind,
                    "title": title,
                    "body": body,
                    "severity": severity,
                    "fid": feature_id,
                    "link": link,
                    "now": _utcnow(),
                },
            )
            s.commit()
        return nid

    def list_notifications(self, *, unread_only: bool = False, limit: int = 50, offset: int = 0) -> list[dict]:
        clauses = []
        params: dict[str, Any] = {"lim": limit, "off": offset}
        if unread_only:
            clauses.append("read_at IS NULL")
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT id, kind, title, body, severity, feature_id, link, created_at, read_at "  # noqa: S608
            f"FROM notifications {where} ORDER BY created_at DESC LIMIT :lim OFFSET :off"
        )
        with self.session() as s:
            rows = s.execute(text(sql), params).mappings().all()
        return [dict(r) for r in rows]

    def count_unread_notifications(self) -> int:
        with self.session() as s:
            return int(s.execute(text("SELECT COUNT(*) FROM notifications WHERE read_at IS NULL")).scalar() or 0)

    def mark_notification_read(self, notification_id: str) -> bool:
        with self.session() as s:
            result = s.execute(
                text("UPDATE notifications SET read_at = :now WHERE id = :id AND read_at IS NULL"),
                {"now": _utcnow(), "id": notification_id},
            )
            s.commit()
            return result.rowcount > 0  # type: ignore[attr-defined]

    def mark_all_notifications_read(self) -> int:
        with self.session() as s:
            result = s.execute(
                text("UPDATE notifications SET read_at = :now WHERE read_at IS NULL"),
                {"now": _utcnow()},
            )
            s.commit()
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    # --- Bulk operations (T1.3a) ---

    BULK_MAX_IDS = 1000  # spec ceiling — guard a single request from being unbounded

    def _validate_feature_ids(self, feature_ids: list[str]) -> tuple[list[str], list[str]]:
        """Return ``(valid, invalid)`` partition. ``feature_ids`` is unbounded
        in size at this layer; route layer enforces ``BULK_MAX_IDS``."""
        if not feature_ids:
            return [], []
        from sqlalchemy import bindparam

        with self.session() as s:
            rows = (
                s.execute(
                    text("SELECT id FROM features WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
                    {"ids": list(feature_ids)},
                )
                .scalars()
                .all()
            )
        found = set(rows)
        valid = [fid for fid in feature_ids if fid in found]
        invalid = [fid for fid in feature_ids if fid not in found]
        return valid, invalid

    def bulk_update_tags(
        self,
        feature_ids: list[str],
        action: str,
        tags: list[str],
    ) -> int:
        """Apply a tag change to many features at once.

        ``action`` is one of:
        - ``add`` — union with existing tags
        - ``remove`` — set difference
        - ``replace`` — overwrite
        Returns count of features updated. Each call routes through
        ``update_feature_tags`` so feature_versions snapshots are created
        as usual — meaning a bulk-tag change is fully reflected in the
        per-feature audit log without a new audit_log table.
        """
        if action not in {"add", "remove", "replace"}:
            raise ValueError(f"action must be one of add/remove/replace, got {action!r}")
        updated = 0
        with self.session() as s:
            from sqlalchemy import bindparam

            rows = (
                s.execute(
                    text("SELECT id, tags FROM features WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
                    {"ids": list(feature_ids)},
                )
                .mappings()
                .all()
            )
        tag_set = set(tags)
        for r in rows:
            current_raw = r["tags"]
            current = json.loads(current_raw) if isinstance(current_raw, str) and current_raw else []
            if action == "add":
                new_tags = list(set(current) | tag_set)
            elif action == "remove":
                new_tags = [t for t in current if t not in tag_set]
            else:  # replace
                new_tags = list(tags)
            if sorted(new_tags) == sorted(current):
                continue
            self.update_feature_tags(r["id"], new_tags)
            updated += 1
        return updated

    def bulk_group_action(self, group_id: str, feature_ids: list[str], action: str) -> int:
        """Add/remove many features to/from a group. Returns rows actually
        changed (idempotent — re-adding members counts 0)."""
        if action not in {"add_to", "remove_from"}:
            raise ValueError(f"action must be add_to or remove_from, got {action!r}")
        if action == "add_to":
            return self.add_group_members(group_id, feature_ids)
        from sqlalchemy import bindparam

        with self.session() as s:
            result = s.execute(
                text("DELETE FROM feature_group_members WHERE group_id = :gid AND feature_id IN :ids").bindparams(
                    bindparam("ids", expanding=True)
                ),
                {"gid": group_id, "ids": list(feature_ids)},
            )
            s.commit()
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    def bulk_delete_features(self, feature_ids: list[str]) -> int:
        """Delete many features. Cleans up child rows whose FK to ``features``
        is NOT configured ON DELETE CASCADE (feature_docs, monitoring_baselines,
        monitoring_checks, usage_log) before issuing the main DELETE.
        CASCADE-configured tables (feature_versions, feature_group_members,
        feature_lineage, action_items) clean up automatically.
        """
        if not feature_ids:
            return 0
        from sqlalchemy import bindparam

        non_cascade_cleanup = (
            "DELETE FROM feature_docs WHERE feature_id IN :ids",
            "DELETE FROM monitoring_baselines WHERE feature_id IN :ids",
            "DELETE FROM monitoring_checks WHERE feature_id IN :ids",
            "DELETE FROM usage_log WHERE feature_id IN :ids",
        )
        with self.session() as s:
            for stmt in non_cascade_cleanup:
                s.execute(
                    text(stmt).bindparams(bindparam("ids", expanding=True)),
                    {"ids": list(feature_ids)},
                )
            result = s.execute(
                text("DELETE FROM features WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
                {"ids": list(feature_ids)},
            )
            s.commit()
            return int(result.rowcount or 0)  # type: ignore[attr-defined]

    # --- Lineage ---

    def add_lineage(
        self,
        child_feature_id: str,
        parent_feature_id: str,
        transform: str = "",
        detected_method: str = "manual",
    ) -> None:
        """Record a feature→feature lineage edge.

        ``detected_method`` defaults to 'manual'; the auto-detect path
        (T1.1b sqlglot parser) passes 'sql_parse'. The unique-constraint
        target was widened in T1.1 to cover the new (parent_type,
        parent_source_id, parent_column) discriminators, so the conflict
        target now lists all five.
        """
        with self.session() as s:
            s.execute(
                text(
                    "INSERT INTO feature_lineage "
                    "(id, child_feature_id, parent_type, parent_feature_id, "
                    " parent_source_id, parent_column, transform, "
                    " detected_method, created_at) "
                    "VALUES (:id, :cid, 'feature', :pid, NULL, NULL, :transform, "
                    "        :method, :now) "
                    "ON CONFLICT (child_feature_id, parent_type, parent_feature_id, "
                    "             parent_source_id, parent_column) DO NOTHING"
                ),
                {
                    "id": _new_id(),
                    "cid": child_feature_id,
                    "pid": parent_feature_id,
                    "transform": transform,
                    "method": detected_method,
                    "now": _utcnow(),
                },
            )
            s.commit()

    def add_source_lineage(
        self,
        child_feature_id: str,
        source_id: str,
        column_name: str,
        transform: str = "",
        detected_method: str = "manual",
    ) -> None:
        """Record a source-column→feature lineage edge (T1.1).

        Use this when a feature is derived directly from a raw column on a
        data source rather than from another feature. ``column_name`` is the
        column on ``source_id``'s parquet/table that the feature reads from.
        """
        with self.session() as s:
            s.execute(
                text(
                    "INSERT INTO feature_lineage "
                    "(id, child_feature_id, parent_type, parent_feature_id, "
                    " parent_source_id, parent_column, transform, "
                    " detected_method, created_at) "
                    "VALUES (:id, :cid, 'source_column', NULL, :sid, :col, "
                    "        :transform, :method, :now) "
                    "ON CONFLICT (child_feature_id, parent_type, parent_feature_id, "
                    "             parent_source_id, parent_column) DO NOTHING"
                ),
                {
                    "id": _new_id(),
                    "cid": child_feature_id,
                    "sid": source_id,
                    "col": column_name,
                    "transform": transform,
                    "method": detected_method,
                    "now": _utcnow(),
                },
            )
            s.commit()

    def remove_lineage(self, child_feature_id: str, parent_feature_id: str) -> None:
        """Remove a feature→feature lineage edge.

        Source-column edges are removed via ``remove_source_lineage`` —
        they're keyed differently and matching them by parent_feature_id
        wouldn't work (it's NULL for source-column rows).
        """
        with self.session() as s:
            s.execute(
                text(
                    "DELETE FROM feature_lineage "
                    "WHERE child_feature_id = :cid "
                    "  AND parent_type = 'feature' "
                    "  AND parent_feature_id = :pid"
                ),
                {"cid": child_feature_id, "pid": parent_feature_id},
            )
            s.commit()

    def remove_source_lineage(self, child_feature_id: str, source_id: str, column_name: str) -> None:
        with self.session() as s:
            s.execute(
                text(
                    "DELETE FROM feature_lineage "
                    "WHERE child_feature_id = :cid "
                    "  AND parent_type = 'source_column' "
                    "  AND parent_source_id = :sid "
                    "  AND parent_column = :col"
                ),
                {"cid": child_feature_id, "sid": source_id, "col": column_name},
            )
            s.commit()

    def get_impact(self, source_name: str, column: str | None = None, max_depth: int = 5) -> list[dict]:
        """Impact analysis: which features depend on this source[.column]?

        Returns features that are direct downstream of the source-column edge,
        plus features transitively downstream via feature→feature edges, up
        to ``max_depth`` hops.

        Each item: ``{name, dtype, depth, via}`` where ``via`` describes how
        the impact propagates (the immediate parent name in the chain).
        """
        source = self.get_source_by_name(source_name)
        if source is None:
            return []

        # Step 1: direct children of this source[.column].
        params: dict[str, Any] = {"sid": source.id}
        col_clause = ""
        if column is not None:
            col_clause = " AND fl.parent_column = :col"
            params["col"] = column
        sql_direct = (
            "SELECT f.id, f.name, f.dtype, fl.parent_column, fl.transform "
            "FROM feature_lineage fl JOIN features f ON fl.child_feature_id = f.id "
            "WHERE fl.parent_type = 'source_column' AND fl.parent_source_id = :sid" + col_clause
        )
        with self.session() as s:
            direct_rows = s.execute(text(sql_direct), params).mappings().all()

        if not direct_rows:
            return []

        impact: dict[str, dict[str, Any]] = {}  # feature_id → record (dedupe across paths)
        frontier: list[tuple[str, str, int]] = []  # (feature_id, via_name, depth)
        for r in direct_rows:
            fid = r["id"]
            via = f"{source.name}.{r['parent_column']}" if r["parent_column"] else source.name
            impact[fid] = {"name": r["name"], "dtype": r["dtype"], "depth": 1, "via": via}
            frontier.append((fid, r["name"], 1))

        # Step 2: BFS through feature→feature edges up to max_depth.
        while frontier:
            next_frontier: list[tuple[str, str, int]] = []
            ids = [fid for fid, _via, depth in frontier if depth < max_depth]
            if not ids:
                break
            from sqlalchemy import bindparam

            with self.session() as s:
                rows = (
                    s.execute(
                        text(
                            "SELECT fl.parent_feature_id, fl.child_feature_id, "
                            "       f.id, f.name, f.dtype, fp.name AS parent_name "
                            "FROM feature_lineage fl "
                            "JOIN features f ON fl.child_feature_id = f.id "
                            "JOIN features fp ON fl.parent_feature_id = fp.id "
                            "WHERE fl.parent_type = 'feature' "
                            "  AND fl.parent_feature_id IN :ids"
                        ).bindparams(bindparam("ids", expanding=True)),
                        {"ids": ids},
                    )
                    .mappings()
                    .all()
                )
            # Find source depth of each parent we just queried.
            depth_by_id = {fid: depth for fid, _via, depth in frontier}
            for r in rows:
                child_id = r["id"]
                if child_id in impact:
                    continue  # first-found depth wins
                parent_depth = depth_by_id.get(r["parent_feature_id"], max_depth)
                new_depth = parent_depth + 1
                impact[child_id] = {
                    "name": r["name"],
                    "dtype": r["dtype"],
                    "depth": new_depth,
                    "via": r["parent_name"],
                }
                next_frontier.append((child_id, r["name"], new_depth))
            frontier = next_frontier

        return sorted(impact.values(), key=lambda d: (d["depth"], d["name"]))

    def get_lineage_graph(self) -> dict:
        with self.session() as s:
            edges_rows = (
                s.execute(
                    text(
                        "SELECT fl.child_feature_id, fl.parent_feature_id, fl.transform, fl.created_at, "
                        "       fc.name as child_name, fp.name as parent_name "
                        "FROM feature_lineage fl "
                        "JOIN features fc ON fl.child_feature_id = fc.id "
                        "JOIN features fp ON fl.parent_feature_id = fp.id"
                    )
                )
                .mappings()
                .all()
            )

            if not edges_rows:
                return {"nodes": [], "edges": []}

            feature_ids: set[str] = set()
            edges = []
            for r in edges_rows:
                feature_ids.add(r["child_feature_id"])
                feature_ids.add(r["parent_feature_id"])
                ca = r["created_at"]
                edges.append(
                    {
                        "source": r["parent_name"],
                        "target": r["child_name"],
                        "transform": r["transform"] or "",
                        "created_at": ca.isoformat() if hasattr(ca, "isoformat") else ca,
                    }
                )

            # IN clauses with named param expansion: SA 2.x supports
            # ``WHERE x IN :ids`` + ``bindparams(bindparam('ids', expanding=True))``.
            # Equivalent to building a placeholder list, but portable across dialects.
            from sqlalchemy import bindparam

            feat_rows = (
                s.execute(
                    text("SELECT * FROM features WHERE id IN :ids").bindparams(bindparam("ids", expanding=True)),
                    {"ids": list(feature_ids)},
                )
                .mappings()
                .all()
            )

            doc_id_rows = (
                s.execute(
                    text(
                        "SELECT feature_id FROM feature_docs WHERE feature_id IN :ids "
                        "AND short_description IS NOT NULL AND short_description != ''"
                    ).bindparams(bindparam("ids", expanding=True)),
                    {"ids": list(feature_ids)},
                )
                .mappings()
                .all()
            )
            doc_ids = {r["feature_id"] for r in doc_id_rows}

            drift_map: dict[str, str] = {}
            for fid in feature_ids:
                row = s.execute(
                    text(
                        "SELECT severity FROM monitoring_checks "
                        "WHERE feature_id = :fid ORDER BY checked_at DESC LIMIT 1"
                    ),
                    {"fid": fid},
                ).first()
                if row:
                    drift_map[fid] = row[0]

        nodes = []
        for r in feat_rows:
            f = _row_to_feature(r)
            src = f.name.split(".")[0] if "." in f.name else ""
            nodes.append(
                {
                    "id": f.name,
                    "spec": f.name,
                    "source": src,
                    "dtype": f.dtype,
                    "has_doc": f.id in doc_ids,
                    "drift_status": drift_map.get(f.id, "healthy"),
                }
            )

        return {"nodes": nodes, "edges": edges}

    def get_feature_lineage(self, feature_name: str, direction: str = "both", depth: int = 3) -> dict:
        feature = self.get_feature_by_name(feature_name)
        if feature is None:
            return {"feature": None, "parents": [], "children": []}

        root = {
            "spec": feature.name,
            "dtype": feature.dtype,
            "source": feature.name.split(".")[0] if "." in feature.name else "",
        }

        def _get_parents(fid: str, d: int) -> list[dict]:
            if d <= 0:
                return []
            with self.session() as s:
                rows = (
                    s.execute(
                        text(
                            "SELECT fp.id, fp.name, fp.dtype, fl.transform "
                            "FROM feature_lineage fl "
                            "JOIN features fp ON fl.parent_feature_id = fp.id "
                            "WHERE fl.child_feature_id = :fid"
                        ),
                        {"fid": fid},
                    )
                    .mappings()
                    .all()
                )
            return [
                {
                    "spec": r["name"],
                    "transform": r["transform"] or "",
                    "dtype": r["dtype"],
                    "parents": _get_parents(r["id"], d - 1),
                }
                for r in rows
            ]

        def _get_children(fid: str, d: int) -> list[dict]:
            if d <= 0:
                return []
            with self.session() as s:
                rows = (
                    s.execute(
                        text(
                            "SELECT fc.id, fc.name, fc.dtype, fl.transform "
                            "FROM feature_lineage fl "
                            "JOIN features fc ON fl.child_feature_id = fc.id "
                            "WHERE fl.parent_feature_id = :fid"
                        ),
                        {"fid": fid},
                    )
                    .mappings()
                    .all()
                )
            return [
                {
                    "spec": r["name"],
                    "transform": r["transform"] or "",
                    "dtype": r["dtype"],
                    "children": _get_children(r["id"], d - 1),
                }
                for r in rows
            ]

        parents = _get_parents(feature.id, depth) if direction in ("both", "up") else []
        children = _get_children(feature.id, depth) if direction in ("both", "down") else []
        return {"feature": root, "parents": parents, "children": children}

    # --- Action Items ---

    @staticmethod
    def _row_to_action_item(row: Any) -> dict:
        d = dict(row)
        ctx = d.get("context_json")
        d["context"] = json.loads(ctx) if isinstance(ctx, str) and ctx else {}
        d.pop("context_json", None)
        for k in ("created_at", "updated_at", "applied_at"):
            v = d.get(k)
            if isinstance(v, datetime):
                d[k] = v.isoformat()
        return d

    def create_action_item(
        self,
        feature_id: str,
        source: str,
        title: str,
        recommendation: str,
        context: dict | None = None,
        created_by: str = "",
    ) -> str:
        item_id = _new_id()
        now = _utcnow()
        with self.session() as s:
            s.execute(
                text(
                    "INSERT INTO action_items "
                    "(id, feature_id, source, title, recommendation, status, "
                    " created_by, applied_by, change_summary, context_json, "
                    " created_at, updated_at) "
                    "VALUES (:id, :fid, :src, :title, :rec, 'pending', "
                    "        :created_by, '', '', :ctx, :now, :now)"
                ),
                {
                    "id": item_id,
                    "fid": feature_id,
                    "src": source,
                    "title": title,
                    "rec": recommendation,
                    "created_by": created_by,
                    "ctx": json.dumps(context or {}, default=str),
                    "now": now,
                },
            )
            s.commit()
        # T2.1 — also emit an in-app notification so the bell icon picks
        # this up. Fire-and-forget; outages here don't fail the action_item write.
        import contextlib as _ctx

        with _ctx.suppress(Exception):
            self.create_notification(
                kind="action",
                title=f"New action item: {title}",
                body=recommendation,
                severity="info",
                feature_id=feature_id,
                link=f"/actions?id={item_id}",
            )
        return item_id

    def find_pending_action(self, feature_id: str, source: str, title: str) -> dict | None:
        with self.session() as s:
            row = (
                s.execute(
                    text(
                        "SELECT * FROM action_items "
                        "WHERE feature_id = :fid AND source = :src AND title = :title AND status = 'pending' "
                        "ORDER BY created_at DESC LIMIT 1"
                    ),
                    {"fid": feature_id, "src": source, "title": title},
                )
                .mappings()
                .first()
            )
            return self._row_to_action_item(row) if row else None

    def list_action_items(
        self,
        feature_id: str | None = None,
        status: str | None = None,
        source: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        clauses: list[str] = []
        params: dict[str, Any] = {"lim": limit, "off": offset}
        if feature_id:
            clauses.append("a.feature_id = :fid")
            params["fid"] = feature_id
        if status:
            # Qualify with ``a.`` to disambiguate from features.status (T3.1
            # added a status column to features that collides without prefix).
            clauses.append("a.status = :status")
            params["status"] = status
        if source:
            clauses.append("a.source = :src")
            params["src"] = source
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = (
            f"SELECT a.*, f.name AS feature_name FROM action_items a "  # noqa: S608
            f"JOIN features f ON a.feature_id = f.id {where} "
            f"ORDER BY a.created_at DESC LIMIT :lim OFFSET :off"
        )
        with self.session() as s:
            rows = s.execute(text(sql), params).mappings().all()
            return [self._row_to_action_item(r) for r in rows]

    def get_action_item(self, item_id: str) -> dict | None:
        with self.session() as s:
            row = (
                s.execute(
                    text(
                        "SELECT a.*, f.name AS feature_name FROM action_items a "
                        "JOIN features f ON a.feature_id = f.id "
                        "WHERE a.id = :id"
                    ),
                    {"id": item_id},
                )
                .mappings()
                .first()
            )
            return self._row_to_action_item(row) if row else None

    def update_action_item_status(
        self,
        item_id: str,
        status: str,
        applied_by: str = "",
        change_summary: str = "",
    ) -> bool:
        valid = {"pending", "applied", "dismissed", "snoozed"}
        if status not in valid:
            raise ValueError(f"Invalid status: {status}. Must be one of {valid}.")
        now = _utcnow()
        applied_at = now if status == "applied" else None
        with self.session() as s:
            result = s.execute(
                text(
                    "UPDATE action_items "
                    "SET status = :status, applied_by = :applied_by, change_summary = :summary, "
                    "    applied_at = :applied_at, updated_at = :now "
                    "WHERE id = :id"
                ),
                {
                    "status": status,
                    "applied_by": applied_by,
                    "summary": change_summary,
                    "applied_at": applied_at,
                    "now": now,
                    "id": item_id,
                },
            )
            s.commit()
            return result.rowcount > 0  # type: ignore[attr-defined]

    def count_action_items(self, status: str | None = None) -> int:
        with self.session() as s:
            if status:
                row = s.execute(
                    text("SELECT COUNT(*) AS n FROM action_items WHERE status = :status"),
                    {"status": status},
                ).first()
            else:
                row = s.execute(text("SELECT COUNT(*) AS n FROM action_items")).first()
            return int(row[0]) if row else 0

    def save_monitoring_llm_analysis(self, feature_id: str, analysis: dict) -> None:
        """Persist LLM analysis JSON onto the latest monitoring_checks row."""
        with self.session() as s:
            row = s.execute(
                text("SELECT id FROM monitoring_checks WHERE feature_id = :fid ORDER BY checked_at DESC LIMIT 1"),
                {"fid": feature_id},
            ).first()
            if row is None:
                return
            s.execute(
                text("UPDATE monitoring_checks SET llm_analysis_json = :payload WHERE id = :id"),
                {"payload": json.dumps(analysis, default=str), "id": row[0]},
            )
            s.commit()
