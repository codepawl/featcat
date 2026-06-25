# Bulk operations

Three API operations support batch mode out of the box: tagging, group membership, and deletion. All three share the same shape: pass a list of feature IDs plus the operation, get back the requested and changed counts.

## When to use it

- **Onboarding a new source** — bulk-tag the freshly scanned features with `team=data-platform` so they show up in the right filter.
- **Closing out a project** — deprecate every feature with `tag=ml-experiment-q3-2025` in one move.
- **Group rebalancing** — pull a dozen features into a new group at once.
- **Cleanup** — when a source migrates, delete the obsolete feature rows in bulk so the catalog reflects reality.

## Bulk tagging

```bash
curl -X POST http://localhost:8000/api/features/bulk/tags \
    -H 'Content-Type: application/json' \
    -d '{
          "feature_ids": ["feature-id-1", "feature-id-2"],
          "action": "add",
          "tags": ["team=data-platform", "domain=churn"]
        }'
```

`action` is `add`, `remove`, or `replace`. Tags are stored as a JSONB column on PostgreSQL, JSON text on SQLite. They're free-form strings — convention is `key=value` but `churn` works fine too.

```json
{"updated": 2, "requested": 2}
```

## Bulk group membership

Add many features to a group:

```bash
curl -X POST http://localhost:8000/api/features/bulk/groups \
    -H 'Content-Type: application/json' \
    -d '{
          "group_id": "group-id",
          "feature_ids": ["feature-id-1", "feature-id-2"],
          "action": "add_to"
        }'
```

`action` is `add_to` or `remove_from`. The web UI's [shared FeatureSelector](catalog.md) calls this endpoint when you click **Add to group** in the catalog with multiple rows selected.

CLI:

```bash
featcat group add churn_v2 \
    user_behavior.session_count_30d \
    user_behavior.event_count_30d
```

## Bulk deletion

Deletion cascades children explicitly (`feature_docs`, `monitoring_baselines`, `monitoring_checks`, `usage_log`) before the feature itself, since FKs aren't `ON DELETE CASCADE` to keep the SQLite path simple.

```bash
curl -X POST http://localhost:8000/api/features/bulk/delete \
    -H 'Content-Type: application/json' \
    -d '{
          "feature_ids": ["feature-id-1", "feature-id-2"],
          "confirm": true
        }'
```

Bulk delete requires `confirm: true`; there is no CLI wrapper or dry-run endpoint today. Take a database backup before destructive bulk deletes.

## Bulk scan

Scanning many sources at once:

```bash
featcat scan-bulk /sources --recursive
featcat scan-bulk s3://bucket/features/ --recursive --dry-run
```

Useful for first-time onboarding a directory or S3 prefix of Parquet files.

## Dry-run discipline

Tagging and group membership are reversible with one more API call. Deletion is **not**. Recommended pattern for any deletion:

Use `featcat export --format json --output backup/catalog-before-delete.json` or a database-level backup before calling the delete endpoint.

The web UI's bulk actions menu always has a confirmation dialog for deletes, listing exact counts before you click through.

## Performance

- Bulk endpoints batch SQL operations: a single `UPDATE features SET tags = … WHERE name IN (…)` instead of N queries. 1k-feature operations finish in <500ms on PostgreSQL, ~2s on SQLite.
- Deletion is the slowest because it has to fan out to four child tables. Plan for ~5s per 1k features on SQLite.

## Limitations / future work

- **No CLI wrappers for feature bulk endpoints yet** — call the API directly or use the web UI.
- **No bulk doc-regenerate in this endpoint group** — batch docs run through `/api/docs/generate-batch`; see [Documentation](docs.md#generating-docs).
- **No bulk owner / status change yet** — slated for a future bulk update PR. For now, loop the single-feature endpoints.
- **No undo log.** Deletion is permanent. Take a SQLite snapshot or PostgreSQL pg_dump before destructive bulk runs in production.

## Related

- **[Catalog browser](catalog.md)** — selecting features in the UI uses the bulk endpoints
- **[Feature groups](groups.md)** — group membership is one of the bulk operations
- **[Documentation](docs.md)** — bulk doc generation has its own page
