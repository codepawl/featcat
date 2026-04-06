# featcat Web UI — Design Spec

**Date:** 2026-04-06
**Scope:** Phase 6.2–6.8 — Web dashboard for the featcat REST API
**Status:** Approved

## Purpose

Build a Web UI dashboard for featcat that talks to the same FastAPI REST API used by CLI/TUI. Single deployment: `featcat serve` hosts both API (`/api/*`) and static Web UI (`/*`).

## Architecture

- **Frontend:** Vanilla HTML + JS + CSS. No framework, no build step, no Node.js.
- **Charts:** Chart.js loaded via CDN (`cdnjs.cloudflare.com`)
- **Streaming:** SSE via `sse-starlette` (already installed) for AI chat
- **Serving:** `FastAPI.mount("/", StaticFiles(..., html=True))` — MUST be after all `/api/*` routes
- **Design:** Clean flat UI, teal accent `#1D9E75`, dark mode via `prefers-color-scheme`, responsive

## File Structure

```
featcat/server/static/
├── index.html           # Dashboard
├── features.html        # Feature browser
├── monitoring.html      # Monitoring view
├── jobs.html            # Job scheduler
├── chat.html            # AI chat
├── css/
│   └── app.css          # Shared styles, CSS variables, dark mode, responsive
└── js/
    ├── api.js           # Shared fetch wrapper for /api/*
    ├── dashboard.js     # Dashboard page logic
    ├── features.js      # Feature browser logic
    ├── monitoring.js    # Monitoring page logic
    ├── jobs.js          # Jobs page logic
    └── chat.js          # AI chat with SSE streaming
```

## Server Changes

### Static file mount in `app.py`

Add at the END of `build_app()`, after all router registrations:

```python
from pathlib import Path
from fastapi.staticfiles import StaticFiles

static_dir = Path(__file__).parent / "static"
if static_dir.is_dir():
    app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
```

The `html=True` flag serves `index.html` for `/`, `features.html` for `/features`, etc.

### SSE streaming endpoint

Add to `featcat/server/routes/ai.py`:

```python
@router.get("/ask/stream")
async def stream_ask(query: str, db=Depends(get_db), llm=Depends(get_llm)):
    """Streaming NL query via Server-Sent Events."""
```

Uses `sse-starlette`'s `EventSourceResponse`. Emits `{"type": "token", "content": "..."}` events, then `{"type": "done", "data": {...}}` with the full result.

## Shared Components

### CSS Design System (`app.css`)

**CSS Variables (light mode):**
```
--bg: #ffffff
--bg-surface: #f8f9fa
--bg-sidebar: #1a1a2e
--text: #1a1a2e
--text-secondary: #6c757d
--accent: #1D9E75
--accent-hover: #178a64
--border: #e9ecef
--success: #1D9E75
--warning: #f0ad4e
--danger: #dc3545
--info: #17a2b8
```

**Dark mode** via `@media (prefers-color-scheme: dark)`:
```
--bg: #0d1117
--bg-surface: #161b22
--text: #e6edf3
--border: #30363d
```

**Components:** Metric cards, data tables (sortable), status badges, pill tags, modals, skeleton loaders, toast notifications.

**Responsive breakpoints:**
- Desktop 1200px+: sidebar + full layout
- Tablet 768–1199px: collapsible sidebar, stacked grids
- Mobile <768px: hidden sidebar (hamburger)

### API Client (`api.js`)

```javascript
const featcat = {
    health: () => api('/health'),
    stats: () => api('/stats'),
    sources: { list, add },
    features: { list, get, update, search },
    docs: { stats, generate, get },
    monitor: { check, baseline, report },
    jobs: { list, logs, run, update, stats },
    ai: { discover, ask, stream },
};
```

Each method returns a Promise. `api.stream(query, onToken, onDone)` uses EventSource for SSE.

### Shared Shell (every HTML page)

Every page includes:
1. `<nav>` sidebar (220px) with logo, nav links, server/LLM status indicators
2. `<main>` content area
3. `<link>` to `css/app.css`
4. `<script>` for `js/api.js`
5. `<script>` for the page-specific JS

Active nav link highlighted via CSS class. Status dots poll `/api/health` on load.

## Page Specifications

### Dashboard (`index.html` + `dashboard.js`)

**Data:** `GET /api/stats`, `GET /api/monitor/check`, `GET /api/jobs/stats`, `GET /api/jobs/logs?limit=10`

**Layout (top to bottom):**

1. **Metric cards row (4 cards):**
   - Total features (count)
   - Doc coverage (% with progress bar)
   - Drift alerts (count, color-coded: green=0, amber=warnings, red=critical)
   - Data sources (count)

2. **Two-column row:**
   - Left: Recent drift alerts table (severity badge, feature name, PSI, max 5 rows, "View all" link to monitoring)
   - Right: Recent activity from job logs (status icon, description, time ago, max 5 rows)

3. **Scheduled jobs table:**
   - Columns: job name, schedule, runs/week, sparkline (7 colored bars from stats API), status badge
   - "Run Now" button per job (calls `POST /api/jobs/{name}/run`)

**Auto-refresh:** polls `/api/stats` every 30 seconds. Updates metric cards and tables without full page reload. Shows "Last updated: X seconds ago" in header.

**Loading:** Skeleton placeholders while API loads. Error state: "Cannot connect to server" with retry button.

