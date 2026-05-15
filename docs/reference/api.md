# HTTP API Reference

Every HTTP endpoint shipped by the featcat FastAPI server, derived from the
live router source. Endpoints are grouped by router (resource).

## Source of truth

- Audit SHA: `84041cd7264d705c82f5a150618d2e4b37e2c547`
- App factory: `featcat/server/app.py` (`build_app()`)
- Router mount table: `featcat/server/app.py:132-150`
- Router files: `featcat/server/routes/*.py`

All routers below are mounted in `build_app()`. Endpoint paths shown include
their mount prefix. Unless flagged **SSE** or **download**, every endpoint
returns JSON.

## App-level routes

Registered directly on the FastAPI app outside any router.

| Method | Path                    | Description                                   | Returns | Source |
|--------|-------------------------|-----------------------------------------------|---------|--------|
| GET    | `/`                     | Serve SPA root (`index.html`).                | HTML    | `featcat/server/app.py:160` (`serve_root`) |
| GET    | `/{full_path:path}`     | SPA catch-all — falls back to `index.html` for React Router client routes. | HTML    | `featcat/server/app.py:167` (`serve_spa`) |
| GET    | `/assets/*`             | Vite-built static assets (`StaticFiles` mount). | files | `featcat/server/app.py:157` |

Middleware: optional bearer token (when `server_auth_token` is set) protects
every route except `/api/health`; CORS allows all origins.

## Health & catalog stats

Router prefix: `/api`. Source: `featcat/server/routes/health.py`.

| Method | Path                       | Description                                                                 | Source |
|--------|----------------------------|-----------------------------------------------------------------------------|--------|
| GET    | `/api/health`              | Health check: DB and LLM reachability with structured diagnostics.          | `health.py:13` (`health`) |
| GET    | `/api/stats`               | Catalog overview counters (cached 600s).                                    | `health.py:51` (`stats`) |
| GET    | `/api/stats/doc-debt`      | Doc coverage debt grouped by owner and source (cached 600s).                | `health.py:63` (`doc_debt`) |
| GET    | `/api/stats/by-source`     | Per-source stats for the dashboard donut chart (cached 600s).               | `health.py:74` (`stats_by_source`) |

## Sources

Router prefix: `/api/sources`. Source: `featcat/server/routes/sources.py`.

| Method | Path                                | Description                                                          | Source |
|--------|-------------------------------------|----------------------------------------------------------------------|--------|
| POST   | `/api/sources`                      | Register a new data source.                                          | `sources.py:67` (`add_source`) |
| GET    | `/api/sources`                      | List registered sources (in-process cache 600s).                     | `sources.py:91` (`list_sources`) |
| GET    | `/api/sources/{name}`               | Fetch a single source.                                               | `sources.py:103` (`get_source`) |
| PATCH  | `/api/sources/{name}`               | Update mutable fields (description, format).                         | `sources.py:112` (`update_source`) |
| GET    | `/api/sources/{name}/impact`        | Pre-delete impact summary (feature + group counts).                  | `sources.py:124` (`source_impact`) |
| GET    | `/api/sources/{name}/scan-logs`     | Recent scan attempts for a source.                                   | `sources.py:134` (`list_source_scan_logs`) |
| POST   | `/api/sources/{name}/scan`          | Scan a source and register its columns as features.                  | `sources.py:143` (`scan`) |
| DELETE | `/api/sources/{name}`               | Hard-delete a source and cascade its features.                       | `sources.py:222` (`delete_source`) |

## Features

Router prefix: `/api/features`. Source: `featcat/server/routes/features.py`.

Feature lookups by name use query parameters (e.g. `/features/by-name?name=foo.bar`)
because feature names contain dots, which FastAPI's path parser treats as
file extensions.

