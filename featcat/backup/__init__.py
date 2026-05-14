"""Catalog backup and restore.

Backup archives are tar.gz with this layout::

    catalog-backup-YYYYMMDD-HHMMSS.tar.gz
    └── catalog-backup-YYYYMMDD-HHMMSS/
        ├── metadata.json     Envelope: version, backend, featcat version, timestamps
        ├── manifest.json     Per-table row counts + FK-respecting insertion order
        └── tables/
            ├── data_sources.jsonl
            ├── features.jsonl
            └── ...one JSONL file per backed-up table

The format is intentionally backend-agnostic (ORM-based row dump in JSONL)
so a sqlite backup restores cleanly into postgres and vice versa.
"""

from __future__ import annotations

from .archive import ArchiveError, pack_archive, unpack_archive
from .dump import TABLE_ORDER, dump_catalog
from .metadata import BACKUP_VERSION, BackupManifest, BackupMetadata
from .restore import RestoreError, restore_catalog

__all__ = [
    "BACKUP_VERSION",
    "ArchiveError",
    "BackupManifest",
    "BackupMetadata",
    "RestoreError",
    "TABLE_ORDER",
    "dump_catalog",
    "pack_archive",
    "restore_catalog",
    "unpack_archive",
]
