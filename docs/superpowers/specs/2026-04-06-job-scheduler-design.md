# Job Scheduler & Logging System — Design Spec

**Date:** 2026-04-06
**Scope:** Phase 6.1 — Internal job scheduler for featcat server
**Status:** Approved

## Purpose

Add an internal job scheduler to the featcat FastAPI server so cron-like tasks (monitoring checks, doc generation, source re-scans, baseline refreshes) run automatically. All executions are logged to SQLite for auditability and the future Web UI dashboard.

## Architecture Overview

APScheduler `AsyncIOScheduler` runs inside the FastAPI event loop. Schedules are defined with defaults in config, with runtime overrides persisted in SQLite. Every job execution is logged to a `job_logs` table.

```
FastAPI lifespan
  ├── LocalBackend (init_db with new tables)
  ├── LLM instance
  └── FeatcatScheduler
        ├── APScheduler (AsyncIOScheduler)
        ├── Reads job_schedules from SQLite
        └── Logs to job_logs on each run
```

## Database Schema

### New table: `job_schedules`

```sql
CREATE TABLE IF NOT EXISTS job_schedules (
    job_name TEXT PRIMARY KEY,
    cron_expression TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    description TEXT DEFAULT '',
    max_log_retention_days INTEGER DEFAULT 30
)
```

### New table: `job_logs`

```sql
CREATE TABLE IF NOT EXISTS job_logs (
    id TEXT PRIMARY KEY,
    job_name TEXT NOT NULL,
    status TEXT NOT NULL,         -- "running", "success", "failed", "warning"
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    duration_seconds REAL,
    result_summary TEXT DEFAULT '{}',  -- JSON: {"features_checked": 147, ...}
    error_message TEXT,
    triggered_by TEXT NOT NULL    -- "scheduler", "manual", "api"
)
```

### Modified table: `data_sources`

Add column: `auto_refresh INTEGER DEFAULT 0` — controls whether `source_scan` job re-scans this source.

### Default schedules (seeded on first init)

| job_name | cron_expression | description | max_log_retention_days |
|----------|----------------|-------------|----------------------|
| monitor_check | `0 */6 * * *` | Check all features for drift | 30 |
| doc_generate | `0 2 * * *` | Generate docs for undocumented features | 30 |
| source_scan | `0 1 * * *` | Re-scan auto_refresh sources | 30 |
| baseline_refresh | `0 3 * * 0` | Refresh baselines weekly | 60 |

## Scheduler Module

**File:** `featcat/server/scheduler.py`

### Data access

The scheduler manages `job_schedules` and `job_logs` tables directly via the `LocalBackend`'s SQLite connection (accessed as `backend.conn`). These tables are NOT part of the `CatalogBackend` abstract interface because they are server-specific concerns — `RemoteBackend` accesses job data via the `/api/jobs` HTTP endpoints instead.

### Class: `FeatcatScheduler`

```python
class FeatcatScheduler:
    def __init__(self, backend: CatalogBackend, llm, settings: Settings): ...
    def setup_default_jobs(self) -> None: ...
    def start(self) -> None: ...
    def stop(self) -> None: ...
    async def run_job(self, job_name: str, triggered_by: str = "scheduler") -> dict: ...
    def get_schedules(self) -> list[dict]: ...
    def update_schedule(self, job_name: str, cron: str | None, enabled: bool | None) -> None: ...
```

### Schedule loading (startup)

1. Check `job_schedules` table
2. If empty, seed with defaults (from hardcoded defaults; config can override via `FEATCAT_JOB_*` env vars)
3. For each enabled job, register with `AsyncIOScheduler` using `CronTrigger.from_crontab(cron_expression)`
4. SQLite overrides persist across restarts

### Job execution flow

1. Insert `job_logs` row: status="running", started_at=now, triggered_by
2. Call internal `_execute(job_name)` which routes to the right plugin
3. On success: update log (status="success", result_summary, finished_at, duration)
4. On failure: update log (status="failed", error_message, finished_at, duration)
5. Update `job_schedules.last_run_at`
6. Purge logs older than `max_log_retention_days` for this job

### Job implementations

| Job | Implementation |
|-----|---------------|
| monitor_check | `MonitoringPlugin.execute(db, llm, action="check")` |
| doc_generate | `AutodocPlugin.execute(db, llm)` — documents undocumented features |
| source_scan | For each source with `auto_refresh=1`: `scan_source(path)` + `upsert_feature` |
| baseline_refresh | `MonitoringPlugin.execute(db, None, action="baseline")` |

## API Endpoints

