# Job Scheduler & Logging System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an internal job scheduler to the featcat server with cron-like scheduling, execution logging, API endpoints, and CLI commands.

**Architecture:** APScheduler `AsyncIOScheduler` runs inside the FastAPI event loop. Schedules default from config, with runtime overrides in SQLite. Each job execution is logged to a `job_logs` table. Jobs call existing plugin logic (same code as API endpoints).

**Tech Stack:** APScheduler 3.x, SQLite, FastAPI, Typer

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `featcat/catalog/local.py` | MODIFY | Add `job_schedules`, `job_logs` tables to schema; add `auto_refresh` column to `data_sources` |
| `featcat/config.py` | MODIFY | Add 4 job cron default fields |
| `featcat/server/scheduler.py` | CREATE | `FeatcatScheduler` class — schedule management, job execution, logging |
| `featcat/server/routes/jobs.py` | CREATE | All `/api/jobs` endpoints |
| `featcat/server/app.py` | MODIFY | Start/stop scheduler in lifespan, register jobs router |
| `featcat/server/deps.py` | MODIFY | Add `get_scheduler` dependency |
| `featcat/cli.py` | MODIFY | Add `job_app` Typer subgroup with 6 commands |
| `pyproject.toml` | MODIFY | Add `apscheduler>=3.10` to server extra |
| `tests/test_scheduler.py` | CREATE | Scheduler unit tests |
| `tests/test_job_api.py` | CREATE | Job API endpoint tests |

---

### Task 1: Add database schema for jobs

**Files:**
- Modify: `featcat/catalog/local.py:14-56` (SCHEMA_SQL)
- Test: `tests/test_catalog.py` (existing tests must still pass)

- [ ] **Step 1: Add job tables and auto_refresh column to SCHEMA_SQL**