| Method | Path                                                   | Description                                                                 | Source |
|--------|--------------------------------------------------------|-----------------------------------------------------------------------------|--------|
| GET    | `/api/features`                                        | List features with filters, sorting, TF-IDF search, pagination.             | `features.py:100` (`list_features`) |
| GET    | `/api/features/health-summary`                         | Aggregated health stats for the catalog.                                    | `features.py:256` (`health_summary`) |
| GET    | `/api/features/stats/status-counts`                    | Per-status counts (draft/reviewed/certified/deprecated).                    | `features.py:332` (`status_counts`) |
| GET    | `/api/features/by-name/versions`                       | List versions of a feature.                                                 | `features.py:348` (`list_versions`) |
| GET    | `/api/features/by-name/versions/{version}`             | Get a specific version of a feature.                                        | `features.py:356` (`get_version`) |
| POST   | `/api/features/by-name/rollback`                       | Rollback a feature to a prior version.                                      | `features.py:367` (`rollback_feature_endpoint`) |
| GET    | `/api/features/by-name/certification-readiness`        | Check whether a feature meets the certification checklist.                  | `features.py:379` (`get_certification_readiness`) |
| POST   | `/api/features/by-name/status`                         | Transition a feature's lifecycle status.                                    | `features.py:400` (`set_status_by_name`) |
| GET    | `/api/features/by-name/similar`                        | Top-k features most similar to the given one.                               | `features.py:427` (`get_similar_by_name`) |
| GET    | `/api/features/by-name`                                | Get a feature by name.                                                      | `features.py:446` (`get_feature_by_name`) |
| PATCH  | `/api/features/by-name`                                | Update mutable feature metadata (tags, owner, description).                 | `features.py:460` (`update_feature_by_name`) |
| DELETE | `/api/features/by-name`                                | Delete a feature.                                                           | `features.py:472` (`delete_feature_by_name`) |
| GET    | `/api/features/by-name/definition`                     | Get a feature's definition.                                                 | `features.py:489` (`get_definition`) |
| PUT    | `/api/features/by-name/definition`                     | Set / update a feature's definition.                                        | `features.py:501` (`set_definition`) |
| DELETE | `/api/features/by-name/definition`                     | Remove a feature's definition.                                              | `features.py:511` (`delete_definition`) |
| GET    | `/api/features/by-name/hints`                          | Get generation hints used by the autodoc plugin.                            | `features.py:528` (`get_hints`) |
| PATCH  | `/api/features/by-name/hints`                          | Set generation hints.                                                       | `features.py:538` (`set_hints`) |
| DELETE | `/api/features/by-name/hints`                          | Clear generation hints.                                                     | `features.py:548` (`delete_hints`) |
| GET    | `/api/features/similarity-graph`                       | Catalog-wide similarity graph (TF-IDF cosine).                              | `features.py:561` (`similarity_graph`) |
| GET    | `/api/features/duplicates`                             | Ranked duplicate-feature pairs.                                             | `features.py:686` (`get_duplicates`) |
| GET    | `/api/features/similarity-matrix`                      | Upper-triangle similarity matrix for caller-selected features.              | `features.py:752` (`get_similarity_matrix`) |
| GET    | `/api/features/similarity-pair`                        | Score a single pair with per-reason breakdown.                              | `features.py:791` (`get_similarity_pair`) |
| POST   | `/api/features/recommend`                              | Rank features for a natural-language use case (LLM or TF-IDF).              | `features.py:932` (`recommend_features`) |

## Feature bulk operations

Router prefix: `/api/features/bulk`. Source: `featcat/server/routes/bulk.py`.

| Method | Path                          | Description                                                       | Source |
|--------|-------------------------------|-------------------------------------------------------------------|--------|
| POST   | `/api/features/bulk/tags`     | Add/remove/replace tags on N features (all-or-nothing).           | `bulk.py:52` (`bulk_tags`) |
| POST   | `/api/features/bulk/groups`   | Add to or remove from group across N features (all-or-nothing).   | `bulk.py:67` (`bulk_groups`) |
| POST   | `/api/features/bulk/delete`   | Bulk hard-delete features (requires confirm flag).                | `bulk.py:81` (`bulk_delete`) |

## Documentation

Router prefix: `/api/docs`. Source: `featcat/server/routes/docs.py`.

| Method | Path                                       | Description                                                       | Source |
|--------|--------------------------------------------|-------------------------------------------------------------------|--------|
| GET    | `/api/docs/glossary`                       | Canonical glossary of scores, severities, metric definitions.     | `docs.py:22` (`glossary`) |
| POST   | `/api/docs/generate`                       | Generate AI documentation for one or more features.               | `docs.py:40` (`generate_docs`) |
| POST   | `/api/docs/generate-batch`                 | Start batch doc generation as a background task; returns job id.  | `docs.py:72` (`generate_batch`) |
| GET    | `/api/docs/generate-batch/{job_id}/status` | Poll batch generation progress.                                   | `docs.py:108` (`batch_status`) |
| GET    | `/api/docs/stats`                          | Doc coverage statistics.                                          | `docs.py:169` (`doc_stats`) |
| GET    | `/api/docs/by-name`                        | Get documentation for a feature (query param for dotted names).   | `docs.py:175` (`get_doc_by_name`) |

