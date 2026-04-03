"""SQLite CRUD operations for the feature catalog."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone

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
"""


def _adapt_datetime(val: datetime) -> str:
    return val.isoformat()


def _convert_datetime(val: bytes) -> datetime:
    return datetime.fromisoformat(val.decode())


sqlite3.register_adapter(datetime, _adapt_datetime)
sqlite3.register_converter("TIMESTAMP", _convert_datetime)


class CatalogDB:
    """Thin wrapper around SQLite for catalog operations."""

    def __init__(self, db_path: str = DEFAULT_DB) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(
            db_path,
            detect_types=sqlite3.PARSE_DECLTYPES,
        )
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")

    def init_db(self) -> None:
        """Create all tables if they don't exist."""
        self.conn.executescript(SCHEMA_SQL)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # --- DataSource CRUD ---

    def add_source(self, source: DataSource) -> DataSource:
        """Insert a new data source."""
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
        """Look up a data source by its unique name."""
        row = self.conn.execute("SELECT * FROM data_sources WHERE name = ?", (name,)).fetchone()
        if row is None:
            return None
        return DataSource(**dict(row))

    def list_sources(self) -> list[DataSource]:
        """Return all registered data sources."""
        rows = self.conn.execute("SELECT * FROM data_sources ORDER BY created_at DESC").fetchall()
        return [DataSource(**dict(r)) for r in rows]

    # --- Feature CRUD ---

    def upsert_feature(self, feature: Feature) -> Feature:
        """Insert or update a feature (keyed on data_source_id + column_name)."""
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
        """Return features, optionally filtered by source name."""
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
        """Look up a feature by name. Returns the first match."""
        row = self.conn.execute("SELECT * FROM features WHERE name = ?", (name,)).fetchone()
        if row is None:
            return None
        return _row_to_feature(row)

    def update_feature_tags(self, feature_id: str, tags: list[str]) -> None:
        """Replace tags for a feature."""
        now = datetime.now(timezone.utc)
        self.conn.execute(
            "UPDATE features SET tags = ?, updated_at = ? WHERE id = ?",
            (json.dumps(tags), now, feature_id),
        )
        self.conn.commit()

    def search_features(self, query: str) -> list[Feature]:
        """Basic keyword search across name, description, tags, and column_name."""
        pattern = f"%{query}%"
        rows = self.conn.execute(
            """SELECT * FROM features
               WHERE name LIKE ? OR description LIKE ? OR tags LIKE ? OR column_name LIKE ?
               ORDER BY name""",
            (pattern, pattern, pattern, pattern),
        ).fetchall()
        return [_row_to_feature(r) for r in rows]


def _row_to_feature(row: sqlite3.Row) -> Feature:
    """Convert a sqlite3.Row to a Feature model, parsing JSON fields."""
    d = dict(row)
    d["tags"] = json.loads(d["tags"]) if isinstance(d["tags"], str) else d["tags"]
    d["stats"] = json.loads(d["stats"]) if isinstance(d["stats"], str) else d["stats"]
    return Feature(**d)