In `featcat/catalog/local.py`, append these three statements to the end of the `SCHEMA_SQL` string (before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS job_schedules (
    job_name TEXT PRIMARY KEY,
    cron_expression TEXT NOT NULL,
    enabled INTEGER DEFAULT 1,
    last_run_at TIMESTAMP,
    next_run_at TIMESTAMP,
    description TEXT DEFAULT '',
    max_log_retention_days INTEGER DEFAULT 30
);

CREATE TABLE IF NOT EXISTS job_logs (
    id TEXT PRIMARY KEY,
    job_name TEXT NOT NULL,
    status TEXT NOT NULL,
    started_at TIMESTAMP NOT NULL,
    finished_at TIMESTAMP,
    duration_seconds REAL,
    result_summary TEXT DEFAULT '{}',
    error_message TEXT,
    triggered_by TEXT NOT NULL
);
```

And add the `auto_refresh` column to the existing `data_sources` table. Since SQLite uses `CREATE TABLE IF NOT EXISTS`, we can't ALTER in the schema string. Instead, add after the schema execution in `init_db()`:

```python
def init_db(self) -> None:
    self.conn.executescript(SCHEMA_SQL)
    # Add auto_refresh column if not present (added in Phase 6)
    try:
        self.conn.execute("ALTER TABLE data_sources ADD COLUMN auto_refresh INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass  # Column already exists
    self.conn.commit()
```

- [ ] **Step 2: Run existing tests to verify no breakage**

Run: `uv run --extra dev --extra server pytest tests/test_catalog.py -v`
Expected: All existing tests PASS (new tables are additive)

- [ ] **Step 3: Commit**

```bash
git add featcat/catalog/local.py
git commit -m "feat: add job_schedules and job_logs tables to schema"
```

---

### Task 2: Add job cron config defaults

**Files:**
- Modify: `featcat/config.py:88-91` (after monitoring thresholds)

- [ ] **Step 1: Add job schedule config fields to Settings**

In `featcat/config.py`, add these fields to the `Settings` class after the monitoring thresholds block:

```python
    # Job scheduler defaults (used to seed job_schedules on first run)
    job_monitor_check_cron: str = "0 */6 * * *"
    job_doc_generate_cron: str = "0 2 * * *"
    job_source_scan_cron: str = "0 1 * * *"
    job_baseline_refresh_cron: str = "0 3 * * 0"
```

- [ ] **Step 2: Run existing tests**

Run: `uv run --extra dev pytest tests/ -x -q`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add featcat/config.py
git commit -m "feat: add job schedule defaults to config"
```

---

### Task 3: Add apscheduler dependency

**Files:**
- Modify: `pyproject.toml:36` (server optional deps)

- [ ] **Step 1: Add apscheduler to server extra**

In `pyproject.toml`, change the `server` line under `[project.optional-dependencies]`:

```toml
server = ["fastapi>=0.110", "uvicorn[standard]>=0.27", "sse-starlette>=1.6", "apscheduler>=3.10"]
```

- [ ] **Step 2: Verify it installs**

Run: `uv run --extra server python -c "import apscheduler; print(apscheduler.__version__)"`
Expected: Prints version (3.10.x)

- [ ] **Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "feat: add apscheduler to server dependencies"
```

---

### Task 4: Build the scheduler module — tests first

**Files:**
- Create: `tests/test_scheduler.py`
- Create: `featcat/server/scheduler.py`

- [ ] **Step 1: Write scheduler tests**

Create `tests/test_scheduler.py`:

```python
"""Tests for the job scheduler."""

from __future__ import annotations

import json
import time
from unittest.mock import patch

import pytest

pytest.importorskip("apscheduler")

from featcat.catalog.local import LocalBackend
from featcat.config import load_settings


@pytest.fixture
def backend(tmp_path):
    db = LocalBackend(str(tmp_path / "test.db"))
    db.init_db()
    return db


@pytest.fixture
def scheduler(backend):
    from featcat.server.scheduler import FeatcatScheduler

    settings = load_settings()
    s = FeatcatScheduler(backend=backend, llm=None, settings=settings)
    return s


class TestSchedulerSetup:
    def test_setup_seeds_default_jobs(self, scheduler, backend):
        scheduler.setup_default_jobs()
        schedules = scheduler.get_schedules()
        names = [s["job_name"] for s in schedules]
        assert "monitor_check" in names
        assert "doc_generate" in names
        assert "source_scan" in names
        assert "baseline_refresh" in names

    def test_setup_does_not_duplicate_on_second_call(self, scheduler, backend):
        scheduler.setup_default_jobs()
        scheduler.setup_default_jobs()
        schedules = scheduler.get_schedules()
        assert len(schedules) == 4

    def test_get_schedules_returns_dicts(self, scheduler):
        scheduler.setup_default_jobs()
        schedules = scheduler.get_schedules()
        assert isinstance(schedules[0], dict)
        assert "job_name" in schedules[0]
        assert "cron_expression" in schedules[0]
        assert "enabled" in schedules[0]


class TestSchedulerUpdate:
    def test_update_cron(self, scheduler):
        scheduler.setup_default_jobs()
        scheduler.update_schedule("monitor_check", cron="0 */2 * * *", enabled=None)
        schedules = scheduler.get_schedules()
        mc = next(s for s in schedules if s["job_name"] == "monitor_check")
        assert mc["cron_expression"] == "0 */2 * * *"

    def test_disable_job(self, scheduler):
        scheduler.setup_default_jobs()
        scheduler.update_schedule("monitor_check", cron=None, enabled=False)
        schedules = scheduler.get_schedules()
        mc = next(s for s in schedules if s["job_name"] == "monitor_check")
        assert mc["enabled"] == 0


class TestJobExecution:
    @pytest.mark.asyncio
    async def test_run_job_creates_log(self, scheduler):
        scheduler.setup_default_jobs()
        result = await scheduler.run_job("baseline_refresh", triggered_by="manual")
        assert result["status"] in ("success", "warning")
        assert result["job_name"] == "baseline_refresh"

        logs = scheduler.get_logs(job_name="baseline_refresh")
        assert len(logs) == 1
        assert logs[0]["triggered_by"] == "manual"
        assert logs[0]["status"] in ("success", "warning")
        assert logs[0]["duration_seconds"] >= 0

    @pytest.mark.asyncio
    async def test_run_invalid_job(self, scheduler):
        scheduler.setup_default_jobs()
        result = await scheduler.run_job("nonexistent", triggered_by="manual")
        assert result["status"] == "failed"
        assert "Unknown job" in result["error_message"]


class TestLogRetention:
    @pytest.mark.asyncio
    async def test_purge_old_logs(self, scheduler, backend):
        scheduler.setup_default_jobs()
        # Run a job to create a log
        await scheduler.run_job("baseline_refresh", triggered_by="manual")
        logs = scheduler.get_logs()
        assert len(logs) == 1

        # Artificially age the log
        backend.conn.execute(
            "UPDATE job_logs SET started_at = datetime('now', '-60 days')"
        )
        backend.conn.commit()

        # Run purge (retention is 30 days for baseline_refresh=60, but let's test with a short one)
        backend.conn.execute(
            "UPDATE job_schedules SET max_log_retention_days = 1 WHERE job_name = 'baseline_refresh'"
        )
        backend.conn.commit()

        scheduler.purge_old_logs("baseline_refresh")
        logs = scheduler.get_logs()
        assert len(logs) == 0


class TestJobStats:
    @pytest.mark.asyncio
    async def test_get_stats(self, scheduler):
        scheduler.setup_default_jobs()
        await scheduler.run_job("baseline_refresh", triggered_by="manual")
        stats = scheduler.get_stats()
        assert "jobs" in stats
        assert "baseline_refresh" in stats["jobs"]
        br = stats["jobs"]["baseline_refresh"]
        assert br["total_runs"] == 1
        assert "sparkline" in br
        assert len(br["sparkline"]) == 7
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run --extra dev --extra server pytest tests/test_scheduler.py -v`
Expected: ImportError — `featcat.server.scheduler` does not exist yet

- [ ] **Step 3: Implement FeatcatScheduler**

Create `featcat/server/scheduler.py`:

```python
"""Internal job scheduler for the featcat server."""

from __future__ import annotations

import json
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from ..catalog.local import LocalBackend
    from ..config import Settings

# Default job definitions
DEFAULT_JOBS = [
    {
        "job_name": "monitor_check",
        "description": "Check all features for drift",
        "max_log_retention_days": 30,
    },
    {
        "job_name": "doc_generate",
        "description": "Generate docs for undocumented features",
        "max_log_retention_days": 30,
    },
    {
        "job_name": "source_scan",
        "description": "Re-scan auto_refresh sources",
        "max_log_retention_days": 30,
    },
    {
        "job_name": "baseline_refresh",
        "description": "Refresh monitoring baselines",
        "max_log_retention_days": 60,
    },
]

# Map job_name -> config field name for cron defaults
_CRON_CONFIG_MAP = {
    "monitor_check": "job_monitor_check_cron",
    "doc_generate": "job_doc_generate_cron",
    "source_scan": "job_source_scan_cron",
    "baseline_refresh": "job_baseline_refresh_cron",
}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class FeatcatScheduler:
    """Manages scheduled jobs, execution, and logging."""

    def __init__(self, backend: LocalBackend, llm: Any, settings: Settings) -> None:
        self.backend = backend
        self.llm = llm
        self.settings = settings
        self._apscheduler = None

    # --- Setup ---

    def setup_default_jobs(self) -> None:
        """Seed job_schedules with defaults if table is empty."""
        conn = self.backend.conn
        count = conn.execute("SELECT COUNT(*) FROM job_schedules").fetchone()[0]
        if count > 0:
            return

        for job in DEFAULT_JOBS:
            cron_field = _CRON_CONFIG_MAP[job["job_name"]]
            cron = getattr(self.settings, cron_field)
            conn.execute(
                """INSERT INTO job_schedules
                   (job_name, cron_expression, enabled, description, max_log_retention_days)
                   VALUES (?, ?, 1, ?, ?)""",
                (job["job_name"], cron, job["description"], job["max_log_retention_days"]),
            )
        conn.commit()

    def start(self) -> None:
        """Start the APScheduler with registered jobs."""
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from apscheduler.triggers.cron import CronTrigger

        self._apscheduler = AsyncIOScheduler()

        for schedule in self.get_schedules():
            if not schedule["enabled"]:
                continue
            trigger = CronTrigger.from_crontab(schedule["cron_expression"])
            self._apscheduler.add_job(
                self.run_job,
                trigger=trigger,
                args=[schedule["job_name"]],
                kwargs={"triggered_by": "scheduler"},
                id=schedule["job_name"],
                replace_existing=True,
            )

        self._apscheduler.start()

    def stop(self) -> None:
        """Shut down the APScheduler."""
        if self._apscheduler:
            self._apscheduler.shutdown(wait=False)

    # --- Schedule CRUD ---

    def get_schedules(self) -> list[dict]:
        """Return all job schedules as dicts."""
        rows = self.backend.conn.execute(
            "SELECT * FROM job_schedules ORDER BY job_name"
        ).fetchall()
        return [dict(row) for row in rows]

    def update_schedule(self, job_name: str, cron: str | None, enabled: bool | None) -> None:
        """Update a job's cron expression and/or enabled state."""
        conn = self.backend.conn
        if cron is not None:
            conn.execute(
                "UPDATE job_schedules SET cron_expression = ? WHERE job_name = ?",
                (cron, job_name),
            )
        if enabled is not None:
            conn.execute(
                "UPDATE job_schedules SET enabled = ? WHERE job_name = ?",
                (1 if enabled else 0, job_name),
            )
        conn.commit()

    # --- Job execution ---

    async def run_job(self, job_name: str, triggered_by: str = "scheduler") -> dict:
        """Execute a job and log the result."""
        log_id = str(uuid.uuid4())
        started_at = _utcnow()
        conn = self.backend.conn

        # Insert running log
        conn.execute(
            """INSERT INTO job_logs (id, job_name, status, started_at, triggered_by)
               VALUES (?, ?, 'running', ?, ?)""",
            (log_id, job_name, started_at, triggered_by),
        )
        conn.commit()

        start_time = time.monotonic()
        try:
            result_summary = await self._execute(job_name)
            status = "success"
            error_message = None
        except ValueError as e:
            status = "failed"
            result_summary = {}
            error_message = str(e)
        except Exception as e:
            status = "failed"
            result_summary = {}
            error_message = f"{type(e).__name__}: {e}"

        duration = time.monotonic() - start_time
        finished_at = _utcnow()

        # Update log
        conn.execute(
            """UPDATE job_logs
               SET status = ?, finished_at = ?, duration_seconds = ?,
                   result_summary = ?, error_message = ?
               WHERE id = ?""",
            (status, finished_at, round(duration, 2), json.dumps(result_summary), error_message, log_id),
        )
        # Update last_run_at
        conn.execute(
            "UPDATE job_schedules SET last_run_at = ? WHERE job_name = ?",
            (finished_at, job_name),
        )
        conn.commit()

        # Purge old logs
        self.purge_old_logs(job_name)

        return {
            "id": log_id,
            "job_name": job_name,
            "status": status,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": round(duration, 2),
            "result_summary": result_summary,
            "error_message": error_message,
            "triggered_by": triggered_by,
        }

    async def _execute(self, job_name: str) -> dict:
        """Route to the correct plugin based on job_name."""
        if job_name == "monitor_check":
            return self._run_monitor_check()
        elif job_name == "doc_generate":
            return self._run_doc_generate()
        elif job_name == "source_scan":
            return self._run_source_scan()
        elif job_name == "baseline_refresh":
            return self._run_baseline_refresh()
        else:
            raise ValueError(f"Unknown job: {job_name}")

    def _run_monitor_check(self) -> dict:
        from ..plugins.monitoring import MonitoringPlugin

        plugin = MonitoringPlugin()
        result = plugin.execute(self.backend, self.llm, action="check")
        return result.data

    def _run_doc_generate(self) -> dict:
        if self.llm is None:
            return {"documented": 0, "message": "LLM not available, skipped"}
        from ..plugins.autodoc import AutodocPlugin

        plugin = AutodocPlugin()
        result = plugin.execute(self.backend, self.llm)
        return result.data

    def _run_source_scan(self) -> dict:
        from ..catalog.models import Feature
        from ..catalog.scanner import scan_source

        sources = self.backend.list_sources()
        total_features = 0
        scanned = 0

        for source in sources:
            # Check auto_refresh flag
            row = self.backend.conn.execute(
                "SELECT auto_refresh FROM data_sources WHERE id = ?", (source.id,)
            ).fetchone()
            if not row or not row["auto_refresh"]:
                continue

            columns = scan_source(source.path)
            for col in columns:
                feature_name = f"{source.name}.{col.column_name}"
                feature = Feature(
                    name=feature_name,
                    data_source_id=source.id,
                    column_name=col.column_name,
                    dtype=col.dtype,
                    stats=col.stats,
                )
                self.backend.upsert_feature(feature)
                total_features += 1
            scanned += 1

        return {"sources_scanned": scanned, "features_updated": total_features}

    def _run_baseline_refresh(self) -> dict:
        from ..plugins.monitoring import MonitoringPlugin

        plugin = MonitoringPlugin()
        result = plugin.execute(self.backend, None, action="baseline")
        return result.data

    # --- Logs ---

    def get_logs(
        self,
        job_name: str | None = None,
        status: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[dict]:
        """Query job_logs with optional filters."""
        query = "SELECT * FROM job_logs WHERE 1=1"
        params: list = []
        if job_name:
            query += " AND job_name = ?"
            params.append(job_name)
        if status:
            query += " AND status = ?"
            params.append(status)
        query += " ORDER BY started_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = self.backend.conn.execute(query, params).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            if isinstance(d.get("result_summary"), str):
                d["result_summary"] = json.loads(d["result_summary"])
            result.append(d)
        return result

    def get_log(self, log_id: str) -> dict | None:
        """Get a single job log by ID."""
        row = self.backend.conn.execute(
            "SELECT * FROM job_logs WHERE id = ?", (log_id,)
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        if isinstance(d.get("result_summary"), str):
            d["result_summary"] = json.loads(d["result_summary"])
        return d

    # --- Retention ---

    def purge_old_logs(self, job_name: str) -> int:
        """Delete logs older than max_log_retention_days for a job."""
        row = self.backend.conn.execute(
            "SELECT max_log_retention_days FROM job_schedules WHERE job_name = ?",
            (job_name,),
        ).fetchone()
        if row is None:
            return 0

        max_days = row["max_log_retention_days"]
        cutoff = _utcnow() - timedelta(days=max_days)
        cursor = self.backend.conn.execute(
            "DELETE FROM job_logs WHERE job_name = ? AND started_at < ?",
            (job_name, cutoff),
        )
        self.backend.conn.commit()
        return cursor.rowcount

    # --- Stats ---

    def get_stats(self) -> dict:
        """Return aggregated stats with sparkline data per job."""
        conn = self.backend.conn
        schedules = self.get_schedules()
        result: dict[str, Any] = {"jobs": {}}

        for sched in schedules:
            name = sched["job_name"]

            # Total runs and success rate
            total = conn.execute(
                "SELECT COUNT(*) FROM job_logs WHERE job_name = ? AND status != 'running'",
                (name,),
            ).fetchone()[0]

            successes = conn.execute(
                "SELECT COUNT(*) FROM job_logs WHERE job_name = ? AND status = 'success'",
                (name,),
            ).fetchone()[0]

            avg_dur = conn.execute(
                "SELECT AVG(duration_seconds) FROM job_logs WHERE job_name = ? AND status != 'running'",
                (name,),
            ).fetchone()[0]

            last_row = conn.execute(
                "SELECT status FROM job_logs WHERE job_name = ? AND status != 'running' ORDER BY started_at DESC LIMIT 1",
                (name,),
            ).fetchone()

            # Sparkline: last 7 days
            sparkline = []
            today = _utcnow().date()
            for days_ago in range(6, -1, -1):
                day = today - timedelta(days=days_ago)
                day_start = datetime(day.year, day.month, day.day, tzinfo=timezone.utc)
                day_end = day_start + timedelta(days=1)

                counts = {"date": day.isoformat(), "success": 0, "failed": 0, "warning": 0}
                rows = conn.execute(
                    """SELECT status, COUNT(*) as cnt FROM job_logs
                       WHERE job_name = ? AND started_at >= ? AND started_at < ? AND status != 'running'
                       GROUP BY status""",
                    (name, day_start, day_end),
                ).fetchall()
                for r in rows:
                    if r["status"] in counts:
                        counts[r["status"]] = r["cnt"]
                sparkline.append(counts)

            result["jobs"][name] = {
                "total_runs": total,
                "success_rate": round(successes / total, 2) if total > 0 else 0.0,
                "avg_duration_seconds": round(avg_dur, 2) if avg_dur else 0.0,
                "last_status": last_row["status"] if last_row else None,
                "sparkline": sparkline,
            }

        return result
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run --extra dev --extra server pytest tests/test_scheduler.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add featcat/server/scheduler.py tests/test_scheduler.py
git commit -m "feat: add FeatcatScheduler with job execution and logging"
```

---

### Task 5: Build jobs API routes — tests first

**Files:**
- Create: `tests/test_job_api.py`
- Create: `featcat/server/routes/jobs.py`
- Modify: `featcat/server/deps.py`
- Modify: `featcat/server/app.py`

- [ ] **Step 1: Add get_scheduler to deps.py**

Add to the end of `featcat/server/deps.py`:

```python
def get_scheduler(request: Request):
    """Return the shared scheduler from app state."""
    return request.app.state.scheduler
```

- [ ] **Step 2: Update app.py lifespan to start scheduler**

In `featcat/server/app.py`, replace the lifespan function:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize backend, LLM, and scheduler on startup."""
    settings = load_settings()
    backend = LocalBackend(settings.catalog_db_path)
    backend.init_db()
    app.state.backend = backend
    app.state.settings = settings

    # Try to create LLM (may fail if Ollama not running)
    try:
        from ..llm import create_llm

        llm = create_llm(
            backend=settings.llm_backend,
            model=settings.llm_model,
            base_url=settings.ollama_url if settings.llm_backend == "ollama" else settings.llamacpp_url,
            timeout=settings.llm_timeout,
            max_retries=settings.llm_max_retries,
        )
        app.state.llm = llm
    except Exception:
        app.state.llm = None

    # Start scheduler
    try:
        from .scheduler import FeatcatScheduler

        scheduler = FeatcatScheduler(backend=backend, llm=app.state.llm, settings=settings)
        scheduler.setup_default_jobs()
        scheduler.start()
        app.state.scheduler = scheduler
    except Exception:
        app.state.scheduler = None

    yield

    # Shutdown
    if getattr(app.state, "scheduler", None):
        app.state.scheduler.stop()
    backend.close()
```

- [ ] **Step 3: Register jobs router in build_app()**

In `featcat/server/app.py`, in `build_app()`, add after the existing router imports:

```python
    from .routes.jobs import router as jobs_router
```

And add after the ai_router include:

```python
    app.include_router(jobs_router, prefix="/api/jobs", tags=["jobs"])
```

- [ ] **Step 4: Write job API tests**

Create `tests/test_job_api.py`:

```python
"""Tests for the job API endpoints."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient

from featcat.server.app import build_app


@pytest.fixture
def app(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("FEATCAT_CATALOG_DB_PATH", db_path)
    return build_app()


@pytest.fixture
def client(app):
    with TestClient(app) as c:
        yield c


class TestJobList:
    def test_list_jobs(self, client):
        resp = client.get("/api/jobs")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 4
        names = [j["job_name"] for j in data]
        assert "monitor_check" in names

    def test_list_has_cron(self, client):
        resp = client.get("/api/jobs")
        job = resp.json()[0]
        assert "cron_expression" in job
        assert "enabled" in job


class TestJobRun:
    def test_run_job(self, client):
        resp = client.post("/api/jobs/baseline_refresh/run")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] in ("success", "warning")
        assert data["job_name"] == "baseline_refresh"

    def test_run_unknown_job(self, client):
        resp = client.post("/api/jobs/nonexistent/run")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "failed"


class TestJobLogs:
    def test_logs_empty(self, client):
        resp = client.get("/api/jobs/logs")
        assert resp.status_code == 200
        assert resp.json() == []

    def test_logs_after_run(self, client):
        client.post("/api/jobs/baseline_refresh/run")
        resp = client.get("/api/jobs/logs")
        assert resp.status_code == 200
        logs = resp.json()
        assert len(logs) == 1

    def test_logs_filter_by_job(self, client):
        client.post("/api/jobs/baseline_refresh/run")
        resp = client.get("/api/jobs/logs?job_name=monitor_check")
        assert resp.json() == []
        resp = client.get("/api/jobs/logs?job_name=baseline_refresh")
        assert len(resp.json()) == 1

    def test_log_detail(self, client):
        run_resp = client.post("/api/jobs/baseline_refresh/run")
        log_id = run_resp.json()["id"]
        resp = client.get(f"/api/jobs/logs/{log_id}")
        assert resp.status_code == 200
        assert resp.json()["id"] == log_id


class TestJobUpdate:
    def test_update_cron(self, client):
        resp = client.patch("/api/jobs/monitor_check", json={"cron_expression": "0 */3 * * *"})
        assert resp.status_code == 200

        jobs = client.get("/api/jobs").json()
        mc = next(j for j in jobs if j["job_name"] == "monitor_check")
        assert mc["cron_expression"] == "0 */3 * * *"

    def test_disable_job(self, client):
        resp = client.patch("/api/jobs/monitor_check", json={"enabled": False})
        assert resp.status_code == 200

        jobs = client.get("/api/jobs").json()
        mc = next(j for j in jobs if j["job_name"] == "monitor_check")
        assert mc["enabled"] == 0


class TestJobStats:
    def test_stats_structure(self, client):
        client.post("/api/jobs/baseline_refresh/run")
        resp = client.get("/api/jobs/stats")
        assert resp.status_code == 200
        data = resp.json()
        assert "jobs" in data
        assert "baseline_refresh" in data["jobs"]
        br = data["jobs"]["baseline_refresh"]
        assert br["total_runs"] == 1
        assert "sparkline" in br
        assert len(br["sparkline"]) == 7
```

- [ ] **Step 5: Create the jobs route file**

Create `featcat/server/routes/jobs.py`:

```python
"""Job scheduler API endpoints."""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..deps import get_scheduler

router = APIRouter()


class JobUpdate(BaseModel):
    cron_expression: str | None = None
    enabled: bool | None = None


@router.get("")
def list_jobs(scheduler=Depends(get_scheduler)):
    """List all job schedules."""
    if scheduler is None:
        return []
    return scheduler.get_schedules()


@router.get("/logs")
def list_logs(
    job_name: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
    scheduler=Depends(get_scheduler),
):
    """List recent job execution logs."""
    if scheduler is None:
        return []
    return scheduler.get_logs(job_name=job_name, status=status, limit=limit, offset=offset)


@router.get("/logs/{log_id}")
def get_log(log_id: str, scheduler=Depends(get_scheduler)):
    """Get details of a single job execution."""
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    log = scheduler.get_log(log_id)
    if log is None:
        raise HTTPException(status_code=404, detail=f"Log not found: {log_id}")
    return log


@router.post("/{name}/run")
async def run_job(name: str, scheduler=Depends(get_scheduler)):
    """Manually trigger a job."""
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    result = await scheduler.run_job(name, triggered_by="api")
    return result


@router.patch("/{name}")
def update_job(name: str, body: JobUpdate, scheduler=Depends(get_scheduler)):
    """Update a job's schedule or enabled state."""
    if scheduler is None:
        raise HTTPException(status_code=503, detail="Scheduler not available")
    schedules = scheduler.get_schedules()
    names = [s["job_name"] for s in schedules]
    if name not in names:
        raise HTTPException(status_code=404, detail=f"Job not found: {name}")
    scheduler.update_schedule(name, cron=body.cron_expression, enabled=body.enabled)
    return {"updated": name}


@router.get("/stats")
def job_stats(scheduler=Depends(get_scheduler)):
    """Aggregated job stats with sparkline data."""
    if scheduler is None:
        return {"jobs": {}}
    return scheduler.get_stats()
```

- [ ] **Step 6: Run all tests**

Run: `uv run --extra dev --extra server pytest tests/ -x -q`
Expected: All tests PASS (existing + new scheduler + new API tests)

- [ ] **Step 7: Commit**

```bash
git add featcat/server/routes/jobs.py featcat/server/deps.py featcat/server/app.py tests/test_job_api.py
git commit -m "feat: add /api/jobs endpoints with run, logs, stats, update"
```

---

### Task 6: Add CLI job commands

**Files:**
- Modify: `featcat/cli.py:26-32` (add job_app)

- [ ] **Step 1: Add job_app Typer group and commands**

In `featcat/cli.py`, add after line 26 (`config_app = ...`):

```python
job_app = typer.Typer(help="Scheduled job management")
```

And add after line 32 (`app.add_typer(config_app, name="config")`):

```python
app.add_typer(job_app, name="job")
```

Then add the job commands. Insert them before the `# TUI command` section (before the `serve` command):

```python
# =========================================================================
# Job commands
# =========================================================================


@job_app.command("list")
def job_list() -> None:
    """Show all scheduled jobs."""
    from .catalog.local import LocalBackend

    settings = load_settings()
    db = LocalBackend(settings.catalog_db_path)
    db.init_db()

    rows = db.conn.execute("SELECT * FROM job_schedules ORDER BY job_name").fetchall()
    db.close()

    if not rows:
        console.print("[dim]No scheduled jobs found.[/dim]")
        return

    table = Table(title="Scheduled Jobs")
    table.add_column("Job", style="cyan")
    table.add_column("Schedule")
    table.add_column("Enabled")
    table.add_column("Last Run")
    table.add_column("Description")

    for row in rows:
        enabled = "[green]yes[/green]" if row["enabled"] else "[red]no[/red]"
        last_run = str(row["last_run_at"])[:19] if row["last_run_at"] else "[dim]never[/dim]"
        table.add_row(row["job_name"], row["cron_expression"], enabled, last_run, row["description"])

    console.print(table)


@job_app.command("logs")
def job_logs(
    job: str | None = typer.Option(None, "--job", "-j", help="Filter by job name"),
    limit: int = typer.Option(20, "--limit", "-n", help="Max rows"),
) -> None:
    """Show recent job execution logs."""
    from .catalog.local import LocalBackend

    settings = load_settings()
    db = LocalBackend(settings.catalog_db_path)
    db.init_db()

    query = "SELECT * FROM job_logs WHERE 1=1"
    params: list = []
    if job:
        query += " AND job_name = ?"
        params.append(job)
    query += " ORDER BY started_at DESC LIMIT ?"
    params.append(limit)

    rows = db.conn.execute(query, params).fetchall()
    db.close()

    if not rows:
        console.print("[dim]No job logs found.[/dim]")
        return

    table = Table(title="Job Logs")
    table.add_column("Job", style="cyan")
    table.add_column("Status")
    table.add_column("Started")
    table.add_column("Duration")
    table.add_column("Triggered By")

    for row in rows:
        status = row["status"]
        color = {"success": "green", "failed": "red", "warning": "yellow", "running": "blue"}.get(status, "dim")
        duration = f"{row['duration_seconds']:.1f}s" if row["duration_seconds"] else "-"
        started = str(row["started_at"])[:19] if row["started_at"] else "-"
        table.add_row(row["job_name"], f"[{color}]{status}[/{color}]", started, duration, row["triggered_by"])

    console.print(table)


@job_app.command("run")
def job_run(
    name: str = typer.Argument(help="Job name to run"),
) -> None:
    """Manually trigger a job."""
    import asyncio

    try:
        from .server.scheduler import FeatcatScheduler
    except ImportError:
        console.print("[red]Job runner requires server extras.[/red] Install: pip install 'featcat[server]'")
        raise typer.Exit(1) from None

    from .catalog.local import LocalBackend

    settings = load_settings()
    db = LocalBackend(settings.catalog_db_path)
    db.init_db()

    scheduler = FeatcatScheduler(backend=db, llm=None, settings=settings)
    scheduler.setup_default_jobs()

    with console.status(f"[blue]Running {name}..."):
        result = asyncio.run(scheduler.run_job(name, triggered_by="manual"))

    db.close()

    status = result["status"]
    color = "green" if status == "success" else "red" if status == "failed" else "yellow"
    console.print(f"[{color}]{status}[/{color}] {name} ({result['duration_seconds']:.1f}s)")
    if result.get("error_message"):
        console.print(f"[red]Error:[/red] {result['error_message']}")


@job_app.command("enable")
def job_enable(name: str = typer.Argument(help="Job name")) -> None:
    """Enable a scheduled job."""
    from .catalog.local import LocalBackend

    settings = load_settings()
    db = LocalBackend(settings.catalog_db_path)
    db.init_db()
    db.conn.execute("UPDATE job_schedules SET enabled = 1 WHERE job_name = ?", (name,))
    db.conn.commit()
    db.close()
    console.print(f"[green]Enabled:[/green] {name}")


@job_app.command("disable")
def job_disable(name: str = typer.Argument(help="Job name")) -> None:
    """Disable a scheduled job."""
    from .catalog.local import LocalBackend

    settings = load_settings()
    db = LocalBackend(settings.catalog_db_path)
    db.init_db()
    db.conn.execute("UPDATE job_schedules SET enabled = 0 WHERE job_name = ?", (name,))
    db.conn.commit()
    db.close()
    console.print(f"[yellow]Disabled:[/yellow] {name}")


@job_app.command("schedule")
def job_schedule(
    name: str = typer.Argument(help="Job name"),
    cron: str = typer.Argument(help="Cron expression (e.g. '0 */6 * * *')"),
) -> None:
    """Change a job's cron schedule."""
    from .catalog.local import LocalBackend

    settings = load_settings()
    db = LocalBackend(settings.catalog_db_path)
    db.init_db()
    db.conn.execute("UPDATE job_schedules SET cron_expression = ? WHERE job_name = ?", (cron, name))
    db.conn.commit()
    db.close()
    console.print(f"[green]Updated:[/green] {name} -> {cron}")
```

- [ ] **Step 2: Run all tests**

Run: `uv run --extra dev --extra server pytest tests/ -x -q`
Expected: All tests PASS

- [ ] **Step 3: Run ruff**

Run: `uv run --extra dev ruff check featcat/cli.py featcat/server/`
Expected: No errors

- [ ] **Step 4: Commit**

```bash
git add featcat/cli.py
git commit -m "feat: add featcat job CLI commands (list, logs, run, enable, disable, schedule)"
```

---

### Task 7: Final integration test

**Files:** None new — verify everything works together

- [ ] **Step 1: Run full test suite**

Run: `uv run --extra dev --extra server pytest tests/ -x -q`
Expected: All tests PASS (existing 131 + new scheduler + new API tests)

- [ ] **Step 2: Run ruff on entire codebase**

Run: `uv run --extra dev ruff check featcat/`
Expected: No errors

- [ ] **Step 3: Commit all remaining changes**

If any uncommitted files remain:
```bash
git add -A
git commit -m "feat: complete job scheduler implementation (Phase 6.1)"
```
