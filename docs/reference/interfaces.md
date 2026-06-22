# Interfaces Reference

featcat ships three end-user interfaces against one shared backend
abstraction (`CatalogBackend`): the `featcat` CLI, the Textual-based TUI,
and the React Web UI served by the FastAPI app. This document enumerates
every command, screen, and route that exists in the current source.

## Source of truth

- Audit SHA: `84041cd7264d705c82f5a150618d2e4b37e2c547`
- CLI entry point: `featcat = "featcat.cli:app"` (`pyproject.toml`)
- CLI root: `featcat/cli.py` (4463 lines)
- TUI root: `featcat/tui/app.py`, screens in `featcat/tui/screens/`
- Web router config: `web/src/App.tsx`, pages in `web/src/pages/`
- Web API client (single chokepoint for backend calls): `web/src/api.ts`
- HTTP API surface (consumed by Web UI and remote-backend clients): see
  [`api.md`](./api.md) in this directory.

---

## CLI

### Root commands

Registered directly on the top-level Typer app in `featcat/cli.py`.

| Command            | Description                                                                  | Source |
|--------------------|------------------------------------------------------------------------------|--------|
| `featcat init`         | Initialize the catalog database.                                         | `cli.py:129` (`init`) |
| `featcat quickstart`   | Non-interactive setup: write a default deployment directory.             | `cli.py:142` (`quickstart_cmd`) |
| `featcat setup`        | Interactive setup wizard.                                                | `cli.py:163` (`setup_cmd`) |
| `featcat add`          | Register, scan, and (optionally) auto-document a source in one step.     | `cli.py:184` (`add`) |
| `featcat stats`        | Catalog overview statistics.                                             | `cli.py:418` (`stats`) |
| `featcat export`       | Export catalog metadata or feature data.                                 | `cli.py:477` (`export_catalog`) |
| `featcat discover`     | AI-driven feature discovery for a use case.                              | `cli.py:1306` (`discover`) |
| `featcat ask`          | Natural-language feature search.                                         | `cli.py:1387` (`ask`) |
| `featcat chat`         | Interactive agentic chat (streams SSE from `/api/ai/chat`).              | `cli.py:1453` (`chat`) |
| `featcat serve`        | Start the FastAPI server (uvicorn factory, 4 workers).                   | `cli.py:2151` (`serve`) |
| `featcat scan-bulk`    | Scan a directory or S3 prefix and register Parquet files.                | `cli.py:2183` (`scan_bulk`) |
| `featcat embed`        | Generate vector embeddings for features.                                 | `cli.py:3343` (`embed`) |
| `featcat impact`       | Show features impacted by changes to a source or `source.column`.        | `cli.py:3493` (`impact`) |
| `featcat restore`      | Restore a catalog from a backup archive.                                 | `cli.py:4313` (`restore_cmd`) |
| `featcat ui`           | Launch the Textual TUI (`featcat.tui.app.FeatcatApp`).                   | `cli.py:4439` (`ui`) |

### Sub-apps

Each line below is a `app.add_typer(...)` mount in `featcat/cli.py` (lines 52–64,
295, 3408). Commands are grouped by the sub-app they live under.

#### `featcat source` — Manage data sources

| Command                  | Description                                                         | Source |
|--------------------------|---------------------------------------------------------------------|--------|
| `source add`             | Register a new data source.                                         | `cli.py:615` (`source_add`) |
| `source list`            | List all registered sources.                                        | `cli.py:646` (`source_list`) |
| `source scan`            | Scan a source and auto-register its columns as features.            | `cli.py:683` (`source_scan`) |
| `source rm`              | Hard-delete a source and cascade-remove its features.               | `cli.py:721` (`source_rm`) |
| `source update`          | Update mutable fields on a source (description, format).            | `cli.py:775` (`source_update`) |

#### `featcat feature` — Manage features