## Monitoring

Router prefix: `/api/monitor`. Source: `featcat/server/routes/monitor.py`.

| Method | Path                                       | Description                                                  | Source |
|--------|--------------------------------------------|--------------------------------------------------------------|--------|
| POST   | `/api/monitor/baseline`                    | Compute and persist baseline stats for all features.         | `monitor.py:46` (`compute_baseline`) |
| GET    | `/api/monitor/check`                       | Run quality checks (optional LLM analysis).                  | `monitor.py:60` (`run_check`) |
| GET    | `/api/monitor/report`                      | Monitoring report (no LLM, always fast).                     | `monitor.py:105` (`monitoring_report`) |
| GET    | `/api/monitor/history/{feature_spec:path}` | PSI history for a feature.                                   | `monitor.py:115` (`monitoring_history`) |
| GET    | `/api/monitor/baseline/{feature_spec:path}` | Baseline stats for a feature.                               | `monitor.py:125` (`get_baseline`) |
| GET    | `/api/monitor/metrics/{feature_spec:path}` | Per-check metric history for the multi-metric chart.         | `monitor.py:137` (`metric_history`) |
| GET    | `/api/monitor/drift-rate`                  | Catalog-wide drift-rate trend (per day).                     | `monitor.py:158` (`drift_rate`) |

## AI

Router prefix: `/api/ai`. Source: `featcat/server/routes/ai.py`.

| Method | Path                  | Description                                                        | Returns | Source |
|--------|-----------------------|--------------------------------------------------------------------|---------|--------|
| POST   | `/api/ai/discover`    | Feature discovery for a use case.                                  | JSON    | `ai.py:61` (`discover`) |
| POST   | `/api/ai/ask`         | Natural-language query about features.                             | JSON    | `ai.py:97` (`ask`) |
| GET    | `/api/ai/ask/stream`  | Streaming NL query.                                                | **SSE** (`EventSourceResponse`, `ai.py:247`) | `ai.py:131` (`stream_ask`) |
| POST   | `/api/ai/chat`        | Agentic chat with tool calling and session memory.                 | **SSE** (`EventSourceResponse`, `ai.py:362`) | `ai.py:260` (`agent_chat`) |

## Search

Router prefix: `/api/search`. Source: `featcat/server/routes/search.py`.

| Method | Path                  | Description                                                          | Source |
|--------|-----------------------|----------------------------------------------------------------------|--------|
| GET    | `/api/search`         | Ranked full-text search (Postgres tsvector + GIN; SQLite FTS5 fallback). | `search.py:17` (`search`) |
| GET    | `/api/search/facets`  | Facet counts for the search sidebar.                                 | `search.py:36` (`search_facets`) |

## Lineage

Router prefix: `/api/lineage`. Source: `featcat/server/routes/lineage.py`.

| Method | Path                  | Description                                                  | Source |
|--------|-----------------------|--------------------------------------------------------------|--------|
| GET    | `/api/lineage/impact` | Features impacted by a source[.column] change.               | `lineage.py:20` (`lineage_impact`) |
| GET    | `/api/lineage/full`   | Catalog-wide feature→feature lineage graph.                  | `lineage.py:39` (`lineage_full`) |

## Groups

Router prefix: `/api/groups`. Source: `featcat/server/routes/groups.py`.

