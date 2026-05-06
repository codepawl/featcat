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

from sqlalchemy import text
from sqlalchemy.exc import OperationalError

from ..db.connection import make_engine, make_session_factory, resolve_backend
from ..db.models import Base
from .backend import CatalogBackend
from .models import DataSource, Feature, FeatureGroup, _new_id

if TYPE_CHECKING:
    from collections.abc import Iterator

    from sqlalchemy.orm import Session

DEFAULT_DB = "catalog.db"


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
            "ALTER TABLE feature_docs ADD COLUMN hints_used TEXT",
            "ALTER TABLE feature_docs ADD COLUMN context_features TEXT",
            "ALTER TABLE feature_versions ADD COLUMN change_type TEXT DEFAULT 'metadata'",
            "ALTER TABLE feature_versions ADD COLUMN previous_value TEXT",
            "ALTER TABLE feature_versions ADD COLUMN new_value TEXT",
            "ALTER TABLE monitoring_checks ADD COLUMN llm_analysis_json TEXT",
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

    def save_monitoring_result(self, feature_id: str, feature_name: str, psi: float | None, severity: str) -> None:
        with self.session() as s:
            s.execute(
                text(
                    "INSERT INTO monitoring_checks "
                    "(id, feature_id, feature_name, psi, severity, checked_at) "
                    "VALUES (:id, :fid, :name, :psi, :sev, :now)"
                ),
                {
                    "id": _new_id(),
                    "fid": feature_id,
                    "name": feature_name,
                    "psi": psi,
                    "sev": severity,
                    "now": _utcnow(),
                },
            )
            s.commit()

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
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.metrics.pairwise import cosine_similarity

        ids: list[str] = []
        corpus: list[str] = []
        ref_idx: int | None = None
        for i, r in enumerate(rows):
            ids.append(r["id"])
            text_blob = r["name"].replace("_", " ").replace(".", " ")
            tags = r["tags"]
            if isinstance(tags, str) and tags:
                with contextlib.suppress(json.JSONDecodeError):
                    text_blob += " " + " ".join(json.loads(tags))
            if r["description"]:
                text_blob += " " + r["description"]
            corpus.append(text_blob)
            if r["id"] == feature_id:
                ref_idx = i
        if ref_idx is None:
            return []

        vectorizer = TfidfVectorizer(ngram_range=(1, 2), min_df=1)
        matrix = vectorizer.fit_transform(corpus)
        # cosine_similarity accepts sparse matrices; cast keeps the type-checker
        # happy on the slice (sklearn returns scipy.sparse.spmatrix which lacks
        # __getitem__ in mypy stubs).
        ref_row = matrix[ref_idx : ref_idx + 1]
        sims = cosine_similarity(ref_row, matrix)[0]
        # Argsort descending excluding self.
        order = np.argsort(-sims)
        result: list[dict] = []
        for idx in order:
            if idx == ref_idx:
                continue
            sim = float(sims[idx])
            if sim <= 0:
                break  # cosine of zero-vector pair → unrelated; stop early
            row = rows[idx]
            result.append({"id": row["id"], "name": row["name"], "dtype": row["dtype"], "similarity": sim})
            if len(result) >= top_k:
                break
        return result

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
            clauses.append("feature_id = :fid")
            params["fid"] = feature_id
        if status:
            clauses.append("status = :status")
            params["status"] = status
        if source:
            clauses.append("source = :src")
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