| Command                       | Description                                                              | Source |
|-------------------------------|--------------------------------------------------------------------------|--------|
| `feature list`                | List features with rich filtering matching the API.                      | `cli.py:806` (`feature_list`) |
| `feature info`                | Show detailed information about a feature.                               | `cli.py:910` (`feature_info`) |
| `feature rm`                  | Hard-delete a feature and cascade dependents.                            | `cli.py:950` (`feature_rm`) |
| `feature update`              | Update mutable fields on a feature.                                      | `cli.py:980` (`feature_update`) |
| `feature bulk-tag`            | Bulk-apply a tag change.                                                 | `cli.py:1035` (`feature_bulk_tag`) |
| `feature bulk-delete`         | Bulk hard-delete features.                                               | `cli.py:1093` (`feature_bulk_delete`) |
| `feature tag`                 | Add tags to a feature.                                                   | `cli.py:1147` (`feature_tag`) |
| `feature search`              | Keyword search across features.                                          | `cli.py:1166` (`feature_search`) |
| `feature history`             | Show version history.                                                    | `cli.py:1196` (`feature_history`) |
| `feature diff`                | Diff two versions of a feature.                                          | `cli.py:1225` (`feature_diff`) |
| `feature rollback`            | Rollback a feature to a prior version.                                   | `cli.py:1265` (`feature_rollback`) |
| `feature set-definition`      | Set a feature's definition (SQL, Python, or manual).                     | `cli.py:2797` (`feature_set_definition`) |
| `feature show-definition`     | Show a feature's definition.                                             | `cli.py:2826` (`feature_show_definition`) |
| `feature set-hint`            | Set generation hints used by the autodoc plugin.                         | `cli.py:2859` (`feature_set_hint`) |
| `feature show-hint`           | Show generation hints.                                                   | `cli.py:2876` (`feature_show_hint`) |
| `feature similar`             | Find features similar to the given one (calls the server).               | `cli.py:2895` (`feature_similar`) |
| `feature clear-hint`          | Remove generation hints.                                                 | `cli.py:2932` (`feature_clear_hint`) |
| `feature health`              | Show health-score breakdown for a feature.                               | `cli.py:2994` (`feature_health`) |
| `feature health-report`       | Health report for all features.                                          | `cli.py:3040` (`feature_health_report`) |

#### `featcat doc` — AI documentation

| Command          | Description                                          | Source |
|------------------|------------------------------------------------------|--------|
| `doc generate`   | Generate AI documentation for features.              | `cli.py:1531` (`doc_generate`) |
| `doc show`       | Display documentation for a feature.                 | `cli.py:1606` (`doc_show`) |
| `doc export`     | Export all docs to Markdown.                         | `cli.py:1636` (`doc_export`) |
| `doc stats`      | Documentation coverage statistics.                   | `cli.py:1652` (`doc_stats`) |

#### `featcat monitor` — Quality monitoring

| Command            | Description                                                | Source |
|--------------------|------------------------------------------------------------|--------|
| `monitor baseline` | Compute and save baseline statistics for all features.     | `cli.py:1677` (`monitor_baseline`) |
| `monitor check`    | Run quality / drift checks.                                | `cli.py:1699` (`monitor_check`) |
| `monitor history`  | Drift check history for a feature.                         | `cli.py:1770` (`monitor_history`) |
| `monitor report`   | Export a monitoring report to Markdown.                    | `cli.py:1795` (`monitor_report`) |

#### `featcat cache` — LLM response cache

| Command         | Description                              | Source |
|-----------------|------------------------------------------|--------|
| `cache stats`   | Show cache statistics.                   | `cli.py:1818` (`cache_stats`) |
| `cache clear`   | Clear all cached LLM responses.          | `cli.py:1834` (`cache_clear`) |

#### `featcat config` — Configuration

| Command         | Description                                | Source |
|-----------------|--------------------------------------------|--------|
| `config show`   | Show all current configuration values.     | `cli.py:1851` (`config_show`) |
| `config get`    | Get a configuration value.                 | `cli.py:1876` (`config_get`) |
| `config set`    | Set a configuration value.                 | `cli.py:1890` (`config_set`) |
| `config reset`  | Reset configuration to defaults.           | `cli.py:1928` (`config_reset`) |
| `config path`   | Show configuration file locations.         | `cli.py:1954` (`config_path`) |

#### `featcat job` — Scheduled jobs

| Command          | Description                                | Source |
|------------------|--------------------------------------------|--------|
| `job list`       | List scheduled jobs.                       | `cli.py:1999` (`job_list`) |
| `job logs`       | Recent job execution logs.                 | `cli.py:2032` (`job_logs`) |
| `job run`        | Manually trigger a job.                    | `cli.py:2074` (`job_run`) |
| `job enable`     | Enable a scheduled job.                    | `cli.py:2101` (`job_enable`) |
| `job disable`    | Disable a scheduled job.                   | `cli.py:2115` (`job_disable`) |
| `job schedule`   | Change a job's cron schedule.              | `cli.py:2129` (`job_schedule`) |

#### `featcat group` — Feature groups

