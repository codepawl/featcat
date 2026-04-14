"""Local SQLite backend for the feature catalog."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from .backend import CatalogBackend
from .models import DataSource, Feature

DEFAULT_DB = "catalog.db"

SCHEMA_SQL = """\
CREATE TABLE IF NOT EXISTS data_sources (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    path TEXT NOT NULL,
    storage_type TEXT NOT NULL DEFAULT 'local',
    format TEXT NOT NULL DEFAULT 'parquet',
    description TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS features (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    data_source_id TEXT NOT NULL REFERENCES data_sources(id),
    column_name TEXT NOT NULL,
    dtype TEXT DEFAULT '',
    description TEXT DEFAULT '',
    tags TEXT DEFAULT '[]',
    owner TEXT DEFAULT '',
    stats TEXT DEFAULT '{}',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL,
    UNIQUE(data_source_id, column_name)
);

CREATE TABLE IF NOT EXISTS feature_docs (
    feature_id TEXT NOT NULL REFERENCES features(id),
    short_description TEXT DEFAULT '',
    long_description TEXT DEFAULT '',
    expected_range TEXT DEFAULT '',
    potential_issues TEXT DEFAULT '',
    generated_at TIMESTAMP,
    model_used TEXT DEFAULT ''
);

CREATE TABLE IF NOT EXISTS monitoring_baselines (
    feature_id TEXT NOT NULL REFERENCES features(id),
    baseline_stats TEXT DEFAULT '{}',
    computed_at TIMESTAMP
);

CREATE TABLE IF NOT EXISTS job_schedules (
    job_name TEXT PRIMARY KEY,
    cron_expression TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    description TEXT DEFAULT '',
    max_log_retention_days INTEGER DEFAULT 30
);

CREATE TABLE IF NOT EXISTS job_logs (
    id TEXT PRIMARY KEY,
    job_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    duration_seconds REAL,
    result_summary TEXT DEFAULT '{}',
    error_message TEXT,
    triggered_by TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS feature_versions (
    id TEXT PRIMARY KEY,
    feature_id TEXT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    version INTEGER NOT NULL,
    snapshot TEXT NOT NULL,
    change_summary TEXT DEFAULT '',
    changed_by TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL,
    UNIQUE(feature_id, version)
);
"""


def _adapt_datetime(val: datetime) -> str:
    return val.isoformat()


def _convert_datetime(val: bytes) -> datetime:
    return datetime.fromisoformat(val.decode())


sqlite3.register_adapter(datetime, _adapt_datetime)
sqlite3.register_converter("TIMESTAMP", _convert_datetime)


def _row_to_feature(row: sqlite3.Row) -> Feature:
    """Convert a sqlite3.Row to a Feature model, parsing JSON fields."""
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


class LocalBackend(CatalogBackend):
    """SQLite-backed catalog backend."""

    def __init__(self, db_path: str = DEFAULT_DB) -> None:
        self.db_path = db_path
        self._lock = threading.RLock()
        self.conn = sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
            check_same_thread=False,
            timeout=30.0,  # 30 second timeout for lock contention
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def init_db(self) -> None:
        import contextlib

        self.conn.executescript(SCHEMA_SQL)
        # Add auto_refresh column if not present (added in Phase 6)
        with contextlib.suppress(sqlite3.OperationalError):
            self.conn.execute("ALTER TABLE data_sources ADD COLUMN auto_refresh INTEGER DEFAULT 0")
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- Sources ---

    def add_source(self, source: DataSource) -> DataSource:
        with self._lock:
            self.conn.execute(
                """INSERT INTO data_sources (id, name, path, storage_type, format, description, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    source.id,
                    source.name,
                    source.path,
                    source.storage_type,
                    source.format,
                    source.description,
                    source.created_at,
                    source.updated_at,
                ),
            )
            self.conn.commit()
        return source

    def get_source_by_name(self, name: str) -> DataSource | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM data_sources WHERE name = ?", (name,)).fetchone()
            if row is None:
                return None
            return DataSource(**dict(row))

    def list_sources(self) -> list[DataSource]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM data_sources ORDER BY created_at DESC").fetchall()
            return [DataSource(**dict(r)) for r in rows]

    # --- Features ---

    def upsert_feature(self, feature: Feature) -> Feature:
        with self._lock:
            self.conn.execute(
                """INSERT INTO features
                   (id, name, data_source_id, column_name, dtype, description, tags, owner, stats, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(data_source_id, column_name) DO UPDATE SET
                       dtype = excluded.dtype,
                       stats = excluded.stats,
                       updated_at = excluded.updated_at""",
                (
                    feature.id,
                    feature.name,
                    feature.data_source_id,
                    feature.column_name,
                    feature.dtype,
                    feature.description,
                    json.dumps(feature.tags),
                    feature.owner,
                    json.dumps(feature.stats),
                    feature.created_at,
                    feature.updated_at,
                ),
            )
            self.conn.commit()
        return feature

    def list_features(self, source_name: str | None = None) -> list[Feature]:
        with self._lock:
            if source_name:
                rows = self.conn.execute(
                    """SELECT f.* FROM features f
                       JOIN data_sources ds ON f.data_source_id = ds.id
                       WHERE ds.name = ?
                       ORDER BY f.name""",
                    (source_name,),
                ).fetchall()
            else:
                rows = self.conn.execute("SELECT * FROM features ORDER BY name").fetchall()
            return [_row_to_feature(r) for r in rows]

    def get_feature_by_name(self, name: str) -> Feature | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM features WHERE name = ?", (name,)).fetchone()
            if row is None:
                return None
            return _row_to_feature(row)

    _VERSIONED_FIELDS = frozenset({"description", "tags", "owner", "dtype", "column_name", "data_source_id"})

    def _snapshot_feature(self, feature_id: str, changes: dict[str, tuple], changed_by: str = "") -> None:
        from .models import _new_id

        with self._lock:
            row = self.conn.execute("SELECT * FROM features WHERE id = ?", (feature_id,)).fetchone()
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
            next_version = self.conn.execute(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM feature_versions WHERE feature_id = ?",
                (feature_id,),
            ).fetchone()[0]
            parts = [f"{field}: {old!r} -> {new!r}" for field, (old, new) in changes.items()]
            now = datetime.now(timezone.utc)
            self.conn.execute(
                """INSERT INTO feature_versions (id, feature_id, version, snapshot, change_summary, changed_by, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (_new_id(), feature_id, next_version, json.dumps(snapshot), "; ".join(parts), changed_by, now),
            )

    def update_feature_metadata(self, feature_id: str, _rollback_version: int | None = None, **kwargs) -> None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM features WHERE id = ?", (feature_id,)).fetchone()
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
            self._snapshot_feature(feature_id, changes, changed_by=kwargs.get("owner", current.get("owner", "")))
            if _rollback_version is not None:
                self.conn.execute(
                    "UPDATE feature_versions SET change_summary = 'rollback to v' || ? || ': ' || change_summary"
                    " WHERE feature_id = ? AND version = (SELECT MAX(version) FROM feature_versions WHERE feature_id = ?)",
                    (str(_rollback_version), feature_id, feature_id),
                )
            now = datetime.now(timezone.utc)
            sets, vals = [], []
            for k, v in kwargs.items():
                if k.startswith("_"):
                    continue
                if k == "tags":
                    sets.append("tags = ?")
                    vals.append(json.dumps(v))
                elif k in self._VERSIONED_FIELDS:
                    sets.append(f"{k} = ?")
                    vals.append(v)
            if sets:
                sets.append("updated_at = ?")
                vals.append(now)
                vals.append(feature_id)
                self.conn.execute(f"UPDATE features SET {', '.join(sets)} WHERE id = ?", vals)  # noqa: S608
            self.conn.commit()

    def update_feature_tags(self, feature_id: str, tags: list[str]) -> None:
        self.update_feature_metadata(feature_id, tags=tags)

    def search_features(self, query: str) -> list[Feature]:
        with self._lock:
            pattern = f"%{query}%"
            rows = self.conn.execute(
                """SELECT * FROM features
                   WHERE name LIKE ? OR description LIKE ? OR tags LIKE ? OR column_name LIKE ?
                   ORDER BY name""",
                (pattern, pattern, pattern, pattern),
            ).fetchall()
            return [_row_to_feature(r) for r in rows]

    def list_feature_versions(self, feature_id: str) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM feature_versions WHERE feature_id = ? ORDER BY version DESC",
                (feature_id,),
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["snapshot"] = (
                    json.loads(d["snapshot"]) if isinstance(d.get("snapshot"), str) else d.get("snapshot", {})
                )
                result.append(d)
            return result

    def get_feature_version(self, feature_id: str, version: int) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM feature_versions WHERE feature_id = ? AND version = ?",
                (feature_id, version),
            ).fetchone()
            if row is None:
                return None
            d = dict(row)
            d["snapshot"] = json.loads(d["snapshot"]) if isinstance(d.get("snapshot"), str) else d.get("snapshot", {})
            return d

    def rollback_feature(self, feature_id: str, version: int) -> dict:
        with self._lock:
            v = self.get_feature_version(feature_id, version)
            if v is None:
                msg = f"Version {version} not found for feature {feature_id}"
                raise ValueError(msg)
            snapshot = v["snapshot"]
            updates = {k: snapshot[k] for k in ("description", "tags", "owner", "dtype") if k in snapshot}
            self.update_feature_metadata(feature_id, _rollback_version=version, **updates)
            feature = self.conn.execute("SELECT * FROM features WHERE id = ?", (feature_id,)).fetchone()
            return dict(feature) if feature else {}

    # --- Feature Docs ---

    def get_feature_doc(self, feature_id: str) -> dict | None:
        with self._lock:
            row = self.conn.execute("SELECT * FROM feature_docs WHERE feature_id = ?", (feature_id,)).fetchone()
            if row is None:
                return None
            return dict(row)

    def save_feature_doc(self, feature_id: str, doc: dict, model_used: str = "unknown") -> None:
        def _str(val: object) -> str:
            if isinstance(val, list):
                return "; ".join(str(v) for v in val)
            return str(val) if val else ""

        with self._lock:
            now = datetime.now(timezone.utc)
            self.conn.execute("DELETE FROM feature_docs WHERE feature_id = ?", (feature_id,))
            self.conn.execute(
                """INSERT INTO feature_docs
                   (feature_id, short_description, long_description,
                    expected_range, potential_issues, generated_at, model_used)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    feature_id,
                    _str(doc.get("short_description", "")),
                    _str(doc.get("long_description", "")),
                    _str(doc.get("expected_range", "")),
                    _str(doc.get("potential_issues", "")),
                    now,
                    model_used,
                ),
            )
            self.conn.commit()

    def list_undocumented_features(self) -> list[Feature]:
        with self._lock:
            rows = self.conn.execute(
                """SELECT f.* FROM features f
                   LEFT JOIN feature_docs fd ON f.id = fd.feature_id
                   WHERE fd.feature_id IS NULL OR f.updated_at > fd.generated_at"""
            ).fetchall()
            return [_row_to_feature(r) for r in rows]

    def get_doc_stats(self) -> dict:
        with self._lock:
            total = self.conn.execute("SELECT COUNT(*) FROM features").fetchone()[0]
            documented = self.conn.execute("SELECT COUNT(DISTINCT feature_id) FROM feature_docs").fetchone()[0]
            return {
                "total_features": total,
                "documented": documented,
                "undocumented": total - documented,
                "coverage": round(documented / total * 100, 1) if total > 0 else 0.0,
            }

    def get_all_feature_docs(self) -> dict[str, dict]:
        with self._lock:
            rows = self.conn.execute("SELECT * FROM feature_docs").fetchall()
            return {row["feature_id"]: dict(row) for row in rows}

    # --- Monitoring Baselines ---

    def get_baseline(self, feature_id: str) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT baseline_stats FROM monitoring_baselines WHERE feature_id = ?",
                (feature_id,),
            ).fetchone()
            if row is None:
                return None
            stats = row[0]
            return json.loads(stats) if isinstance(stats, str) else stats

    def save_baseline(self, feature_id: str, stats: dict) -> None:
        with self._lock:
            now = datetime.now(timezone.utc)
            self.conn.execute("DELETE FROM monitoring_baselines WHERE feature_id = ?", (feature_id,))
            self.conn.execute(
                "INSERT INTO monitoring_baselines (feature_id, baseline_stats, computed_at) VALUES (?, ?, ?)",
                (feature_id, json.dumps(stats), now),
            )
            self.conn.commit()

    # --- Stats ---

    def get_catalog_stats(self) -> dict:
        sources = len(self.list_sources())
        features = len(self.list_features())
        doc_stats = self.get_doc_stats()
        return {
            "sources": sources,
            "features": features,
            **doc_stats,
        }
