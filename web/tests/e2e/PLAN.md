# featcat E2E Test Plan

12 user-facing flows covered by Playwright. All AI/LLM endpoints are mocked
via `page.route()`; DB-only endpoints hit a real FastAPI backend on port 8101
backed by an isolated temp SQLite DB seeded once per run from
`tests/fixtures/*.parquet`.

| # | Spec | Route(s) | Components | Real API | AI Mocked |
|---|------|----------|------------|----------|-----------|
| 1 | dashboard.spec.ts | `/` | Dashboard, MetricCard, DocDebtHeatmap, DataSourceNodes | stats, doc-debt, by-source, usage/top, usage/activity | — |
| 2 | features-list.spec.ts | `/features`, `/features/:name` | Features page, DataTable, feature detail Modal | features, features/by-name (GET/PATCH) | — |
| 3 | search.spec.ts | `/search` | Search page, facets sidebar | search, search/facets | — |
| 4 | feature-selector.spec.ts | `/groups` | FeatureSelector inside AddFeaturesModal | features, groups/{name}/members | ai/discover (suggest) |
| 5 | generate-docs.spec.ts | `/features` | Features page generate-docs Modal, FeatureSelector | features | docs/generate-batch + status polling |
| 6 | export-modal.spec.ts | `/features`, `/groups` | ExportModal, FeatureSelector | export, export/{id}/download | — |
| 7 | groups.spec.ts | `/groups` | Groups page, CreateGroupModal, AddFeaturesModal, group tabs | groups CRUD + members + health + monitoring | — |
| 8 | audit-log.spec.ts | `/audit` | Audit page | versions/recent | — |
| 9 | similarity-graph.spec.ts | `/similarity` | Similarity page (D3 SVG) | features/similarity-graph | — |
| 10 | monitoring.spec.ts | `/monitoring` | Monitoring page, PsiTimeline, DistributionShift | monitor/check, monitor/report, monitor/history, monitor/baseline | — |
| 11 | jobs.spec.ts | `/jobs` | Jobs page, SchedulerOverview, cron edit Modal | scheduler, jobs/stats, jobs/{name}/run | — |
| 12 | chat.spec.ts | `/chat` | Chat page, chatStore, AI elements (reasoning/tool/response) | — | ai/chat (SSE: thinking_start → thinking → thinking_end → tool_call → tool_result → token → done) |

## Skipped flows + reasons

- **Bulk inventory import (`POST /api/scan-bulk` UI)** — backend pytest covers it; UI is exercised indirectly via the seed step.
- **Lineage canvas at >500 nodes** — render fallback only; SVG path is covered by similarity.
- **Notifications panel, Settings cache clear, Help glossary** — trivial; not worth flake risk.
- **`POST /api/ai/discover`, `/ai/ask`, `/ai/ask/stream`** — superseded by agentic `/api/ai/chat` in real product flows.

## Conventions

- `getByRole > getByLabel > getByText > data-testid` (Playwright best practice).
- `data-testid` added only where semantic locators don't disambiguate. Current additions:
  - chart container roots (Similarity SVG, PsiTimeline)
  - chat reasoning/tool blocks
  - export/generate-docs/add-features modal roots when multiple modals can coexist
- No `page.waitForTimeout()`. Use auto-waiting (`expect(...).toBeVisible()`) and locator-based readiness.
- Each spec self-contained; common state (groups, actions, notifications) reset per test via `clearWriteState()`.
- AI endpoints default to `503 mocked` — un-mocked tests fail loudly.