| Method | Path                                                       | Description                                                 | Source |
|--------|------------------------------------------------------------|-------------------------------------------------------------|--------|
| GET    | `/api/groups`                                              | List all feature groups.                                    | `groups.py:42` (`list_groups`) |
| POST   | `/api/groups`                                              | Create a new feature group.                                 | `groups.py:54` (`create_group`) |
| GET    | `/api/groups/{name}`                                       | Get a group with its member features.                       | `groups.py:65` (`get_group`) |
| PATCH  | `/api/groups/{name}`                                       | Update mutable group metadata.                              | `groups.py:78` (`update_group`) |
| DELETE | `/api/groups/{name}`                                       | Delete a feature group.                                     | `groups.py:90` (`delete_group`) |
| POST   | `/api/groups/{name}/members`                               | Add features to a group.                                    | `groups.py:100` (`add_members`) |
| DELETE | `/api/groups/{name}/members`                               | Remove a feature from a group.                              | `groups.py:123` (`remove_member`) |
| GET    | `/api/groups/{name}/health`                                | Aggregate health score and grade distribution.              | `groups.py:148` (`group_health`) |
| GET    | `/api/groups/{name}/monitoring`                            | Latest drift/PSI status across members.                     | `groups.py:201` (`group_monitoring`) |
| POST   | `/api/groups/{name}/regenerate-docs`                       | Kick off batch doc regeneration scoped to group members.    | `groups.py:272` (`group_regenerate_docs`) |
| POST   | `/api/groups/{name}/freeze`                                | Snapshot group members as an immutable version.             | `groups.py:388` (`freeze_group`) |
| GET    | `/api/groups/{name}/versions`                              | List frozen versions for a group.                           | `groups.py:406` (`list_group_versions`) |
| GET    | `/api/groups/{name}/versions/{version_number}`             | Fetch a single frozen version with snapshot and warnings.   | `groups.py:423` (`get_group_version`) |
| GET    | `/api/groups/{name}/versions/{version_number}/export`      | Export a frozen version as a feature manifest (JSON/CSV/Parquet). | `groups.py:441` (`export_group_version`) |
| GET    | `/api/groups/{name}/drift-matrix`                          | Per-member × per-day severity matrix for the heatmap.       | `groups.py:547` (`group_drift_matrix`) |

## Actions

Router prefix: `/api/actions`. Source: `featcat/server/routes/actions.py`.

| Method | Path                       | Description                                  | Source |
|--------|----------------------------|----------------------------------------------|--------|
| GET    | `/api/actions`             | List action items with optional filters.     | `actions.py:32` (`list_actions`) |
| GET    | `/api/actions/count`       | Count action items (optionally filtered).    | `actions.py:53` (`count_actions`) |
| POST   | `/api/actions`             | Create a new action item.                    | `actions.py:61` (`create_action`) |
| GET    | `/api/actions/{item_id}`   | Fetch a single action item.                  | `actions.py:87` (`get_action`) |
| PATCH  | `/api/actions/{item_id}`   | Update an action item's status.              | `actions.py:96` (`update_action`) |

## Jobs (schedule metadata)

Router prefix: `/api/jobs`. Source: `featcat/server/routes/jobs.py`.

| Method | Path                          | Description                                          | Source |
|--------|-------------------------------|------------------------------------------------------|--------|
| GET    | `/api/jobs`                   | List job schedules.                                  | `jobs.py:19` (`list_jobs`) |
| GET    | `/api/jobs/logs`              | List recent job execution logs.                      | `jobs.py:27` (`list_logs`) |
| GET    | `/api/jobs/logs/{log_id}`     | Detail of a single execution.                        | `jobs.py:41` (`get_log`) |
| POST   | `/api/jobs/{name}/run`        | Manually trigger a job.                              | `jobs.py:52` (`run_job`) |
| PATCH  | `/api/jobs/{name}`            | Update a job's schedule or enabled state.            | `jobs.py:61` (`update_job`) |
| PATCH  | `/api/jobs/{name}/toggle`     | Toggle a job's enabled flag.                         | `jobs.py:74` (`toggle_job`) |
| GET    | `/api/jobs/stats`             | Aggregated job stats with sparkline data.            | `jobs.py:88` (`job_stats`) |

## Scheduler (live runtime view)

Router prefix: `/api/scheduler`. Source: `featcat/server/routes/scheduler.py`.

| Method | Path                                  | Description                                                            | Source |
|--------|---------------------------------------|------------------------------------------------------------------------|--------|
| GET    | `/api/scheduler/jobs`                 | List all jobs with last-run summary and active backend.                | `scheduler.py:214` (`list_jobs`) |
| GET    | `/api/scheduler/jobs/{name}`          | Detailed view: schedule + last 20 runs + active task ids.              | `scheduler.py:227` (`get_job_detail`) |
| POST   | `/api/scheduler/jobs/{name}/run`      | Trigger immediately; returns a tracking handle.                        | `scheduler.py:254` (`trigger_job`) |
| GET    | `/api/scheduler/runs`                 | Paginated `job_logs` view for the history table.                       | `scheduler.py:329` (`list_runs`) |