### Feature Browser (`features.html` + `features.js`)

**Data:** `GET /api/features`, `GET /api/features/{name}`, `PATCH /api/features/{name}`, `POST /api/docs/generate`

**Layout:**

1. **Top bar:** Search input (300ms debounce), source dropdown filter, "Add" button (opens modal)
2. **Results count:** "Showing 42 of 147 features"
3. **Feature table:**
   - Columns: name, source, dtype, tags (pills), doc status (check/cross), owner
   - Sortable by clicking headers
   - 25 rows per page with pagination
   - Click row expands detail panel below

4. **Detail panel (when row selected):**
   - Feature metadata: name, dtype, source, stats (mean, std, min, max, null_ratio)
   - Documentation: short + long description
   - Tags (displayed as pills)
   - Actions: [Generate Doc], [Check Drift]

5. **Add modal:** Path input, name, owner, tags. Calls `POST /api/sources` to register, then `POST /api/sources/{name}/scan` to discover features (both endpoints exist).

### Monitoring (`monitoring.html` + `monitoring.js`)

**Data:** `GET /api/monitor/check`, `POST /api/monitor/baseline`, `GET /api/monitor/report`

**Layout:**

1. **Summary cards (3):** Healthy (green), Warning (amber), Critical (red) — count + percentage. Plus "Run Check Now" button and "Last check" timestamp.

2. **Monitoring table:**
   - Columns: feature name, severity (color badge), issue type, PSI score, delta from baseline
   - Sorted by severity (critical first)
   - Click row expands: AI analysis (if available), baseline vs current stats comparison

3. **Drift trend chart (Chart.js, full width):**
   - Stacked area chart: warnings (amber) + critical (red)
   - Toggle: 7 days / 30 days
   - X-axis: dates, Y-axis: count

4. **Actions:** "Refresh Baseline" (with confirmation modal), "Export Report" (downloads markdown)

**Auto-refresh:** polls every 60 seconds when page is visible.

### Jobs (`jobs.html` + `jobs.js`)

**Data:** `GET /api/jobs`, `GET /api/jobs/logs`, `POST /api/jobs/{name}/run`, `PATCH /api/jobs/{name}`, `GET /api/jobs/stats`

**Layout:**

1. **Job cards (one per scheduled job):**
   - Job name + description
   - Schedule (human-readable: "Every 6 hours")
   - Next run countdown
   - Toggle switch (enabled/disabled, calls PATCH)
   - "Run Now" button

2. **Execution history table:**
   - Columns: job name, status (badge), started at, duration, result summary, triggered by
   - Filter by job name, status
   - Click row expands: full result_summary JSON, error_message if failed
   - 50 per page

3. **Execution stats (Chart.js bar chart):**
   - Runs per day, last 14 days
   - Stacked bars: green=success, amber=warning, red=failed
   - Grouped by job name

4. **Schedule editor modal:** Cron expression input, human-readable preview, preset buttons ("Every hour", "Every 6 hours", "Daily", "Weekly").

### AI Chat (`chat.html` + `chat.js`)

**Data:** `POST /api/ai/ask`, `GET /api/ai/ask/stream?query=...`, `POST /api/ai/discover`

**Layout (full-height chat):**

1. **Message area (scrollable):**
   - User messages: right-aligned, teal background
   - AI messages: left-aligned, surface background
   - AI responses can contain formatted tables, relevance scores
   - Streaming: tokens appear as they arrive via SSE

2. **Input area (fixed bottom):**
   - Shortcut buttons above input: [Discover Features], [Check Drift], [Catalog Stats]
   - Text input + Send button
   - Shortcuts prefill the input with context

3. **SSE streaming implementation:**
   - Client creates `EventSource` to `/api/ai/ask/stream?query=...`
   - Listens for `message` events with `{type: "token", content: "..."}` and `{type: "done"}`
   - Auto-scrolls on new content

**Bilingual:** Detects Vietnamese input, AI responds in Vietnamese. Feature names always English.

## Dark Mode

- Pure CSS via `@media (prefers-color-scheme: dark)` — no JS toggle needed
- All colors use CSS variables
- Charts: Chart.js `color` and `borderColor` read from CSS variables

## Responsive Design

- **Desktop (1200px+):** Full sidebar + multi-column layouts
- **Tablet (768–1199px):** Collapsible sidebar, 2-column becomes 1-column
- **Mobile (<768px):** Hidden sidebar with hamburger menu, stacked cards

## Files Changed/Created

| File | Action |
|------|--------|
| `featcat/server/static/` (entire directory) | CREATE — all HTML, CSS, JS files |
| `featcat/server/app.py` | MODIFY — add StaticFiles mount at end of build_app() |
| `featcat/server/routes/ai.py` | MODIFY — add GET /api/ai/ask/stream SSE endpoint |

## Testing

- **Manual testing:** Open browser to `http://localhost:8000`, verify each page loads and fetches data
- **API tests:** Existing tests cover all API endpoints; Web UI is a consumer only
- **SSE endpoint:** Add test for `/api/ai/ask/stream` response format

## Verification

1. `featcat serve` starts and serves both API and Web UI
2. `http://localhost:8000/` shows dashboard with live data
3. All 5 pages render correctly
4. Dark mode toggles with system preference
5. Auto-refresh works on dashboard and monitoring
6. Chat streaming shows tokens incrementally
7. Responsive layout works at 768px and 1200px breakpoints