**New file:** `featcat/server/routes/jobs.py`

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/jobs` | List all job schedules |
| GET | `/api/jobs/logs` | List recent logs. Query params: `job_name`, `status`, `limit` (default 50), `offset` |
| GET | `/api/jobs/logs/{id}` | Detail of one job execution |
| POST | `/api/jobs/{name}/run` | Manually trigger a job. Returns job log entry. |
| PATCH | `/api/jobs/{name}` | Update schedule. Body: `{cron_expression?, enabled?}` |
| GET | `/api/jobs/stats` | Aggregated stats + sparkline data |

### `/api/jobs/stats` response format

```json
{
  "jobs": {
    "monitor_check": {
      "total_runs": 42,
      "success_rate": 0.95,
      "avg_duration_seconds": 12.3,
      "last_status": "success",
      "sparkline": [
        {"date": "2026-03-31", "success": 4, "failed": 0, "warning": 0},
        {"date": "2026-04-01", "success": 4, "failed": 0, "warning": 0},
        ...
      ]
    },
    ...
  }
}
```

Sparkline covers last 7 days, one entry per day with counts by status.

## CLI Commands

**New Typer subgroup:** `job_app` registered as `featcat job`

| Command | Description |
|---------|-------------|
| `featcat job list` | Table: name, schedule, enabled, last run, next run |
| `featcat job logs [--job NAME] [--limit N]` | Recent job logs |
| `featcat job run <name>` | Manually trigger (local or via API) |
| `featcat job enable <name>` | Enable a scheduled job |
| `featcat job disable <name>` | Disable a scheduled job |
| `featcat job schedule <name> "<cron>"` | Change cron expression |

When `server_url` is set, CLI commands call the API. Otherwise, they operate on the local SQLite directly.

## Server Integration

**Modified:** `featcat/server/app.py` lifespan:

```python
# After backend.init_db() and LLM creation:
scheduler = FeatcatScheduler(backend, llm, settings)
scheduler.setup_default_jobs()
scheduler.start()
app.state.scheduler = scheduler

# In lifespan cleanup:
scheduler.stop()
```

**New dependency in deps.py:**
```python
def get_scheduler(request: Request) -> FeatcatScheduler:
    return request.app.state.scheduler
```

## Configuration

**New fields in `Settings`:**
- `job_monitor_check_cron: str = "0 */6 * * *"`
- `job_doc_generate_cron: str = "0 2 * * *"`
- `job_source_scan_cron: str = "0 1 * * *"`
- `job_baseline_refresh_cron: str = "0 3 * * 0"`

These serve as initial defaults when seeding `job_schedules`. Once the table is populated, SQLite values take precedence.

## Dependencies

**Modified `pyproject.toml`:**
```toml
server = ["fastapi>=0.110", "uvicorn[standard]>=0.27", "sse-starlette>=1.6", "apscheduler>=3.10"]
```

## Files Changed/Created

| File | Action |
|------|--------|
| `featcat/server/scheduler.py` | NEW — FeatcatScheduler class |
| `featcat/server/routes/jobs.py` | NEW — all /api/jobs endpoints |
| `featcat/server/app.py` | MODIFIED — scheduler in lifespan, register jobs router |
| `featcat/server/deps.py` | MODIFIED — add get_scheduler dependency |
| `featcat/catalog/local.py` | MODIFIED — add job_logs, job_schedules tables to init_db; add auto_refresh to data_sources |
| `featcat/catalog/backend.py` | UNCHANGED — job tables are managed by the scheduler directly, not through CatalogBackend |
| `featcat/cli.py` | MODIFIED — add job_app Typer group |
| `featcat/config.py` | MODIFIED — add job cron default fields |
| `pyproject.toml` | MODIFIED — add apscheduler to server extra |
| `tests/test_scheduler.py` | NEW — scheduler unit tests |
| `tests/test_job_api.py` | NEW — job API endpoint tests |

## Testing

- **test_scheduler.py:** Mock APScheduler, verify job execution creates correct log entries, test retention purge, test schedule update
- **test_job_api.py:** Use FastAPI TestClient, test all /api/jobs endpoints, test manual trigger, test schedule CRUD
- **Existing tests:** Must still pass (new tables are additive, no breaking changes)

## Verification

1. `featcat serve` starts with scheduler running
2. `featcat job list` shows 4 default jobs
3. `featcat job run monitor_check` executes and creates a log entry
4. `featcat job logs` shows the execution
5. `GET /api/jobs/stats` returns sparkline data
6. Wait for a scheduled job to fire (set a short cron for testing)
