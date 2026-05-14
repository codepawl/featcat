"""Restore a catalog from a dump directory produced by ``dump_catalog``.

One transaction: truncate every target table in FK-reverse order, then
insert each table in FK order. Any failure rolls back — the destination
is left in its pre-restore state.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING, Any

from sqlalchemy import text

from .metadata import BACKUP_VERSION, BackupManifest, BackupMetadata

if TYPE_CHECKING:
    from pathlib import Path

    from sqlalchemy.orm import Session

    from ..catalog.local import LocalBackend


class RestoreError(Exception):
    """Restore failed — validation, schema mismatch, or insertion error."""


def restore_catalog(db: LocalBackend, dump_dir: Path, *, force: bool = False) -> dict[str, int]:
    """Restore ``db`` from a dump directory. Returns per-table insert counts.

    Raises ``RestoreError`` for missing files, invalid envelopes, schema
    version mismatch, non-empty destination without ``force``, or any
    insertion failure (rolled back).
    """
    meta_path = dump_dir / "metadata.json"
    manifest_path = dump_dir / "manifest.json"
    if not meta_path.exists() or not manifest_path.exists():
        raise RestoreError(f"Dump directory missing metadata.json or manifest.json: {dump_dir}")

    try:
        metadata = BackupMetadata.model_validate_json(meta_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RestoreError(f"Invalid metadata.json: {e}") from e
    try:
        manifest = BackupManifest.model_validate_json(manifest_path.read_text(encoding="utf-8"))
    except Exception as e:
        raise RestoreError(f"Invalid manifest.json: {e}") from e

    if metadata.version != BACKUP_VERSION:
        raise RestoreError(
            f"Backup version {metadata.version} is not supported by this featcat (expected {BACKUP_VERSION})"
        )

    if not force:
        existing = db.get_catalog_stats()
        if int(existing.get("sources", 0) or 0) > 0 or int(existing.get("features", 0) or 0) > 0:
            raise RestoreError("Destination catalog is not empty. Re-run with force=True to replace.")

    counts: dict[str, int] = {}
    tables_dir = dump_dir / "tables"

    with db.session() as s:
        try:
            # Truncate in reverse FK order so child rows go first.
            for table_name in reversed(manifest.table_order):
                s.execute(text(f"DELETE FROM {table_name}"))  # noqa: S608
            # Insert in FK order.
            for table_name in manifest.table_order:
                file_path = tables_dir / f"{table_name}.jsonl"
                counts[table_name] = _insert_table(s, table_name, file_path)
            s.commit()
        except Exception as e:
            s.rollback()
            raise RestoreError(f"Restore failed during insertion: {e}") from e

    return counts


def _insert_table(session: Session, table_name: str, file_path: Path) -> int:
    if not file_path.exists():
        return 0
    rows: list[dict[str, Any]] = []
    with file_path.open("r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped:
                continue
            payload = json.loads(stripped)
            for k, v in list(payload.items()):
                if isinstance(v, dict) and set(v.keys()) == {"_b64"}:
                    payload[k] = base64.b64decode(v["_b64"])
            rows.append(payload)
    if not rows:
        return 0
    columns = list(rows[0].keys())
    placeholders = ", ".join(f":{c}" for c in columns)
    column_list = ", ".join(columns)
    stmt = text(f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})")  # noqa: S608
    session.execute(stmt, rows)
    return len(rows)
