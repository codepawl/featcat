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

# Run a single test file or test
pytest tests/test_catalog.py -v
pytest tests/test_scheduler.py::TestJobExecution::test_run_job_creates_log -v

# Frontend (React + Vite + Tailwind in web/)
cd web && npm install
cd web && npm run build          # tsc + vite build → outputs to featcat/server/static/
cd web && npm run dev            # dev server at :5173 with /api proxy to :8000

# Docker (multi-stage: Node builds frontend, Python serves everything)
cd deploy && docker compose build && docker compose up -d
```

## Architecture

featcat is an AI-powered Feature Catalog with four interfaces (CLI, TUI, REST API, Web UI) all sharing the same backend abstraction.

### Core Pattern: CatalogBackend

All data access goes through `CatalogBackend` (abstract class in `featcat/catalog/backend.py`):
- **LocalBackend** (`catalog/local.py`): SQLite implementation, used by default
- **RemoteBackend** (`catalog/remote.py`): HTTP client that calls the REST API using query-param endpoints (`/features/by-name?name=...`)
- **Factory** (`catalog/factory.py`): `get_backend()` returns LocalBackend or RemoteBackend based on `FEATCAT_SERVER_URL` config

CLI uses `_get_db()` which calls `get_backend()`. Plugins receive the backend as a parameter. **Never instantiate LocalBackend directly** outside of `init` command and server lifespan.

### Plugin System

Plugins in `featcat/plugins/` extend `BasePlugin` (defined in `plugins/base.py`):
- `execute(catalog_db: CatalogBackend, llm: BaseLLM, **kwargs) -> PluginResult`
- Four plugins: `DiscoveryPlugin`, `AutodocPlugin`, `MonitoringPlugin`, `NLQueryPlugin`
- `PluginResult` has `status` ("success"/"error"/"partial"), `data` (dict), `errors` (list)

Plugins are called identically from CLI, TUI, server routes, and the scheduler.

### LLM Layer

`featcat/llm/base.py` defines `BaseLLM` with `generate()`, `stream()`, `generate_json()`, `health_check()`. Implementations: `OllamaLLM`, `LlamaCppLLM`. `CachedLLM` wraps any BaseLLM with SQLite response caching. Factory: `create_llm(backend="ollama"|"llamacpp", **kwargs)`.

**Thinking model support**: The default model `qwen3.5:0.8b` returns `<think>...</think>` blocks before the answer. `strip_thinking_tags()` in `llm/base.py` removes these. Applied automatically in `generate()` (OllamaLLM/LlamaCppLLM) and `generate_json()`. The SSE streaming endpoint in `routes/ai.py` detects think tags in-flight and emits separate `thinking_start`/`thinking`/`thinking_end` events.

`generate_json()` uses `json_mode=True` with retry on parse failure. `_extract_json()` handles fenced code blocks, bare objects, and arrays.

### Server (`featcat/server/`)

FastAPI app factory in `app.py` (`build_app()`). Called via `create_app()` in `__init__.py`. Lifespan initializes LocalBackend, LLM (optional), and FeatcatScheduler. `STATIC_DIR` is a module-level constant pointing to `Path(__file__).parent / "static"`.

**Multi-worker**: `featcat serve` runs uvicorn with 4 workers (factory pattern: `"featcat.server:create_app"`). All LLM-calling routes are `async` and use `run_in_threadpool()` with 3-minute `asyncio.wait_for` timeouts so blocking LLM inference doesn't starve the event loop.

**Route order matters**: API routers (`/api/*`) → `/assets` StaticFiles mount → `GET /` root → `GET /{full_path:path}` SPA catch-all. The catch-all returns `index.html` for React Router client-side routing.

**Feature names contain dots** (e.g. `device_performance.cpu_usage`). Routes that look up features/docs by name use query parameters (`/features/by-name?name=...`, `/docs/by-name?name=...`) instead of path parameters to avoid FastAPI's dot-as-extension handling.

### Web UI (`web/`)

React 19 + TypeScript + Vite + Tailwind CSS. Vite build outputs to `featcat/server/static/`. In Docker, the Dockerfile uses an editable pip install (`-e`) so `Path(__file__)` resolves to `/app/featcat/server/` where the built static files are copied.

Key patterns:
- `api.ts`: Fetch wrapper with 10s client-side cache for GETs, `invalidateCache()` after mutations
- `stores/chatStore.ts`: Module-level store (not React state) for chat messages — persists across tab switches via `useSyncExternalStore`
- `hooks/useSSE.ts`: EventSource hook for streaming chat (but Chat page uses direct EventSource for message mutation)
- Dark/light theme: Tailwind `class` strategy, toggled via `document.documentElement.classList`, persisted to localStorage

### Scheduler (`featcat/server/scheduler.py`)

`FeatcatScheduler` uses APScheduler's `AsyncIOScheduler`. Manages `job_schedules` and `job_logs` SQLite tables directly via `backend.conn` (not through CatalogBackend interface — these are server-specific). Four default jobs seeded on first run.

### Config Layering

`featcat/config.py` loads settings with priority: overrides > env vars (`FEATCAT_*`) > project `featcat.yaml` > user `~/.config/featcat/config.yaml` > defaults.

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
- Server routes that call LLM must be `async` with `run_in_threadpool` + timeout
- `_row_to_feature()` in `catalog/local.py` handles None values and filters extra columns from ALTER TABLE migrations

## Database

SQLite with 6 tables: `data_sources`, `features`, `feature_docs`, `monitoring_baselines`, `job_schedules`, `job_logs`. Schema defined as `SCHEMA_SQL` string in `catalog/local.py`. The `auto_refresh` column on `data_sources` is added via ALTER TABLE in `init_db()` for migration compatibility.

## Docker

`deploy/` contains Dockerfile (multi-stage: `node:20-slim` builds React frontend, `python:3.12-slim` serves everything), `docker-compose.yml` (featcat + Ollama). Uses editable install (`uv pip install -e`) so static files resolve correctly at runtime.