| Command                    | Description                                                  | Source |
|----------------------------|--------------------------------------------------------------|--------|
| `group create`             | Create a new feature group.                                  | `cli.py:2283` (`group_create`) |
| `group list`               | List feature groups.                                         | `cli.py:2303` (`group_list`) |
| `group show`               | Show group details and member features.                      | `cli.py:2342` (`group_show`) |
| `group add`                | Add features to a group.                                     | `cli.py:2375` (`group_add`) |
| `group remove`             | Remove features from a group.                                | `cli.py:2403` (`group_remove`) |
| `group delete`             | Delete a feature group.                                      | `cli.py:2427` (`group_delete`) |
| `group update`             | Update mutable group fields.                                 | `cli.py:2450` (`group_update`) |
| `group health`             | Aggregate health metrics for a group.                        | `cli.py:2485` (`group_health`) |
| `group monitoring`         | Aggregate latest drift status across members.                | `cli.py:2538` (`group_monitoring`) |
| `group regenerate-docs`    | Kick off batch doc regeneration via the server.              | `cli.py:2591` (`group_regenerate_docs`) |
| `group freeze`             | Snapshot the current members as an immutable version.        | `cli.py:2638` (`group_freeze`) |
| `group versions`           | List frozen versions.                                        | `cli.py:2670` (`group_versions`) |
| `group export`             | Export a frozen group version.                               | `cli.py:2706` (`group_export`) |

#### `featcat usage` — Usage analytics

| Command            | Description                                       | Source |
|--------------------|---------------------------------------------------|--------|
| `usage top`        | Top features by usage count.                      | `cli.py:3127` (`usage_top`) |
| `usage orphaned`   | Features with zero usage in the given period.     | `cli.py:3155` (`usage_orphaned`) |
| `usage activity`   | Per-day usage activity summary.                   | `cli.py:3181` (`usage_activity`) |

#### `featcat actions` — Recommended action items

| Command            | Description                                       | Source |
|--------------------|---------------------------------------------------|--------|
| `actions list`     | List action items.                                | `cli.py:3219` (`actions_list`) |
| `actions show`     | Show full detail of an action item.               | `cli.py:3268` (`actions_show`) |
| `actions apply`    | Mark an action item as applied.                   | `cli.py:3294` (`actions_apply`) |
| `actions dismiss`  | Dismiss an action item.                           | `cli.py:3304` (`actions_dismiss`) |

#### `featcat status` — Feature lifecycle

| Command           | Description                                                                          | Source |
|-------------------|--------------------------------------------------------------------------------------|--------|
| `status show`     | Show a feature's current status, last-change timestamp, and notes.                   | `cli.py:3411` (`status_show`) |
| `status set`      | Set a feature's status (transition to `certified` runs the readiness checklist).     | `cli.py:3426` (`status_set`) |
| `status check`    | Check whether a feature meets the certification checklist.                           | `cli.py:3451` (`status_check`) |
| `status list`     | List features in a given status.                                                     | `cli.py:3468` (`status_list`) |

#### `featcat lineage` — Lineage tracking

| Command              | Description                                                                   | Source |
|----------------------|-------------------------------------------------------------------------------|--------|
| `lineage detect`     | Auto-detect feature→feature lineage from SQL definitions.                     | `cli.py:3536` (`lineage_detect`) |
| `lineage seed`       | Import lineage edges from a JSON fixture (auto-creates missing features).     | `cli.py:3863` (`lineage_seed`) |
| `lineage clear`      | Remove demo lineage seeded by `lineage seed`.                                 | `cli.py:4047` (`lineage_clear`) |
| `lineage edge add`   | Manually add a feature→feature lineage edge.                                  | `cli.py:4133` (`lineage_edge_add`) |
| `lineage edge rm`    | Remove a feature→feature lineage edge.                                        | `cli.py:4166` (`lineage_edge_rm`) |

#### `featcat demo` — Demo data

| Command         | Description                                          | Source |
|-----------------|------------------------------------------------------|--------|
| `demo seed`     | Populate the catalog with bundled demo data.         | `cli.py:4205` (`demo_seed`) |
| `demo clear`    | Remove every demo-tagged row.                        | `cli.py:4242` (`demo_clear`) |

#### `featcat backup` — Catalog backups

| Command           | Description                                                                       | Source |
|-------------------|-----------------------------------------------------------------------------------|--------|
| `backup` (no arg) | Create a backup archive of the current catalog (callback on the sub-app).         | `cli.py:4274` (`backup_root`) |
| `backup list`     | List backup archives in a directory.                                              | `cli.py:4290` (`backup_list_cmd`) |

#### `featcat doctor` — Diagnostics