## Admin

Router prefix: `/api/admin`. Source: `featcat/server/routes/admin.py`.

| Method | Path                              | Description                                       | Source |
|--------|-----------------------------------|---------------------------------------------------|--------|
| GET    | `/api/admin/cache/stats`          | LLM response-cache stats.                         | `admin.py:13` (`cache_stats`) |
| POST   | `/api/admin/cache/clear`          | Drop all entries from the LLM response cache.     | `admin.py:25` (`cache_clear`) |
| POST   | `/api/admin/cache/clear-expired`  | Drop only expired entries from the cache.         | `admin.py:38` (`cache_clear_expired`) |

## Usage

Router prefix: `/api/usage`. Source: `featcat/server/routes/usage.py`.

| Method | Path                    | Description                                            | Source |
|--------|-------------------------|--------------------------------------------------------|--------|
| GET    | `/api/usage/top`        | Most-used features by action count.                    | `usage.py:13` (`usage_top`) |
| GET    | `/api/usage/orphaned`   | Features with zero usage in the given period.          | `usage.py:23` (`usage_orphaned`) |
| GET    | `/api/usage/activity`   | Per-day usage activity summary.                        | `usage.py:32` (`usage_activity`) |
| GET    | `/api/usage/feature`    | Usage summary for a single feature.                    | `usage.py:41` (`feature_usage`) |

## Scan (bulk)

Router prefix: `/api/scan-bulk`. Source: `featcat/server/routes/scan.py`.

| Method | Path                | Description                                                                | Source |
|--------|---------------------|----------------------------------------------------------------------------|--------|
| POST   | `/api/scan-bulk`    | Scan a directory or S3 prefix and register Parquet files as sources+features. | `scan.py:45` (`bulk_scan`) |

## Export

Router prefix: `/api/export`. Source: `featcat/server/routes/export.py`.

| Method | Path                              | Description                                  | Returns | Source |
|--------|-----------------------------------|----------------------------------------------|---------|--------|
| POST   | `/api/export`                     | Create a feature data export.                | JSON    | `export.py:33` (`create_export`) |
| GET    | `/api/export/{export_id}/download` | Download an exported file.                  | **file** (CSV or `application/octet-stream`) | `export.py:89` (`download_export`) |

## Versions

Router prefix: `/api/versions`. Source: `featcat/server/routes/versions.py`.

| Method | Path                      | Description                                          | Source |
|--------|---------------------------|------------------------------------------------------|--------|
| GET    | `/api/versions/recent`    | Recent feature-version changes for the audit log.    | `versions.py:12` (`recent_versions`) |

## Notifications

Router prefix: `/api/notifications`. Source: `featcat/server/routes/notifications.py`.

| Method | Path                                            | Description                                            | Source |
|--------|-------------------------------------------------|--------------------------------------------------------|--------|
| GET    | `/api/notifications`                            | Paginated notification feed (newest first).            | `notifications.py:22` (`list_notifications`) |
| GET    | `/api/notifications/unread-count`               | Single-int badge value for the unread count.           | `notifications.py:31` (`unread_count`) |
| POST   | `/api/notifications/{notification_id}/read`     | Mark one notification as read.                         | `notifications.py:37` (`mark_read`) |
| POST   | `/api/notifications/read-all`                   | Mark every unread notification as read.                | `notifications.py:44` (`mark_all_read`) |

---

## Summary

- **20 routers / mount points** (19 `/api/*` routers + 3 app-level routes).
- **~110 JSON endpoints**, **2 SSE endpoints** (`/api/ai/ask/stream`, `/api/ai/chat`), **1 file-download** endpoint (`/api/export/{export_id}/download`), **1 static-files mount** (`/assets`).
- SSE responses use `sse_starlette.sse.EventSourceResponse`. Every LLM-calling
  route is `async` and wraps its blocking work in `run_in_threadpool` + a
  timeout (`featcat/server/routes/ai.py`, etc.).
