# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Build & Test Commands

```bash
make install          # uv pip install -e ".[dev,tui,s3,server]" + pre-commit hooks
make test             # pytest (730+ tests, ~2.5 min full suite)
make test-cov         # pytest --cov=featcat --cov-report=html
make lint             # ruff check . && ruff format --check .
make format           # ruff check --fix . && ruff format .
make type-check       # mypy featcat/ — must stay green; 0 errors enforced
make check            # lint + type-check + test in sequence (use before committing)
make build            # python -m build

# Run a single test file or test
pytest tests/test_catalog.py -v
pytest tests/test_scheduler.py::TestJobExecution::test_run_job_creates_log -v

# Frontend (React + Vite + Tailwind in web/)
cd web && bun install
cd web && bun run build          # tsc + vite build → outputs to featcat/server/static/
cd web && bun run dev            # dev server at :5173 with /api proxy to :8000
cd web && bun run test:e2e       # Playwright suite (12 user journeys, AI mocked)

# Full local dev (LLM + backend + frontend)
./dev.sh              # downloads GGUF model, starts llama.cpp Docker, inits catalog, starts both servers

# Docker (multi-stage: Node builds frontend, Python serves everything)
cd deploy && docker compose build && docker compose up -d

# Demo data
featcat lineage seed tests/fixtures/lineage-demo.json
featcat lineage clear --demo-only --yes

# Demo screenshots (requires server at :8000 with seeded catalog)
cd web && FEATCAT_URL=http://localhost:8000 bun run capture:demo
cd web && FEATCAT_URL=http://localhost:8000 bun run capture:lineage

# Matrix layout regression check (Playwright probe)
cd web && FEATCAT_URL=http://localhost:8000 bun run ../scripts/probe_matrix_widths.ts
```

## Architecture

featcat is an AI-powered Feature Catalog with four interfaces (CLI, TUI, REST API, Web UI) all sharing the same backend abstraction.

### Core Pattern: CatalogBackend

All data access goes through `CatalogBackend` (abstract class in `featcat/catalog/backend.py`):
- **LocalBackend** (`catalog/local.py`): SQLAlchemy-based, runs on SQLite (default) or PostgreSQL
- **RemoteBackend** (`catalog/remote.py`): HTTP client that calls the REST API using query-param endpoints (`/features/by-name?name=...`)
- **Factory** (`catalog/factory.py`): `get_backend()` returns LocalBackend or RemoteBackend based on `FEATCAT_SERVER_URL` config

CLI uses `_get_db()` which calls `get_backend()`. Plugins receive the backend as a parameter. **Never instantiate LocalBackend directly** outside of `init` command and server lifespan.

The base class provides **default empty implementations** for `find_duplicate_pairs`, `full_text_search`, and `get_impact` so RemoteBackend and test stubs satisfy the interface without overriding everything. LocalBackend overrides each with a real SQL implementation.

### Database Backends (SQLite + PostgreSQL)

`featcat/db/connection.py` resolves the backend via `FEATCAT_DB_BACKEND` env var (`sqlite` default, `postgres` for prod). Schema is defined as SQLAlchemy ORM models in `featcat/db/models.py` and created via `Base.metadata.create_all()` in `LocalBackend.init_db()`. SQLite migrations for pre-existing catalogs run as a tuple of idempotent ALTER/CREATE statements wrapped in `contextlib.suppress(OperationalError)`.

Tables include: `data_sources`, `features`, `feature_docs`, `feature_groups`, `feature_group_members`, `feature_lineage`, `feature_versions`, `monitoring_baselines`, `monitoring_checks`, `usage_log`, `scan_logs`, `action_items`, `job_schedules`, `job_logs`. SQLite also gets a `features_fts` FTS5 virtual table + INSERT/UPDATE/DELETE triggers for full-text search (see Search section).

### Plugin System

Plugins in `featcat/plugins/` extend `BasePlugin` (defined in `plugins/base.py`):
- `execute(catalog_db: CatalogBackend, llm: BaseLLM, **kwargs) -> PluginResult`
- Four plugins: `DiscoveryPlugin`, `AutodocPlugin`, `MonitoringPlugin`, `NLQueryPlugin`
- `PluginResult` has `status` ("success"/"error"/"partial"), `data` (dict), `errors` (list)

Plugins are called identically from CLI, TUI, server routes, and the scheduler.

### LLM Layer

`featcat/llm/base.py` defines `BaseLLM` with abstract `generate()`, `stream()`, `health_check()` plus concrete `generate_json()`, `chat()`, and `stream_chat()` (the latter two raise `NotImplementedError` by default so test mocks can subclass without implementing them). Only real implementation: `LlamaCppLLM` (`llm/llamacpp.py`). `CachedLLM` wraps any BaseLLM with SQLite response caching — passes `chat`/`stream_chat` through without caching (stateful calls). Factory: `create_llm(backend="llamacpp", **kwargs)` — accepts `"ollama"` as alias for backward compatibility but always returns `LlamaCppLLM`.

