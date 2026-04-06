# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
make install          # uv pip install -e ".[dev,tui,s3,server]" + pre-commit hooks
make test             # pytest
make test-cov         # pytest --cov=featcat --cov-report=html
make lint             # ruff check . && ruff format --check .
make format           # ruff check --fix . && ruff format .
make type-check       # mypy featcat/
make check            # lint + type-check + test (use before committing)
make build            # python -m build
make release-check    # clean + check + build + twine check

# Run a single test file or test
pytest tests/test_catalog.py -v
pytest tests/test_scheduler.py::TestJobExecution::test_run_job_creates_log -v

# Run with server extras (needed for server/scheduler tests)
uv run --extra dev --extra server pytest tests/ -x -q
```

## Architecture

featcat is an AI-powered Feature Catalog with four interfaces (CLI, TUI, REST API, Web UI) all sharing the same backend abstraction.

### Core Pattern: CatalogBackend

All data access goes through `CatalogBackend` (abstract class in `featcat/catalog/backend.py`):
- **LocalBackend** (`catalog/local.py`): SQLite implementation, used by default
- **RemoteBackend** (`catalog/remote.py`): HTTP client that calls the REST API
- **Factory** (`catalog/factory.py`): `get_backend()` returns LocalBackend or RemoteBackend based on `FEATCAT_SERVER_URL` config

CLI uses `_get_db()` which calls `get_backend()`. TUI screens import `get_backend` from the factory. Plugins receive the backend as a parameter. **Never instantiate LocalBackend directly** outside of `init` command and server lifespan.

### Plugin System

Plugins in `featcat/plugins/` extend `BasePlugin` (defined in `plugins/base.py`):
- `execute(catalog_db: CatalogBackend, llm: BaseLLM, **kwargs) -> PluginResult`
- Four plugins: `DiscoveryPlugin`, `AutodocPlugin`, `MonitoringPlugin`, `NLQueryPlugin`
- `PluginResult` has `status` ("success"/"error"/"partial"), `data` (dict), `errors` (list)

Plugins are called identically from CLI, TUI, server routes, and the scheduler.

### LLM Layer

`featcat/llm/base.py` defines `BaseLLM` with `generate()`, `stream()`, `generate_json()`, `health_check()`. Implementations: `OllamaLLM`, `LlamaCppLLM`. `CachedLLM` wraps any BaseLLM with SQLite response caching. Factory: `create_llm(backend="ollama"|"llamacpp", **kwargs)`.

`generate_json()` uses `json_mode=True` (Ollama's native JSON output) with retry on parse failure. `_extract_json()` in `llm/base.py` handles extracting JSON from fenced code blocks, bare objects, and arrays.

### Server (`featcat/server/`)

FastAPI app factory in `app.py`. Lifespan initializes LocalBackend, LLM (optional), and FeatcatScheduler. Routes in `routes/` delegate to plugins. Static Web UI files served from `server/static/` via `StaticFiles` mount (must be AFTER all `/api/*` routes).

### Scheduler (`featcat/server/scheduler.py`)

`FeatcatScheduler` uses APScheduler's `AsyncIOScheduler`. Manages `job_schedules` and `job_logs` SQLite tables directly via `backend.conn` (not through CatalogBackend interface — these are server-specific). Four default jobs seeded on first run. Each execution logged with status, duration, and result summary.

### Config Layering

`featcat/config.py` loads settings with priority: overrides > env vars (`FEATCAT_*`) > project `featcat.yaml` > user `~/.config/featcat/config.yaml` > defaults. `get_setting_source(key)` returns where a value came from.

### Vietnamese Bilingual Support

`utils/lang.py` provides `detect_language()` and `localize_system_prompt()`. Plugins auto-detect query language. System prompts stay in English; response language matches the user's input. Feature names and JSON keys always stay in English.

## Key Conventions

- `from __future__ import annotations` at top of every Python file
- Ruff: line-length 120, target py310
- FastAPI `Depends()` in defaults is allowed in `featcat/server/**` (B008 suppressed)
- mypy: `ignore_errors=true` for tui, server, config modules; specific error codes disabled for cli and plugins
- Commit messages: Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`)
- SQLite uses `check_same_thread=False` for FastAPI thread safety
- All prompts in `utils/prompts.py` are optimized for small models (short, explicit JSON instructions)

## Database

SQLite with 6 tables: `data_sources`, `features`, `feature_docs`, `monitoring_baselines`, `job_schedules`, `job_logs`. Schema defined as `SCHEMA_SQL` string in `catalog/local.py`. The `auto_refresh` column on `data_sources` is added via ALTER TABLE in `init_db()` for migration compatibility.

## Docker

`deploy/` contains Dockerfile, docker-compose.yml (featcat + Ollama), setup.sh, and Vietnamese deployment guide.
