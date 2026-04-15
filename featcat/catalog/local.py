"""Local SQLite backend for the feature catalog."""

from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime, timezone

from .backend import CatalogBackend
from .models import DataSource, Feature, FeatureGroup, _new_id

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

CREATE TABLE IF NOT EXISTS feature_groups (
    id TEXT PRIMARY KEY,
    name TEXT UNIQUE NOT NULL,
    description TEXT DEFAULT '',
    project TEXT DEFAULT '',
    owner TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL,
    updated_at TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS feature_group_members (
    group_id TEXT NOT NULL REFERENCES feature_groups(id) ON DELETE CASCADE,
    feature_id TEXT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    added_at TIMESTAMP NOT NULL,
    PRIMARY KEY (group_id, feature_id)
);

CREATE TABLE IF NOT EXISTS usage_log (
    id TEXT PRIMARY KEY,
    feature_id TEXT NOT NULL REFERENCES features(id),
    action TEXT NOT NULL,
    user TEXT DEFAULT '',
    context TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_usage_log_feature ON usage_log(feature_id);
CREATE INDEX IF NOT EXISTS idx_usage_log_created ON usage_log(created_at);

CREATE TABLE IF NOT EXISTS monitoring_checks (
    id TEXT PRIMARY KEY,
    feature_id TEXT NOT NULL REFERENCES features(id),
    feature_name TEXT NOT NULL,
    psi REAL,
    severity TEXT NOT NULL,
    checked_at TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_monitoring_checks_feature ON monitoring_checks(feature_name);
CREATE INDEX IF NOT EXISTS idx_monitoring_checks_date ON monitoring_checks(checked_at);

CREATE TABLE IF NOT EXISTS feature_lineage (
    id TEXT PRIMARY KEY,
    child_feature_id TEXT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    parent_feature_id TEXT NOT NULL REFERENCES features(id) ON DELETE CASCADE,
    transform TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL,
    UNIQUE(child_feature_id, parent_feature_id)
);

CREATE INDEX IF NOT EXISTS idx_lineage_child ON feature_lineage(child_feature_id);
CREATE INDEX IF NOT EXISTS idx_lineage_parent ON feature_lineage(parent_feature_id);
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
        # Feature definition columns
        with contextlib.suppress(sqlite3.OperationalError):
            self.conn.execute("ALTER TABLE features ADD COLUMN definition TEXT")
        with contextlib.suppress(sqlite3.OperationalError):
            self.conn.execute("ALTER TABLE features ADD COLUMN definition_type TEXT")
        with contextlib.suppress(sqlite3.OperationalError):
            self.conn.execute("ALTER TABLE features ADD COLUMN definition_updated_at TIMESTAMP")
        # Generation hints
        with contextlib.suppress(sqlite3.OperationalError):
            self.conn.execute("ALTER TABLE features ADD COLUMN generation_hints TEXT")
        # Doc generation audit columns
        with contextlib.suppress(sqlite3.OperationalError):
            self.conn.execute("ALTER TABLE feature_docs ADD COLUMN hints_used TEXT")
        with contextlib.suppress(sqlite3.OperationalError):
            self.conn.execute("ALTER TABLE feature_docs ADD COLUMN context_features TEXT")
        # Version tracking: change_type, previous/new value
        with contextlib.suppress(sqlite3.OperationalError):
            self.conn.execute("ALTER TABLE feature_versions ADD COLUMN change_type TEXT DEFAULT 'metadata'")
        with contextlib.suppress(sqlite3.OperationalError):
            self.conn.execute("ALTER TABLE feature_versions ADD COLUMN previous_value TEXT")
        with contextlib.suppress(sqlite3.OperationalError):
            self.conn.execute("ALTER TABLE feature_versions ADD COLUMN new_value TEXT")
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
            # Check if feature already exists to distinguish insert from update
            existing = self.conn.execute(
                "SELECT id FROM features WHERE data_source_id = ? AND column_name = ?",
                (feature.data_source_id, feature.column_name),
            ).fetchone()
            is_new = existing is None

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

        # Create initial version entry for new features
        if is_new:
            source_name = feature.name.split(".")[0] if "." in feature.name else ""
            self._snapshot_feature(
                feature.id,
                {"source": ("", source_name), "column": ("", feature.column_name), "dtype": ("", feature.dtype)},
                changed_by=feature.owner or "system",
                change_type="metadata",
            )
            # Overwrite auto-generated summary
            with self._lock:
                self.conn.execute(
                    "UPDATE feature_versions SET change_summary = ? "
                    "WHERE feature_id = ? AND version = 1",
                    ("Initial registration via scan", feature.id),
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

    def _snapshot_feature(
        self,
        feature_id: str,
        changes: dict[str, tuple],
        changed_by: str = "",
        change_type: str = "metadata",
    ) -> None:
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
            prev_val = {field: old for field, (old, _new) in changes.items()}
            new_val = {field: new for field, (_old, new) in changes.items()}
            now = datetime.now(timezone.utc)
            self.conn.execute(
                """INSERT INTO feature_versions
                   (id, feature_id, version, snapshot, change_summary, changed_by, created_at,
                    change_type, previous_value, new_value)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    _new_id(), feature_id, next_version, json.dumps(snapshot),
                    "; ".join(parts), changed_by, now,
                    change_type, json.dumps(prev_val, default=str),
                    json.dumps(new_val, default=str),
                ),
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
            # Determine change type from changed fields
            ct = "tags" if set(changes) == {"tags"} else "metadata"
            self._snapshot_feature(
                feature_id, changes,
                changed_by=kwargs.get("owner", current.get("owner", "")),
                change_type=ct,
            )
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

    @staticmethod
    def _parse_version_row(d: dict) -> dict:
        """Parse JSON fields in a feature_versions row."""
        d["snapshot"] = json.loads(d["snapshot"]) if isinstance(d.get("snapshot"), str) else d.get("snapshot", {})
        d["previous_value"] = (
            json.loads(d["previous_value"]) if isinstance(d.get("previous_value"), str) else d.get("previous_value")
        )
        d["new_value"] = (
            json.loads(d["new_value"]) if isinstance(d.get("new_value"), str) else d.get("new_value")
        )
        d.setdefault("change_type", "metadata")
        return d

    def list_feature_versions(self, feature_id: str) -> list[dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM feature_versions WHERE feature_id = ? ORDER BY version DESC",
                (feature_id,),
            ).fetchall()
            return [self._parse_version_row(dict(r)) for r in rows]

    def get_feature_version(self, feature_id: str, version: int) -> dict | None:
        with self._lock:
            row = self.conn.execute(
                "SELECT * FROM feature_versions WHERE feature_id = ? AND version = ?",
                (feature_id, version),
            ).fetchone()
            if row is None:
                return None
            return self._parse_version_row(dict(row))

    def get_recent_versions(self, limit: int = 20, days: int = 7) -> list[dict]:
        """Return recent version changes across all features for audit log."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT fv.*, f.name as feature_name
                   FROM feature_versions fv
                   JOIN features f ON fv.feature_id = f.id
                   WHERE fv.created_at >= datetime('now', ? || ' days')
                   ORDER BY fv.created_at DESC
                   LIMIT ?""",
                (f"-{days}", limit),
            ).fetchall()
            return [self._parse_version_row(dict(r)) for r in rows]

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

        # Capture previous doc for versioning
        old_doc = self.get_feature_doc(feature_id)
        old_short = old_doc.get("short_description", "") if old_doc else ""
        new_short = _str(doc.get("short_description", ""))

        with self._lock:
            now = datetime.now(timezone.utc)
            self.conn.execute("DELETE FROM feature_docs WHERE feature_id = ?", (feature_id,))
            ctx_json = json.dumps(context_features) if context_features else None
            self.conn.execute(
                """INSERT INTO feature_docs
                   (feature_id, short_description, long_description,
                    expected_range, potential_issues, generated_at, model_used,
                    hints_used, context_features)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    feature_id,
                    new_short,
                    _str(doc.get("long_description", "")),
                    _str(doc.get("expected_range", "")),
                    _str(doc.get("potential_issues", "")),
                    now,
                    model_used,
                    hints_used,
                    ctx_json,
                ),
            )
            self.conn.commit()

        # Create version entry
        from .usage import resolve_user

        changes = {"short_description": (old_short, new_short)}
        summary = "Updated short_description" if old_short else "Generated documentation"
        self._snapshot_feature(
            feature_id, changes, changed_by=resolve_user(), change_type="doc",
        )
        # Overwrite auto-generated summary with more descriptive one
        with self._lock:
            self.conn.execute(
                "UPDATE feature_versions SET change_summary = ? "
                "WHERE feature_id = ? AND version = (SELECT MAX(version) FROM feature_versions WHERE feature_id = ?)",
                (summary, feature_id, feature_id),
            )
            self.conn.commit()

    def list_undocumented_features(self) -> list[Feature]:
        with self._lock:
            rows = self.conn.execute(
                """SELECT f.* FROM features f
                   LEFT JOIN feature_docs fd ON f.id = fd.feature_id
                   WHERE fd.feature_id IS NULL
                     OR (fd.short_description IS NULL OR fd.short_description = '')
                     OR f.updated_at > fd.generated_at"""
            ).fetchall()
            return [_row_to_feature(r) for r in rows]

    def get_doc_stats(self) -> dict:
        with self._lock:
            total = self.conn.execute("SELECT COUNT(*) FROM features").fetchone()[0]
            documented = self.conn.execute(
                "SELECT COUNT(DISTINCT feature_id) FROM feature_docs WHERE short_description IS NOT NULL AND short_description != ''"
            ).fetchone()[0]
            with_hints = self.conn.execute(
                "SELECT COUNT(*) FROM features WHERE generation_hints IS NOT NULL AND generation_hints != ''"
            ).fetchone()[0]
            return {
                "total_features": total,
                "documented": documented,
                "documented_features": documented,
                "features_with_hints": with_hints,
                "undocumented": total - documented,
                "coverage": round(documented / total * 100, 1) if total > 0 else 0.0,
            }

    def get_all_feature_docs(self) -> dict[str, dict]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT * FROM feature_docs WHERE short_description IS NOT NULL AND short_description != ''"
            ).fetchall()
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

    # --- Source lookup by path ---

    def get_source_by_path(self, path: str) -> DataSource | None:
        """Look up a data source by its file path."""
        with self._lock:
            row = self.conn.execute("SELECT * FROM data_sources WHERE path = ?", (path,)).fetchone()
            if row is None:
                return None
            return DataSource(**dict(row))

    # --- Feature Groups ---

    def create_group(self, group: FeatureGroup) -> FeatureGroup:
        """Create a new feature group."""
        with self._lock:
            self.conn.execute(
                """INSERT INTO feature_groups (id, name, description, project, owner, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (group.id, group.name, group.description, group.project,
                 group.owner, group.created_at, group.updated_at),
            )
            self.conn.commit()
        return group

    def get_group_by_name(self, name: str) -> FeatureGroup | None:
        """Get a feature group by name."""
        with self._lock:
            row = self.conn.execute("SELECT * FROM feature_groups WHERE name = ?", (name,)).fetchone()
            if row is None:
                return None
            return FeatureGroup(**dict(row))

    def list_groups(self, project: str | None = None) -> list[FeatureGroup]:
        """List all feature groups, optionally filtered by project."""
        with self._lock:
            if project:
                rows = self.conn.execute(
                    "SELECT * FROM feature_groups WHERE project = ? ORDER BY name", (project,)
                ).fetchall()
            else:
                rows = self.conn.execute("SELECT * FROM feature_groups ORDER BY name").fetchall()
            return [FeatureGroup(**dict(r)) for r in rows]

    def update_group(self, group_id: str, **kwargs: object) -> None:
        """Update group fields (description, project, owner)."""
        allowed = {"description", "project", "owner"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            return
        with self._lock:
            sets = [f"{k} = ?" for k in updates]
            sets.append("updated_at = ?")
            vals = list(updates.values())
            vals.append(datetime.now(timezone.utc))
            vals.append(group_id)
            self.conn.execute(f"UPDATE feature_groups SET {', '.join(sets)} WHERE id = ?", vals)  # noqa: S608
            self.conn.commit()

    def delete_group(self, group_id: str) -> None:
        """Delete a feature group (CASCADE removes members)."""
        with self._lock:
            self.conn.execute("DELETE FROM feature_groups WHERE id = ?", (group_id,))
            self.conn.commit()

    def add_group_members(self, group_id: str, feature_ids: list[str]) -> int:
        """Add features to a group. Returns count of newly added members."""
        added = 0
        now = datetime.now(timezone.utc)
        with self._lock:
            for fid in feature_ids:
                try:
                    self.conn.execute(
                        "INSERT INTO feature_group_members (group_id, feature_id, added_at) VALUES (?, ?, ?)",
                        (group_id, fid, now),
                    )
                    added += 1
                except sqlite3.IntegrityError:
                    pass  # already a member
            self.conn.commit()
        return added

    def remove_group_member(self, group_id: str, feature_id: str) -> None:
        """Remove a feature from a group."""
        with self._lock:
            self.conn.execute(
                "DELETE FROM feature_group_members WHERE group_id = ? AND feature_id = ?",
                (group_id, feature_id),
            )
            self.conn.commit()

    def list_group_members(self, group_id: str) -> list[Feature]:
        """List all features in a group."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT f.* FROM features f
                   JOIN feature_group_members gm ON f.id = gm.feature_id
                   WHERE gm.group_id = ?
                   ORDER BY f.name""",
                (group_id,),
            ).fetchall()
            return [_row_to_feature(r) for r in rows]

    def count_group_members(self, group_id: str) -> int:
        """Count members in a group."""
        with self._lock:
            return self.conn.execute(
                "SELECT COUNT(*) FROM feature_group_members WHERE group_id = ?", (group_id,)
            ).fetchone()[0]

    # --- Feature Definitions ---

    def set_feature_definition(self, feature_id: str, definition: str, definition_type: str) -> None:
        """Set or update a feature's definition."""
        from .usage import resolve_user

        old_def = self.get_feature_definition(feature_id)
        with self._lock:
            now = datetime.now(timezone.utc)
            self.conn.execute(
                "UPDATE features SET definition = ?, definition_type = ?,"
                " definition_updated_at = ?, updated_at = ? WHERE id = ?",
                (definition, definition_type, now, now, feature_id),
            )
            self.conn.commit()
        old_val = old_def.get("definition") if old_def else None
        old_dtype = old_def.get("definition_type") if old_def else None
        self._snapshot_feature(
            feature_id,
            {"definition": (old_val, definition), "definition_type": (old_dtype, definition_type)},
            changed_by=resolve_user(),
            change_type="definition",
        )

    def get_feature_definition(self, feature_id: str) -> dict | None:
        """Get a feature's definition. Returns None if not set."""
        with self._lock:
            row = self.conn.execute(
                "SELECT definition, definition_type, definition_updated_at FROM features WHERE id = ?",
                (feature_id,),
            ).fetchone()
            if row is None or row["definition"] is None:
                return None
            return dict(row)

    def clear_feature_definition(self, feature_id: str) -> None:
        """Remove a feature's definition."""
        from .usage import resolve_user

        old_def = self.get_feature_definition(feature_id)
        with self._lock:
            now = datetime.now(timezone.utc)
            self.conn.execute(
                "UPDATE features SET definition = NULL, definition_type = NULL,"
                " definition_updated_at = NULL, updated_at = ? WHERE id = ?",
                (now, feature_id),
            )
            self.conn.commit()
        if old_def and old_def.get("definition"):
            self._snapshot_feature(
                feature_id,
                {"definition": (old_def["definition"], None)},
                changed_by=resolve_user(),
                change_type="definition",
            )

    # --- Usage Tracking ---

    def log_usage(self, feature_id: str, action: str, user: str = "", context: str = "") -> None:
        """Log a usage event for a feature."""
        with self._lock:
            now = datetime.now(timezone.utc)
            self.conn.execute(
                "INSERT INTO usage_log (id, feature_id, action, user, context, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                (_new_id(), feature_id, action, user, context, now),
            )
            self.conn.commit()

    def get_top_features(self, limit: int = 10, days: int = 30) -> list[dict]:
        """Get most-used features by action counts."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT f.name,
                       SUM(CASE WHEN ul.action = 'view' THEN 1 ELSE 0 END) as view_count,
                       SUM(CASE WHEN ul.action = 'query' THEN 1 ELSE 0 END) as query_count,
                       COUNT(*) as total_count,
                       MAX(ul.created_at) as last_seen,
                       f.created_at,
                       ds.name as source
                   FROM usage_log ul
                   JOIN features f ON ul.feature_id = f.id
                   JOIN data_sources ds ON f.data_source_id = ds.id
                   WHERE ul.created_at >= datetime('now', ? || ' days')
                   GROUP BY ul.feature_id
                   ORDER BY total_count DESC
                   LIMIT ?""",
                (f"-{days}", limit),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_orphaned_features(self, days: int = 30) -> list[dict]:
        """Get features with zero usage in the given period."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT f.name,
                       (SELECT MAX(ul2.created_at) FROM usage_log ul2 WHERE ul2.feature_id = f.id) as last_seen
                   FROM features f
                   LEFT JOIN usage_log ul ON f.id = ul.feature_id
                       AND ul.created_at >= datetime('now', ? || ' days')
                   WHERE ul.id IS NULL
                   ORDER BY f.name""",
                (f"-{days}",),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_usage_activity(self, days: int = 7) -> list[dict]:
        """Get per-day usage activity summary."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT DATE(created_at) as date,
                       SUM(CASE WHEN action = 'view' THEN 1 ELSE 0 END) as view_count,
                       SUM(CASE WHEN action = 'query' THEN 1 ELSE 0 END) as query_count,
                       COUNT(DISTINCT feature_id) as unique_features,
                       COUNT(*) as total
                   FROM usage_log
                   WHERE created_at >= datetime('now', ? || ' days')
                   GROUP BY DATE(created_at)
                   ORDER BY date DESC""",
                (f"-{days}",),
            ).fetchall()
            return [dict(r) for r in rows]

    def get_feature_usage(self, feature_id: str, days: int = 30) -> dict:
        """Get usage summary for a single feature."""
        with self._lock:
            row = self.conn.execute(
                """SELECT
                       SUM(CASE WHEN action = 'view' THEN 1 ELSE 0 END) as views,
                       SUM(CASE WHEN action = 'query' THEN 1 ELSE 0 END) as queries,
                       COUNT(*) as total,
                       MAX(created_at) as last_seen
                   FROM usage_log
                   WHERE feature_id = ? AND created_at >= datetime('now', ? || ' days')""",
                (feature_id, f"-{days}"),
            ).fetchone()
            daily = self.conn.execute(
                """SELECT DATE(created_at) as date, COUNT(*) as count
                   FROM usage_log
                   WHERE feature_id = ? AND created_at >= datetime('now', '-7 days')
                   GROUP BY DATE(created_at)
                   ORDER BY date""",
                (feature_id,),
            ).fetchall()
            return {
                "views": row["views"] or 0,
                "queries": row["queries"] or 0,
                "total": row["total"] or 0,
                "last_seen": row["last_seen"],
                "daily": [dict(d) for d in daily],
            }

    # --- Generation Hints ---

    def set_feature_hint(self, feature_id: str, hint: str) -> None:
        """Set generation hints for a feature."""
        from .usage import resolve_user

        old_hint = self.get_feature_hint(feature_id)
        with self._lock:
            now = datetime.now(timezone.utc)
            self.conn.execute(
                "UPDATE features SET generation_hints = ?, updated_at = ? WHERE id = ?",
                (hint, now, feature_id),
            )
            self.conn.commit()
        self._snapshot_feature(
            feature_id,
            {"generation_hints": (old_hint, hint)},
            changed_by=resolve_user(),
            change_type="hints",
        )

    def get_feature_hint(self, feature_id: str) -> str | None:
        """Get generation hints for a feature."""
        with self._lock:
            row = self.conn.execute(
                "SELECT generation_hints FROM features WHERE id = ?",
                (feature_id,),
            ).fetchone()
            if row is None:
                return None
            return row["generation_hints"]

    def clear_feature_hint(self, feature_id: str) -> None:
        """Remove generation hints for a feature."""
        from .usage import resolve_user

        old_hint = self.get_feature_hint(feature_id)
        with self._lock:
            now = datetime.now(timezone.utc)
            self.conn.execute(
                "UPDATE features SET generation_hints = NULL, updated_at = ? WHERE id = ?",
                (now, feature_id),
            )
            self.conn.commit()
        if old_hint:
            self._snapshot_feature(
                feature_id,
                {"generation_hints": (old_hint, None)},
                changed_by=resolve_user(),
                change_type="hints",
            )

    # --- Visualization Queries ---

    def get_doc_debt(self) -> list[dict]:
        """Return doc debt grouped by owner and data source."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT
                       COALESCE(NULLIF(f.owner, ''), 'unassigned') as owner,
                       ds.name as source,
                       COUNT(*) as total,
                       COUNT(*) - COUNT(CASE WHEN fd.short_description IS NOT NULL AND fd.short_description != '' THEN fd.feature_id END) as undocumented
                   FROM features f
                   JOIN data_sources ds ON f.data_source_id = ds.id
                   LEFT JOIN feature_docs fd ON f.id = fd.feature_id
                   GROUP BY f.owner, ds.name
                   ORDER BY undocumented DESC"""
            ).fetchall()
            result = []
            for r in rows:
                d = dict(r)
                d["pct_undocumented"] = round(d["undocumented"] / d["total"] * 100, 1) if d["total"] > 0 else 0.0
                result.append(d)
            return result

    def get_monitoring_history(self, feature_name: str, days: int = 30) -> list[dict]:
        """Return PSI check history for a feature."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT checked_at, psi, severity
                   FROM monitoring_checks
                   WHERE feature_name = ?
                     AND checked_at >= datetime('now', ? || ' days')
                   ORDER BY checked_at ASC""",
                (feature_name, f"-{days}"),
            ).fetchall()
            return [dict(r) for r in rows]

    def save_monitoring_result(self, feature_id: str, feature_name: str, psi: float | None, severity: str) -> None:
        """Save a monitoring check result for history tracking."""
        with self._lock:
            now = datetime.now(timezone.utc)
            self.conn.execute(
                """INSERT INTO monitoring_checks (id, feature_id, feature_name, psi, severity, checked_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (_new_id(), feature_id, feature_name, psi, severity, now),
            )
            self.conn.commit()

    def get_baseline_for_feature(self, feature_name: str) -> dict | None:
        """Retrieve baseline stats for a feature by name, including metadata."""
        with self._lock:
            row = self.conn.execute(
                """SELECT mb.baseline_stats, mb.computed_at, f.name as feature_spec
                   FROM monitoring_baselines mb
                   JOIN features f ON mb.feature_id = f.id
                   WHERE f.name = ?""",
                (feature_name,),
            ).fetchone()
            if row is None:
                return None
            stats = row["baseline_stats"]
            return {
                "feature_spec": row["feature_spec"],
                "baseline_stats": json.loads(stats) if isinstance(stats, str) else stats,
                "computed_at": row["computed_at"].isoformat() if row["computed_at"] else None,
            }

    def get_stats_by_source(self) -> list[dict]:
        """Return per-source stats for dashboard visualization."""
        with self._lock:
            rows = self.conn.execute(
                """SELECT
                       ds.name as source_name,
                       ds.path,
                       COUNT(DISTINCT f.id) as feature_count,
                       COUNT(DISTINCT CASE WHEN fd.short_description IS NOT NULL AND fd.short_description != '' THEN f.id END) as documented_count,
                       ds.updated_at as last_scanned
                   FROM data_sources ds
                   LEFT JOIN features f ON f.data_source_id = ds.id
                   LEFT JOIN feature_docs fd ON f.id = fd.feature_id
                   GROUP BY ds.id, ds.name, ds.path, ds.updated_at
                   ORDER BY ds.name"""
            ).fetchall()

            # Get latest monitoring check per feature for alert counts
            latest_checks = self.conn.execute(
                """SELECT mc.feature_name, mc.severity, mc.psi
                   FROM monitoring_checks mc
                   INNER JOIN (
                       SELECT feature_name, MAX(checked_at) as max_checked
                       FROM monitoring_checks
                       GROUP BY feature_name
                   ) latest ON mc.feature_name = latest.feature_name
                       AND mc.checked_at = latest.max_checked"""
            ).fetchall()

            # Index checks by source (feature_name format is "source.column")
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
                result.append({
                    "source_name": src,
                    "path": r["path"],
                    "feature_count": r["feature_count"],
                    "documented_count": r["documented_count"],
                    "drift_alerts": len(drift),
                    "critical_alerts": len(critical),
                    "last_scanned": ls.isoformat() if hasattr(ls, "isoformat") else ls,
                    "top_drifting_feature": top_drift["feature_name"] if top_drift and (top_drift["psi"] or 0) > 0.1 else None,
                })
            return result

    # --- Lineage ---

    def add_lineage(self, child_feature_id: str, parent_feature_id: str, transform: str = "") -> None:
        with self._lock:
            now = datetime.now(timezone.utc)
            self.conn.execute(
                """INSERT OR IGNORE INTO feature_lineage (id, child_feature_id, parent_feature_id, transform, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (_new_id(), child_feature_id, parent_feature_id, transform, now),
            )
            self.conn.commit()

    def remove_lineage(self, child_feature_id: str, parent_feature_id: str) -> None:
        with self._lock:
            self.conn.execute(
                "DELETE FROM feature_lineage WHERE child_feature_id = ? AND parent_feature_id = ?",
                (child_feature_id, parent_feature_id),
            )
            self.conn.commit()

    def get_lineage_graph(self) -> dict:
        """Return full lineage graph as {nodes, edges}."""
        with self._lock:
            edges_rows = self.conn.execute(
                """SELECT fl.child_feature_id, fl.parent_feature_id, fl.transform, fl.created_at,
                          fc.name as child_name, fp.name as parent_name
                   FROM feature_lineage fl
                   JOIN features fc ON fl.child_feature_id = fc.id
                   JOIN features fp ON fl.parent_feature_id = fp.id"""
            ).fetchall()

            if not edges_rows:
                return {"nodes": [], "edges": []}

            # Collect unique feature IDs involved in lineage
            feature_ids: set[str] = set()
            edges = []
            for r in edges_rows:
                feature_ids.add(r["child_feature_id"])
                feature_ids.add(r["parent_feature_id"])
                ca = r["created_at"]
                edges.append({
                    "source": r["parent_name"],
                    "target": r["child_name"],
                    "transform": r["transform"] or "",
                    "created_at": ca.isoformat() if hasattr(ca, "isoformat") else ca,
                })

            # Fetch feature details and doc/drift status
            placeholders = ",".join("?" for _ in feature_ids)
            feat_rows = self.conn.execute(
                f"SELECT * FROM features WHERE id IN ({placeholders})",  # noqa: S608
                list(feature_ids),
            ).fetchall()

            doc_ids = {
                r["feature_id"]
                for r in self.conn.execute(
                    f"SELECT feature_id FROM feature_docs WHERE feature_id IN ({placeholders}) AND short_description IS NOT NULL AND short_description != ''",  # noqa: S608
                    list(feature_ids),
                ).fetchall()
            }

            # Latest drift severity per feature
            drift_map: dict[str, str] = {}
            for fid in feature_ids:
                row = self.conn.execute(
                    "SELECT severity FROM monitoring_checks WHERE feature_id = ? ORDER BY checked_at DESC LIMIT 1",
                    (fid,),
                ).fetchone()
                if row:
                    drift_map[fid] = row["severity"]

            nodes = []
            for r in feat_rows:
                f = _row_to_feature(r)
                src = f.name.split(".")[0] if "." in f.name else ""
                nodes.append({
                    "id": f.name,
                    "spec": f.name,
                    "source": src,
                    "dtype": f.dtype,
                    "has_doc": f.id in doc_ids,
                    "drift_status": drift_map.get(f.id, "healthy"),
                })

            return {"nodes": nodes, "edges": edges}

    def get_feature_lineage(self, feature_name: str, direction: str = "both", depth: int = 3) -> dict:
        """Return lineage tree for a single feature."""
        feature = self.get_feature_by_name(feature_name)
        if feature is None:
            return {"feature": None, "parents": [], "children": []}

        root = {"spec": feature.name, "dtype": feature.dtype, "source": feature.name.split(".")[0] if "." in feature.name else ""}

        def _get_parents(fid: str, d: int) -> list[dict]:
            if d <= 0:
                return []
            with self._lock:
                rows = self.conn.execute(
                    """SELECT fp.id, fp.name, fp.dtype, fl.transform
                       FROM feature_lineage fl
                       JOIN features fp ON fl.parent_feature_id = fp.id
                       WHERE fl.child_feature_id = ?""",
                    (fid,),
                ).fetchall()
            result = []
            for r in rows:
                result.append({
                    "spec": r["name"],
                    "transform": r["transform"] or "",
                    "dtype": r["dtype"],
                    "parents": _get_parents(r["id"], d - 1),
                })
            return result

        def _get_children(fid: str, d: int) -> list[dict]:
            if d <= 0:
                return []
            with self._lock:
                rows = self.conn.execute(
                    """SELECT fc.id, fc.name, fc.dtype, fl.transform
                       FROM feature_lineage fl
                       JOIN features fc ON fl.child_feature_id = fc.id
                       WHERE fl.parent_feature_id = ?""",
                    (fid,),
                ).fetchall()
            result = []
            for r in rows:
                result.append({
                    "spec": r["name"],
                    "transform": r["transform"] or "",
                    "dtype": r["dtype"],
                    "children": _get_children(r["id"], d - 1),
                })
            return result

        parents = _get_parents(feature.id, depth) if direction in ("both", "up") else []
        children = _get_children(feature.id, depth) if direction in ("both", "down") else []

        return {"feature": root, "parents": parents, "children": children}