| Command           | Description                                                                       | Source |
|-------------------|-----------------------------------------------------------------------------------|--------|
| `doctor` (no arg) | Run every diagnostic group (callback when invoked with no subcommand).            | `cli.py:367` (`doctor_root`) |
| `doctor deploy`   | Git, Docker, and docker-compose validity.                                         | `cli.py:378` (`doctor_deploy`) |
| `doctor db`       | DB reachability, version, migrations, catalog stats.                              | `cli.py:386` (`doctor_db`) |
| `doctor llm`      | LLM reachability, model identity, context size, slot availability.                | `cli.py:394` (`doctor_llm`) |
| `doctor network`  | TCP probes, proxy correctness, S3 endpoint.                                       | `cli.py:402` (`doctor_network`) |
| `doctor data`     | Sources, stats coverage, doc coverage, drift recency, lineage coverage.           | `cli.py:410` (`doctor_data`) |

### How the CLI reaches the catalog

The CLI does not call HTTP endpoints directly. It uses `get_backend()`
(`featcat/catalog/factory.py`) which returns either:

- `LocalBackend` (`featcat/catalog/local.py`) — direct SQLAlchemy access; the default.
- `RemoteBackend` (`featcat/catalog/remote.py`) — HTTP client that calls the
  REST API, used when `FEATCAT_SERVER_URL` is set.

A handful of commands talk to the server directly regardless of the backend
because the work is server-resident:

- `featcat chat` streams from `POST /api/ai/chat`.
- `featcat feature similar` calls `GET /api/features/by-name/similar`.
- `featcat group regenerate-docs` calls `POST /api/groups/{name}/regenerate-docs`.
- `featcat serve` boots the API process (`uvicorn` factory).

---

## TUI