**Thinking model support**: The default model (`gemma-4-E2B-it-Q4_K_M.gguf` served via llama.cpp at `:8080`) returns `<think>...</think>` blocks before the answer. `strip_thinking_tags()` in `llm/base.py` removes these. Applied automatically in `generate()` and `generate_json()`. The SSE streaming endpoint in `routes/ai.py` detects think tags in-flight and emits separate `thinking_start`/`thinking`/`thinking_end` events.

`generate_json()` uses `json_mode=True` with retry on parse failure. `_extract_json()` handles fenced code blocks, bare objects, and arrays.

### AI Agent (`featcat/ai/`)

`CatalogAgent` in `ai/agent.py` implements agentic chat with native tool calling via llama.cpp's `/v1/chat/completions` endpoint. The agent yields SSE events (`thinking`/`tool_call`/`tool_result`/`token`/`done`). Tools are defined in `ai/tools.py` (`CATALOG_TOOLS`: search, feature detail, comparisons, drift reports, similar/duplicate features, etc.). `ai/executor.py` runs tool calls against the catalog backend. Max 2 tool rounds per query (`MAX_TOOL_ROUNDS`) with duplicate call detection.

**Intent classifier** (`ai/intent.py`): rule-based label routing filters the 14-tool CATALOG_TOOLS down to a per-query subset (~830 token savings per matched intent). Set `FEATCAT_INTENT_FILTER=off` to bypass. Fallback set is search-oriented when no rule matches.

**Session memory** (`ai/session.py`): `ChatSession.get_history()` returns the last 6 user/assistant turns. `ChatSession.get_context_summary()` extracts feature-name entities (`\w+\.\w+` pattern) from messages **older than** that window and prepends them as a second system message labeled "Bối cảnh trước đó" (vi) or "Earlier context" (en). Capped at 8 entities. Sessions are in-memory, per-process, 30-min TTL, max 50 sessions.

### Server (`featcat/server/`)

FastAPI app factory in `app.py` (`build_app()`). Called via `create_app()` in `__init__.py`. Lifespan initializes LocalBackend, LLM (optional), and FeatcatScheduler. `STATIC_DIR` is a module-level constant pointing to `Path(__file__).parent / "static"`.

**Multi-worker**: `featcat serve` runs uvicorn with 4 workers (factory pattern: `"featcat.server:create_app"`). All LLM-calling routes are `async` and use `run_in_threadpool()` with `asyncio.wait_for` timeouts.

**Timeouts**:
- `/discover` and `/ask`: `LLM_TIMEOUT = 180s` — wraps the threadpool call.
- `/chat` (SSE): `CHAT_TIMEOUT = 90s` configurable via `FEATCAT_CHAT_TIMEOUT_SECONDS`. Per-iteration `wait_for` on the async generator with a shrinking deadline (Python 3.10 lacks `asyncio.timeout()`). On timeout emits `{"type":"error","content":"Phản hồi quá lâu..."}` and skips the assistant-turn session write so a half-streamed answer can't poison future context.

**Route order matters**: API routers (`/api/*`) → `/assets` StaticFiles mount → `GET /` root → `GET /{full_path:path}` SPA catch-all. The catch-all returns `index.html` for React Router client-side routing.

**Feature names contain dots** (e.g. `device_performance.cpu_usage`). Routes that look up features/docs by name use query parameters (`/features/by-name?name=...`, `/docs/by-name?name=...`) instead of path parameters to avoid FastAPI's dot-as-extension handling.

### Search & FTS5

`LocalBackend.search_features` delegates to `full_text_search`, which on SQLite uses an FTS5 contentful virtual table (`features_fts`) with `unicode61 remove_diacritics=2` tokenizer over `name`, `description`, `tags`, `column_name`. `_build_fts5_query` quotes each token, joins with `OR`, plus a phrase boost so verbatim hits rank highest via BM25. On FTS5 parse failure (malformed input, stale DB without the virtual table) it falls back to the legacy keyword scorer in `_fts_sqlite_legacy`. The PostgreSQL branch (`_fts_postgres`) uses `tsvector + plainto_tsquery` and is unaffected by SQLite changes.

The virtual table is populated and kept in sync via AFTER INSERT/UPDATE/DELETE triggers added in `init_db`'s `legacy_alters` tuple. Tags (JSON string column) tokenize naturally on punctuation.

### Lineage

`featcat/lineage/sql_detect.py` parses SQL definitions to extract parent/child feature relationships. `feature_lineage` table stores edges with `detected_method` ∈ {`manual`, `sql_parse`, `imported`, `demo`}. The `demo` marker plus `tag='demo'` on features lets `featcat lineage clear --demo-only` remove demo fixtures without touching real data. Demo fixture: `tests/fixtures/lineage-demo.json` (3 sources, 15 features, 13 edges covering the four common derivation patterns).

### Web UI (`web/`)

React 19 + TypeScript + Vite + Tailwind CSS. Vite build outputs to `featcat/server/static/`. In Docker, the Dockerfile uses an editable pip install (`-e`) so `Path(__file__)` resolves to `/app/featcat/server/` where the built static files are copied.

