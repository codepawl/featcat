# Backup and restore

featcat ships portable, cross-backend catalog backups. A backup taken on SQLite restores cleanly into Postgres and vice versa — archives contain row data in JSONL, not raw `.sqlite` files or `pg_dump` SQL.

## Quick reference

```bash
# Create a backup (defaults to ./catalog-backup-<ts>.tar.gz)
featcat backup
featcat backup --output ~/snapshots/2026-05-14.tar.gz

# List backups in a directory
featcat backup list --dir ~/snapshots

# Restore
featcat restore --input ~/snapshots/2026-05-14.tar.gz
featcat restore --input ~/snapshots/2026-05-14.tar.gz --force --yes  # scripted
```

## What's included

Backup archives contain every catalog table **except** scheduler state:

- **Included**: `data_sources`, `features`, `feature_docs`, `feature_versions`, `feature_lineage`, `feature_groups`, `feature_group_members`, `feature_group_versions`, `monitoring_baselines`, `monitoring_checks`, `scan_logs`, `usage_log`, `action_items`, `notifications`.
- **Excluded**: `job_schedules`, `job_logs` (re-seeded by the server on first start) and `alembic_version` (captured in `metadata.json` instead).

## Archive layout

```
catalog-backup-20260514-100000.tar.gz
└── catalog-backup-20260514-100000/
    ├── metadata.json     Envelope: version, backend, featcat version, timestamps, stats
    ├── manifest.json     Per-table row counts + FK-respecting insertion order
    └── tables/
        ├── data_sources.jsonl
        ├── features.jsonl
        └── ...one JSONL file per backed-up table
```

Datetime values are serialized as ISO 8601 strings. Bytes columns are encoded as `{"_b64": "..."}` envelopes to keep the JSON valid.

## Cross-backend restores

Because the dump is ORM-based row data (not engine-specific SQL), backups taken on SQLite can be restored into Postgres and vice versa. The destination must already have featcat's schema initialised — run `featcat init` (SQLite) or `alembic upgrade head` (Postgres) before `featcat restore`.

## Restoring into a non-empty catalog

`featcat restore` refuses to overwrite a non-empty catalog by default. Pass `--force` (or confirm the interactive prompt) to replace existing data. The restore is transactional — if anything fails mid-insert, the destination is rolled back to its pre-restore state.

## Version compatibility

The metadata envelope includes a `version` field. featcat refuses to restore an archive whose version it doesn't recognise. Cross-version upgrades (running an older backup through `alembic upgrade head` before restoring) are not yet automated — track the roadmap for V2.

## Related

- **[Installation](../getting-started/installation.md)** — how to bootstrap a destination catalog
- **[Architecture › Data Layer](../architecture/data.md)** *(coming soon)* — schema reference
