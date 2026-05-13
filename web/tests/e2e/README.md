# E2E tests

Playwright suite covering the web UI's critical user journeys. Runs against an isolated FastAPI backend (port 8101) and a dedicated Vite dev server (port 5174) so neither the regular `bun run dev` flow nor the dev `catalog.db` is affected.

## Running

```bash
cd web
bun install                    # one-time, picks up @playwright/test
bunx playwright install chromium  # one-time, downloads the browser

bun run test:e2e               # run the full suite headless
bun run test:e2e -- --grep chat  # filter by spec name
bun run test:e2e:ui            # Playwright UI runner (recommended for debugging)
bun run test:e2e:report        # open the last HTML report
bun run test:e2e:codegen       # record a new test by clicking through the app
```

The suite seeds 14 features once per run via `POST /api/scan-bulk` against `tests/fixtures/*.parquet`, so feature data is real (not mocked). Per-test write state (groups, actions, notifications) is reset by the `clearWriteState()` fixture hook.

## Architecture

```
web/playwright.config.ts          ← config + dual webServer (backend + Vite)
web/tests/e2e/
├── *.spec.ts                     ← one per flow
└── fixtures/
    ├── constants.ts              ← ports, paths, URLs
    ├── test.ts                   ← extended `test` with seed + mockAi
    ├── seed.ts                   ← typed factories using the real REST API
    ├── mock-ai.ts                ← page.route() helpers for AI endpoints (default-deny + per-test overrides)
    └── types.ts                  ← typed shapes for assertions
```

Backend boot is wrapped into the Playwright `webServer` command:

```
mkdir -p .tmp && rm -f .tmp/e2e.db* && python -m uvicorn featcat.server:create_app --factory ...
```

Wiping the DB inside the command (rather than as a config-module side effect) ensures the cleanup runs once per run, not once per worker import. The lifespan in `featcat/server/app.py` swallows the LLM-init failure (`FEATCAT_LLAMACPP_URL` is pointed at an unreachable port) so `app.state.llm = None` and AI routes return errors rather than blocking.

## Mocking AI

All AI endpoints (`/api/ai/*`, `/api/docs/generate*`) are mocked by default to return `503` so any test that forgets to set up a mock fails loudly. To override:

```ts
import { test, expect } from './fixtures/test'

test('chat streams', async ({ page, mockAi }) => {
  await mockAi.mockChat([
    { type: 'thinking_start' },
    { type: 'thinking', content: '...' },
    { type: 'thinking_end' },
    { type: 'tool_call', id: 't1', name: 'search', input: { q: 'foo' } },
    { type: 'tool_result', id: 't1', name: 'search', output: { hits: [] } },
    { type: 'token', content: 'Answer here.' },
    { type: 'done' },
  ])
  // ... assertions
})
```

Available helpers:

- `mockAi.mockChat(events)` — SSE stream for `POST /api/ai/chat`. Wire format: one `data: {json}\n\n` frame per event.
- `mockAi.mockSuggestFeatures(specs)` — `/api/ai/discover` for FeatureSelector AI Suggest.
- `mockAi.mockGenerateDocsBatch(jobId)` — initial `POST /api/docs/generate-batch`.
- `mockAi.mockBatchStatus(jobId, payload)` — status polling for a known job_id.
- `mockAi.callCount(urlPattern)` — assert how many times an endpoint was hit.

To add a new mock helper, edit `fixtures/mock-ai.ts` and extend the `AiMockHelpers` interface in the same file.

## Locator conventions

Per Playwright best practice, prefer in this order:

1. `getByRole('heading' | 'button' | 'dialog' | …)`
2. `getByLabel(...)`
3. `getByText(...)` (with `{ exact: true }` when names overlap)
4. `data-testid` (only as a last resort)

Currently no `data-testid` attributes are added in app code. The base `Modal` component carries `role="dialog" aria-modal="true" aria-label={title}` so all modals are reachable by `getByRole('dialog')`.

## Debugging

- `bun run test:e2e:ui` — interactive runner, time-travel debugger, pick locators visually.
- HTML report opens automatically on failure with `trace.zip`, screenshot, and video.
- `bunx playwright show-trace test-results/<name>/trace.zip` for an existing trace.
- Backend logs are piped to Playwright's `stderr`; check the test output for `[WebServer] ...` lines.

## Known limitations

- **Chromium only.** No cross-browser. Adding Firefox/WebKit means another download per machine; revisit when there's a real cross-browser bug.
- **No CI.** Runs only on local pre-PR. CI integration is out of scope; the suite would need a llama.cpp-less seeding path (already true) plus headless display in CI.
- **Real LLM never used.** All AI endpoints are stubbed; the actual Gemma model is too slow on CPU for E2E.
- **Single worker.** `workers: 1`. Going parallel would need per-worker DBs or test isolation per group; current runtime (~40s) doesn't justify the complexity.
- **Backend stderr noise.** A pre-existing SQLAlchemy `InterfaceError` on `action_items` count under StaticPool concurrency surfaces in webServer logs but does not fail tests. Unrelated to this suite.