Key patterns:
- `api.ts`: Fetch wrapper with 10s client-side cache for GETs, `invalidateCache()` after mutations
- `stores/chatStore.ts`: Module-level store (not React state) for chat messages — persists across tab switches via `useSyncExternalStore`
- `hooks/useSSE.ts`: EventSource hook for streaming chat (but Chat page uses direct EventSource for message mutation)
- Dark/light theme: Tailwind `class` strategy, toggled via `document.documentElement.classList`, persisted to localStorage
- **Page testids**: Every top-level page has a `data-testid` (`chat-messages`, `stats-cards`, `features-list`, `group-row`, `group-detail`, `lineage-graph`, `similarity-matrix`, `audit-page`) anchoring Playwright captures and E2E tests
- **Matrix layout invariant**: `MatrixGrid.tsx` uses `[table-layout:fixed]` + `<colgroup>` + `w-max` to lock cell widths at 40px. Without `w-max` the browser proportionally scales colgroup widths to fit the parent — `scripts/probe_matrix_widths.ts` is the regression check

### Scheduler (`featcat/server/scheduler.py`)

`FeatcatScheduler` uses APScheduler's `AsyncIOScheduler`. Manages `job_schedules` and `job_logs` SQLite tables directly via `backend.conn` (not through CatalogBackend interface — these are server-specific). Four default jobs seeded on first run.

### Config Layering

`featcat/config.py` loads settings with priority: overrides > env vars (`FEATCAT_*`) > project `featcat.yaml` > user `~/.config/featcat/config.yaml` > defaults.

Key env vars: `FEATCAT_DB_BACKEND` (sqlite/postgres), `FEATCAT_SERVER_URL` (switches to RemoteBackend), `FEATCAT_CHAT_TIMEOUT_SECONDS` (default 90), `FEATCAT_INTENT_FILTER` (on/off).

### Vietnamese Bilingual Support

`utils/lang.py` provides `detect_language()` and `localize_system_prompt()`. Plugins auto-detect query language. System prompts stay in English; response language matches the user's input. Feature names and JSON keys always stay in English. FTS5 search uses `remove_diacritics=2` so `luot truy cap` matches `lượt truy cập`.

## Key Conventions

- `from __future__ import annotations` at top of every Python file
- Ruff: line-length 120, target py310
- FastAPI `Depends()` in defaults is allowed in `featcat/server/**` (B008 suppressed)
- mypy: 0 errors enforced on the whole `featcat/` package; if adding a method only used through the abstract base, declare it on the base (with a default-raise or default-empty body) rather than annotating callers
- Commit messages: Conventional Commits (`feat:`, `fix:`, `docs:`, `chore:`, `refactor:`, `test:`)
- SQLite uses `check_same_thread=False` for FastAPI thread safety
- All prompts in `utils/prompts.py` are optimized for small models (short, explicit JSON instructions)
- Server routes that call LLM must be `async` with `run_in_threadpool` + timeout
- `_row_to_feature()` in `catalog/local.py` handles None values and filters extra columns from ALTER TABLE migrations

## Path-Scoped Rules (`.claude/rules/`)

Two scoped rule files apply on top of this CLAUDE.md:

- `.claude/rules/api.md` (active in `featcat/server/**`): no raw SQL in routes, typed Pydantic responses, async + `run_in_threadpool` + `wait_for`, query params for feature-name lookups, scheduler tables direct via `backend.conn`.
- `.claude/rules/frontend.md` (active in `web/**`): Tailwind only, all API calls through `web/src/api.ts`, no `any`, dark/light via Tailwind class strategy, chat state in `stores/chatStore.ts`, bun as package manager.

## Shared UI Components

### FeatureSelector — web/src/components/FeatureSelector.tsx
Reusable feature picker. Use for ANY UI that lets users pick features.
- Props: features (FeatureItem[]), selected (Set<string>), onChange, groupName?, showAISuggest?
- Built-in: search, shift+click range, select-all-by-source, show-selected filter, AI suggest
- Helper: `toFeatureItems(rawApiData)` converts API response to FeatureItem[]
- DO NOT build a new feature list/picker — always use this component

Existing usages: Groups page (add features modal), Features page (generate docs modal), ExportModal (feature checklist).

## Internal Docs (`audits/`)

`audits/*.md` contains design and verification docs that explain why specific architectural choices were made. They are not generated; treat them as authoritative for "why is this code shaped this way":
- `ai-chat-mvp-failure-analysis-2026-05-12.md` — diagnosis of MVP-prompt failures + fix priorities
- `p0-3-verification-2026-05-13.md` — intent classifier + tool-subset measured numbers
- `post-deep-fixes-2026-05-13.md` — server timeout, conversation memory, FTS5 rationale

## Docker

`deploy/` contains Dockerfile (multi-stage: `node:20-slim` builds React frontend, `python:3.12-slim` serves everything), `docker-compose.yml` (featcat + llama.cpp). Uses editable install (`uv pip install -e`) so static files resolve correctly at runtime.
