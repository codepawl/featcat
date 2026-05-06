# Bulk operations

Three operations support batch mode out of the box: tagging, group membership, and deletion. All three share the same shape: pass a list of feature names + the operation, get back per-feature success/failure.

## When to use it

- **Onboarding a new source** — bulk-tag the freshly scanned features with `team=data-platform` so they show up in the right filter.
- **Closing out a project** — deprecate every feature with `tag=ml-experiment-q3-2025` in one move.
- **Group rebalancing** — pull a dozen features into a new group at once.
- **Cleanup** — when a source migrates, delete the obsolete feature rows in bulk so the catalog reflects reality.

## Bulk tagging

```bash
featcat features tag-bulk \
    --names user_behavior.session_count_30d \
    --names user_behavior.event_count_30d \
    --names device_performance.crash_count_7d \
    --add team=data-platform \
    --add domain=churn
```

Or by filter:

```bash
featcat features tag-bulk --source user_behavior --add team=data-platform
```

`--add` adds tags; `--remove` strips them; both can repeat. Tags are stored as a JSONB column on PostgreSQL, JSON text on SQLite. They're free-form strings — convention is `key=value` but `churn` works fine too.

API:

```bash
curl -X POST http://localhost:8000/api/bulk/tags \
    -H 'Content-Type: application/json' \
    -d '{
          "feature_names": ["user_behavior.session_count_30d", ...],
          "add": ["team=data-platform", "domain=churn"],
          "remove": ["team=legacy"]
        }'
```

Response:

```json
{
  "succeeded": ["user_behavior.session_count_30d", ...],
  "failed": [{"name": "missing.feature", "error": "not found"}]
}
```

## Bulk group membership

Add many features to a group:

```bash
curl -X POST http://localhost:8000/api/bulk/groups \
    -H 'Content-Type: application/json' \
    -d '{
          "group_name": "churn_v2",
          "feature_names": ["user_behavior.session_count_30d", ...],
          "operation": "add"
        }'
```

`operation` is `add` or `remove`. The web UI's [shared FeatureSelector](catalog.md) calls this endpoint when you click **Add to group** in the catalog with multiple rows selected.

CLI:

```bash
featcat groups add-members churn_v2 \
    user_behavior.session_count_30d \
    user_behavior.event_count_30d
```

## Bulk deletion

Deletion cascades children explicitly (`feature_docs`, `monitoring_baselines`, `monitoring_checks`, `usage_log`) before the feature itself, since FKs aren't `ON DELETE CASCADE` to keep the SQLite path simple.

```bash
curl -X POST http://localhost:8000/api/bulk/delete \
    -H 'Content-Type: application/json' \
    -d '{
          "feature_names": [...],
          "dry_run": true
        }'
```

`dry_run: true` returns what *would* be deleted (with row counts per child table) without committing. **Always run with `dry_run: true` first** for irreversible operations.

CLI:

```bash
featcat features delete-bulk --source legacy_pipeline --dry-run
# Would delete 47 features:
#   - legacy_pipeline.col_a (3 baselines, 12 monitoring_checks, 0 usage_log)
#   - ...

featcat features delete-bulk --source legacy_pipeline --confirm
```

## Bulk scan

Scanning many sources at once:

```bash
featcat scan-bulk --pattern "/sources/user_*"      # glob over filesystem
featcat scan-bulk --from-yaml sources.yaml         # batch declarative config
```

`sources.yaml`:

```yaml
sources:
  - name: user_behavior
    path: /sources/user_behavior_30d.parquet
    description: 30-day user behavior fixture
  - name: device_performance
    path: /sources/device_performance.parquet
```

Useful for first-time onboarding or for keeping a YAML manifest under git as the source of truth for which feeds the catalog watches.

## Dry-run discipline

Tagging and group membership are reversible with one more API call. Deletion is **not**. Recommended pattern for any deletion:

```bash
# 1. dry-run to see scope
featcat features delete-bulk --source legacy --dry-run > /tmp/preview.json

# 2. eyeball the output
jq '.would_delete | length' /tmp/preview.json

# 3. confirm
featcat features delete-bulk --source legacy --confirm
```

The web UI's bulk actions menu always has a confirmation dialog for deletes, listing exact counts before you click through.

## Performance

- Bulk endpoints batch SQL operations: a single `UPDATE features SET tags = … WHERE name IN (…)` instead of N queries. 1k-feature operations finish in <500ms on PostgreSQL, ~2s on SQLite.
- Deletion is the slowest because it has to fan out to four child tables. Plan for ~5s per 1k features on SQLite.

## Limitations / future work

- **No bulk doc-regenerate yet** — that runs through the Celery batch path; see [Documentation](docs.md#generating-docs).
- **No bulk owner / status change yet** — slated for the next bulk update PR. For now, loop the single-feature endpoints.
- **No undo log.** Deletion is permanent. Take a SQLite snapshot or PostgreSQL pg_dump before destructive bulk runs in production.

## Related

- **[Catalog browser](catalog.md)** — selecting features in the UI uses the bulk endpoints
- **[Feature groups](groups.md)** — group membership is one of the bulk operations
- **[Documentation](docs.md)** — bulk doc generation has its own page
