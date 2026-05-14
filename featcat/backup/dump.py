"""Read every catalog table through SQLAlchemy and emit JSONL files.

Backend-agnostic: rows are read via raw ``SELECT *`` so sqlite and postgres
produce identical row shapes. Scheduler-owned tables (``job_schedules``,
``job_logs``) and the alembic version table are intentionally excluded —
they're environment state, not catalog data. The alembic version is
captured in ``metadata.json`` instead.
"""

from __future__ import annotations

import base64
import json
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from .. import __version__ as _featcat_version
from ..config import load_settings
from .metadata import BackupManifest, BackupMetadata

if TYPE_CHECKING:
    from pathlib import Path

    from ..catalog.local import LocalBackend

TABLE_ORDER: list[str] = [
    "data_sources",
    "features",
    "feature_docs",
    "feature_versions",
    "feature_lineage",
    "feature_groups",
    "feature_group_members",
    "feature_group_versions",
    "monitoring_baselines",
    "monitoring_checks",
    "scan_logs",
    "usage_log",
    "action_items",
    "notifications",
]


def dump_catalog(db: LocalBackend, out_dir: Path) -> tuple[BackupMetadata, BackupManifest]:
    """Write JSONL files for every table in ``TABLE_ORDER`` plus envelopes.

    ``out_dir`` must already exist; this writes into it. Returns the
    metadata and manifest objects so the CLI can render a summary.
    """
    tables_dir = out_dir / "tables"
    tables_dir.mkdir(parents=True, exist_ok=True)

    row_counts: dict[str, int] = {}
    for table_name in TABLE_ORDER:
        row_counts[table_name] = _dump_table(db, table_name, tables_dir / f"{table_name}.jsonl")

    settings = load_settings()
    stats = db.get_catalog_stats()
    metadata = BackupMetadata(
        featcat_version=_featcat_version,
        backend=db.backend,
        backend_version=_backend_version(db),
        alembic_version=_alembic_version(db) if db.backend == "postgres" else None,
        created_at=datetime.now(timezone.utc),
        stats={
            "sources": int(stats.get("sources", 0) or 0),
            "features": int(stats.get("features", 0) or 0),
            "groups": int(row_counts.get("feature_groups", 0)),
            "lineage_edges": int(row_counts.get("feature_lineage", 0)),
        },
        embedding_model=getattr(settings, "embedding_model", None),
    )
    (out_dir / "metadata.json").write_text(metadata.model_dump_json(indent=2), encoding="utf-8")

    manifest = BackupManifest(table_order=list(TABLE_ORDER), row_counts=row_counts)
    (out_dir / "manifest.json").write_text(manifest.model_dump_json(indent=2), encoding="utf-8")

    return metadata, manifest


def _dump_table(db: LocalBackend, table_name: str, path: Path) -> int:
    """Stream rows from ``table_name`` to ``path`` as JSONL. Returns row count."""
    count = 0
    with db.session() as s, path.open("w", encoding="utf-8") as fh:
        result = s.execute(text(f"SELECT * FROM {table_name}"))  # noqa: S608
        columns = list(result.keys())
        for row in result:
            payload = {col: _coerce_value(row[idx]) for idx, col in enumerate(columns)}
            fh.write(json.dumps(payload, ensure_ascii=False, default=str) + "\n")
            count += 1
    return count


def _coerce_value(v: Any) -> Any:
    """JSON-safe coercion. datetime → ISO 8601 string, bytes → base64 envelope."""
    if isinstance(v, datetime):
        return v.isoformat()
    if isinstance(v, bytes):
        return {"_b64": base64.b64encode(v).decode("ascii")}
    return v


def _backend_version(db: LocalBackend) -> str:
    with db.session() as s:
        if db.backend == "sqlite":
            row = s.execute(text("SELECT sqlite_version()")).first()
            return str(row[0]) if row else "unknown"
        row = s.execute(text("SELECT version()")).first()
        if not row:
            return "unknown"
        # postgres version() returns "PostgreSQL 16.13 on x86_64-..."; pull the
        # second whitespace-delimited token so the metadata stays compact.
        parts = str(row[0]).split()
        return parts[1] if len(parts) > 1 else parts[0]


def _alembic_version(db: LocalBackend) -> str | None:
    with db.session() as s:
        try:
            row = s.execute(text("SELECT version_num FROM alembic_version LIMIT 1")).first()
        except Exception:
            return None
    return str(row[0]) if row else None