The terminal UI is implemented with [Textual](https://textual.textualize.io/)
and gated behind the optional `tui` extra. It is launched from the CLI:
`featcat ui` → `FeatcatApp().run()` (`featcat/cli.py:4443`).

### App and global bindings

Source: `featcat/tui/app.py`.

| Binding | Action               | Source |
|---------|----------------------|--------|
| `q`     | Quit                 | `app.py:30-33` |
| `?`     | Show help notification | `app.py:30-33` |

### Screens

| Screen          | Class               | Source                          | Reached via | Purpose |
|-----------------|---------------------|---------------------------------|-------------|---------|
| `dashboard`     | `DashboardScreen`   | `featcat/tui/screens/dashboard.py` | `d` / startup | Stats bar, welcome message, recent monitoring alerts. |
| `features`      | `FeaturesScreen`    | `featcat/tui/screens/features.py`  | `f` / `/`     | Feature table with search input and detail side panel. |
| `monitoring`    | `MonitoringScreen`  | `featcat/tui/screens/monitoring.py` | `m` / `r` / `b` | Quality table with severity/PSI columns; run check, recompute baseline. |
| `chat`          | `ChatScreen`        | `featcat/tui/screens/chat.py`      | `c`           | AI chat input/output; supports `/discover`, `/search`, `/monitor` commands. |

All four screen files in `featcat/tui/screens/` are registered in the app's
`MODES` map — no orphans.

### How the TUI reaches the catalog

The TUI uses the same `get_backend()` factory as the CLI plus the plugin
system (`DiscoveryPlugin`, `MonitoringPlugin`, `NLQueryPlugin`, `AutodocPlugin`)
and an optional `BaseLLM` created via `create_llm(...)`. It does **not** make
HTTP calls of its own — it talks to the database in-process unless
`FEATCAT_SERVER_URL` flips the factory to `RemoteBackend`.

---

## Web UI

The Web UI is a React 19 + TypeScript + Vite + Tailwind SPA. Source:
`web/src/`. Routes are registered with `react-router-dom` in
`web/src/App.tsx` and every page is lazy-loaded.

### Routes

| Path                 | Component                                  | Purpose |
|----------------------|--------------------------------------------|---------|
| `/`                  | `pages/Dashboard.tsx` (`Dashboard`)        | Stats, alerts, quality trends, recent activity. |
| `/search`            | `pages/Search.tsx` (`Search`)              | Ranked full-text search with faceted filtering. |
| `/features`          | `pages/Features.tsx` (`Features`)          | Browseable feature table. |
| `/features/:name`    | `pages/Features.tsx` (`Features`)          | Feature detail (docs, monitoring, lineage, usage, definitions). |
| `/business-metrics`  | `pages/BusinessMetrics.tsx` (`BusinessMetrics`) | Business metric registry, CX matrix, and CSV import. |
| `/business-metrics/:name` | `pages/BusinessMetrics.tsx` (`BusinessMetrics`) | Business metric detail and mapped feature links. |
| `/groups`            | `pages/Groups.tsx` (`Groups`)              | Feature groups: membership, health, versioning. |
| `/sources`           | `pages/Sources.tsx` (`Sources`)            | Data sources: local/S3, scan logs, impact. |
| `/sources/:name`     | `pages/Sources.tsx` (`Sources`)            | Single-source detail. |
| `/similarity`        | `pages/Similarity.tsx` (`Similarity`)      | Feature similarity graph and matrix. |
| `/lineage`           | `pages/Lineage.tsx` (`Lineage`)            | Interactive lineage graph. |
| `/audit`             | `pages/Audit.tsx` (`Audit`)                | Audit log of feature changes. |
| `/monitoring`        | `pages/Monitoring.tsx` (`Monitoring`)      | Quality checks, drift severity, PSI, baselines. |
| `/actions`           | `pages/Actions.tsx` (`Actions`)            | Action items (pending / applied / dismissed / snoozed). |
| `/jobs`              | `pages/Jobs.tsx` (`Jobs`)                  | Scheduler jobs, runs, manual triggers. |
| `/chat`              | `pages/Chat.tsx` (`Chat`)                  | AI chat (streams from `POST /api/ai/chat`). |
| `/settings`          | `pages/Settings.tsx` (`Settings`)          | Preferences, cache management. |
| `/help`              | `pages/Help.tsx` (`Help`)                  | Glossary of metrics and severities. |
| `/dev/components`    | `pages/_dev/Components.tsx` (`Components`) | **Dev-only** component gallery; dead-code-eliminated in prod by the `import.meta.env.DEV` guard. |

Every file in `web/src/pages/` corresponds to a route above; there are no
orphan pages. The `web/src/pages/similarity/` subdirectory contains
sub-components (`SimilarityGraph`, `SimilarityMatrix`, `MatrixGrid`,
`PairPanel`) that are lazy-loaded inside `Similarity.tsx`, not standalone
routes.

### Layout and shared components

The router is wrapped in `<Layout>` from `web/src/components/Layout.tsx`,
which provides the persistent navigation shell.

### How the Web UI reaches the backend

All API calls go through `web/src/api.ts` (the `api` object plus
`invalidateCache()`), per the project's frontend rules. Every endpoint the
UI consumes appears in [`api.md`](./api.md). Notable consumption patterns:

- **Dashboard** — `/api/health`, `/api/stats`, `/api/stats/by-source`, `/api/stats/doc-debt`, `/api/features/health-summary`, `/api/features/stats/status-counts`, `/api/monitor/check`, `/api/jobs`, `/api/jobs/logs`, `/api/usage/top`, `/api/usage/orphaned`.
- **Features** — `/api/sources`, `/api/features`, `/api/features/by-name`, `/api/features/by-name/definition`, `/api/features/by-name/hints`, `/api/features/bulk/{tags,groups,delete}`, `/api/docs/by-name`, `/api/docs/generate-batch[/...]`, `/api/monitor/check`, `/api/usage/feature`.
- **Business Metrics** — `/api/business-metrics`, `/api/business-metrics/by-name`, `/api/business-metrics/import-csv`.
- **Groups** — full `/api/groups/*` surface including `/health`, `/monitoring`, `/drift-matrix`, `/versions`, `/versions/{n}/export`, and `/regenerate-docs`.
- **Sources** — `/api/sources` CRUD, `/api/sources/{name}/scan`, `/api/sources/{name}/scan-logs`, `/api/sources/{name}/impact`, `/api/stats/by-source`.
- **Similarity** — `/api/features/similarity-graph`, `/api/features/similarity-matrix`, `/api/features/similarity-pair`.
- **Lineage** — `/api/lineage/full`.
- **Monitoring** — `/api/monitor/check`, `/api/monitor/baseline[/...]`, `/api/monitor/report`, `/api/monitor/metrics/...`, `/api/monitor/drift-rate`.
- **Audit** — `/api/versions/recent`.
- **Chat** — `/api/health` (LLM check) and the SSE stream `POST /api/ai/chat`.
- **Jobs** — `/api/jobs*`, `/api/scheduler/jobs*`, `/api/scheduler/runs`.
- **Actions** — `/api/actions[/{id}]`.
- **Settings** — `/api/admin/cache/{stats,clear,clear-expired}`.
- **Search** — `/api/search`, `/api/search/facets`.
- **Help** — `/api/docs/glossary`, `/api/docs/stats`.

---

## Packaging — what actually ships

From `pyproject.toml`:

- Console script: `featcat = "featcat.cli:app"` (the only entry point).
- The TUI lives behind the optional `tui` extra (`pip install featcat[tui]`).
- The Web UI is built by `cd web && bun run build` into
  `featcat/server/static/` and served by the FastAPI app from the same
  Python package (editable install in Docker, so `Path(__file__)` resolves
  the static directory at runtime).
