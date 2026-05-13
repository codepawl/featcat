# Loading-states audit — featcat frontend

**Date**: 2026-05-12
**Scope**: `web/src/` only. Audit-only — no code changed.
**Method**: Three parallel passes — every `pages/*.tsx`, every chart in `components/charts/`, and cross-cutting orchestration patterns (single source of truth, parallel vs sequential, refresh semantics, optimistic mutations).

---

## Section 1 — Current state inventory

### 1a. Pages

| Page / Section | File:line | Loading state | Loading UI | Matches shape? | Layout shift? | Cascading? | Refresh treatment | Notes |
|---|---|---|---|---|---|---|---|---|
| **Dashboard** | `Dashboard.tsx:51` | `loading` | skeleton-matched (4× `h-20` for cards, plus per-section) | Yes | No | **Yes** — DataSourceNodes, DocDebtHeatmap, DriftRateTrend each fetch on mount | Refresh keeps page interactive | Best-in-class for the upper section. |
| **Features list** | `Features.tsx:86` | `loading` | **none** | — | **Yes** (table jumps in) | No | Refresh blanks rows | Missing skeleton — biggest gap on the page. |
| **Features detail modal** | `Features.tsx:1629` | `loadingGroups` etc. | disabled-button only | — | — | Yes (docs / monitoring / definition sub-fetches) | — | No modal-level skeleton; sections pop in independently. |
| **Groups list** | `Groups.tsx:46` | `loading` | skeleton-generic (`h-32` box) | No | No | **Yes** — detail load + per-tab loads inside | Refresh re-skeletons list | List skeleton doesn't reflect row shape. |
| **Groups detail (each tab)** | `Groups.tsx:352, 475, 579` | each tab has own `loading` | skeleton-generic (`h-32`) | No | Approximately | **Yes** — DistributionShift, GroupDriftHeatmap each fetch | Tab switch re-skeletons | Switching tabs flashes a generic box, then content. |
| **Sources list** | `Sources.tsx:63` | `loading` | skeleton-generic (`h-32`) | No | No | Yes — detail loads separately | **Good**: refresh preserves data | Row list doesn't preview row shape. |
| **Sources detail** | `Sources.tsx:71` | `detailLoading` | skeleton-matched (h-8, h-20, h-32 stacked) | Approximately | No | No | Detail re-skeletons on source switch | Closest to ideal stacked-skeleton pattern. |
| **Similarity > Graph** | `similarity/SimilarityGraph.tsx:67` | `loading` | spinner inside Suspense `h-64` skeleton | — | — | No | Suspense fallback only | Graph itself shows no internal scaffolding once mounted. |
| **Similarity > Matrix** | `similarity/SimilarityMatrix.tsx:42,49` | `loadingFeatures`, `matrixLoading` | skeleton-generic | No | No | Yes — matrix re-fetches on threshold change | Matrix re-fetches every threshold change (400ms debounced) | Two independent loading flags. |
| **Monitoring** | `Monitoring.tsx:23` | `loading` | skeleton-matched (3× `h-20` + `h-32` table) | Yes | No | **Yes** — `FeatureDetail` panel async-fetches metrics+baseline | **Bad**: `setData(null)` on error → blank page | Detail panel cascades MultiMetricTimeline + DistributionShift. |
| **Lineage** | `Lineage.tsx:80` | `loading` | skeleton-generic (`h-64`) | No | No | No | Full skeleton on refresh | Graph layout doesn't preview during load. |
| **Audit** | `Audit.tsx:23` | `loading` | skeleton-generic (`h-48`) | No | No | No | **Bad**: auto-refresh every 60s re-skeletons | User sees the table disappear every minute. |
| **Jobs** | `Jobs.tsx:26` | `loading` | **none** in table; SchedulerOverview self-loads | — | **Yes** (table renders empty) | Yes (SchedulerOverview cards) | Refresh shows nothing | Worst loading-state coverage of any page. |
| **Actions** | `Actions.tsx:27` | `loading` | **none** | — | Yes | No | Filter changes silently swap content | Missing skeleton entirely. |
| **Search** | `Search.tsx:54` | `loading` | **none** for results & facets | — | Yes | No | Search-on-type renders empty during fetch | Missing skeleton; user types and sees nothing. |
| **Chat** | `Chat.tsx:129` | `busy` | text + spinner inside `ChatMessage` | — | — | Yes (tool calls stream in) | N/A (streaming) | Streaming patterns out of scope per spec. |
| **Help** | `Help.tsx:19` | via `useGlossary()` | skeleton-generic (`h-64`) | No | No | No | Refresh re-skeletons | Glossary doc preview not previewed. |
| **Settings** | `Settings.tsx:119` (`LLMCacheCard`) | `loading` | spinner on refresh button | — | — | No | **Good**: refresh button shows spinner, content stays | Best refresh treatment in the app. |

### 1b. Charts + heavy components

| Component | File:line | Loading state | Loading UI | Matches shape? | Layout shift? | Self-fetches? | Empty vs loading? | Notes |
|---|---|---|---|---|---|---|---|---|
| **MultiMetricTimeline** | `charts/MultiMetricTimeline.tsx:99-124` | `loading` prop | `animate-shimmer h-44` | No (generic) | Yes (44→180) | No | Yes (renders `not_enough_history` distinctly) | No axis bones. |
| **DriftRateTrend** | `charts/DriftRateTrend.tsx:49-64` | internal `useState` | `<Skeleton h-40 />` | No | Yes (40→180) | **Yes** — `api.monitor.driftRate` on mount | Yes | Cascading inside Dashboard's already-loading state. |
| **PsiTimeline** | `charts/PsiTimeline.tsx:34-47` | `loading` prop | `animate-shimmer h-32` | No | Yes (32→140) | No | Yes | No axis bones. |
| **UsageBubbleChart** | `charts/UsageBubbleChart.tsx:51-75` | `loading` prop | `<Skeleton h-64 />` | No | Yes (64→300) | No | Yes (zero-usage vs no-data distinct) | Big height jump. |
| **GroupDriftHeatmap** | `charts/GroupDriftHeatmap.tsx:28-50` | internal `useState` | `<Skeleton h-32 />` | No | Yes (32→full table) | **Yes** — `api.groups.driftMatrix` on `groupName`/`days` change | Yes | Cascading. |
| **DocCoverageDonut** | `charts/DocCoverageDonut.tsx:20-31` | `loading` prop | `<Skeleton h-24 />` | No (box, not donut) | Yes | No | Yes | Card frame preserved. |
| **DataSourceNodes** | `charts/DataSourceNodes.tsx:29-55` | `loading` prop | 3× `<Skeleton h-36 />` in a grid | **Yes** (grid layout) | Minor | No | Yes | Best chart-skeleton example. |
| **DocDebtHeatmap** | `charts/DocDebtHeatmap.tsx:26-39` | `loading` prop | `<Skeleton h-48 />` | No (box, not table) | Yes | No | Yes | Heatmap has no preview during load. |
| **DistributionShift** | `charts/DistributionShift.tsx:66-83` | `loading` prop | `<Skeleton h-32 />` | No (box, not table) | Yes | No | Yes | Inside Monitoring detail panel. |
| **ExportModal** | `ExportModal.tsx:16-56` | `exporting` (action) | disabled button | — | — | No | N/A | Action-driven, not data-driven. |
| **FeatureSelector** | `FeatureSelector.tsx:36-130` | `suggesting` (action) | disabled "AI suggest" button | — | — | LLM-health check only | N/A | Component-level. |
| **SchedulerOverview** | `SchedulerOverview.tsx:104-275` | 5 flags: `loading`, `detailLoading`, `savingCron`, `activeRuns`, `togglingJobs` | grid skeletons + modal skeletons | Mixed | Yes | **Yes** — list-jobs on mount, get-job on detail open, polling | Yes | Internal modal "open flash" — detail modal opens with skeleton while it fetches the job. |

---

## Section 2 — Findings by severity

### Critical (white flash / jarring)

| # | Page / area | What's wrong |
|---|---|---|
| C1 | **Features list** (`Features.tsx:86`) | No loading UI at all. Table jumps in cold; biggest visual gap. |
| C2 | **Jobs** (`Jobs.tsx:26`) | Table renders empty during load; no skeleton, no spinner. |
| C3 | **Actions** (`Actions.tsx:27`) | Same — empty list during fetch. Filter changes silently swap content. |
| C4 | **Search** (`Search.tsx:54`) | Results AND facet sidebar both render empty while query runs. Typing feels broken. |
| C5 | **Monitoring `setData(null)` on error** (`Monitoring.tsx:28-45`) | Refresh failure blanks the page entirely — user loses visible drift data because of a transient error. |

### High (wrong pattern — spinner/generic where shape-matched skeleton belongs)

| # | Site | What's wrong |
|---|---|---|
| H1 | **Groups list + all 5 tabs** (`Groups.tsx:46, 352, 475, 579`) | Generic `h-32` `<Skeleton>` for every load. Tabs especially jarring — switching tabs shows a generic box then reveals a structured chart/table. |
| H2 | **Sources list rows** (`Sources.tsx:63`) | Single `h-32` skeleton instead of N row-shaped skeletons. |
| H3 | **Audit auto-refresh** (`Audit.tsx:23` + 60s interval) | Auto-refresh re-skeletons the whole table every minute. Should be a subtle indicator or full preserve. |
| H4 | **Lineage** (`Lineage.tsx:80`) | Generic `h-64` box for a graph that has totally different shape. |
| H5 | **Help** (`Help.tsx:19`) | Generic `h-64` for a doc list (should be N list-item skeletons). |
| H6 | **All 7 mismatched chart skeletons** (Multi/Psi/Drift/Doc/Distrib/Heatmap) | Each chart's skeleton is a fixed-height grey box; the actual chart has axis lines, grid, bars. No axis bones means each load is a noticeable jolt. |

### Medium (layout shift, cascading reveals, sequential fetches)

| # | Site | What's wrong |
|---|---|---|
| M1 | **Cascading loads** — Dashboard, Groups detail tabs, Monitoring detail panel | Parent shows skeleton, then child charts each show their own skeleton when they hit the API. User sees 2-3 loading waves instead of 1. Specifically: `DriftRateTrend` + `GroupDriftHeatmap` fetch on mount despite parent already loading. |
| M2 | **Sources bulk scan sequential loop** (`Sources.tsx:193-225`) | `for (const name of names) { await api.sources.scan(name) }` — scans 10 sources serially (~30s) when `Promise.all` would do it in parallel (~3s). |
| M3 | **Features dual load paths** (`Features.tsx`) | Paginated mode and unbounded mode have separate `load()` functions with separate `Promise.all` calls. Refresh semantics drift between modes. |
| M4 | **Groups detail polls 1.5s** (`Groups.tsx:735-747`) | Docs job polling fires every 1.5s — backend status doesn't change that fast; 3s would be fine. |
| M5 | **SchedulerOverview detail-modal open flash** (`SchedulerOverview.tsx`) | Modal opens immediately with `detailLoading=true` and shows a skeleton — better than nothing, but consider eager-fetching alongside list. |

### Low (minor inconsistencies)

| # | Site | What's wrong |
|---|---|---|
| L1 | **`animate-shimmer` vs `<Skeleton>` divergence** (charts) | Two chart components (MultiMetric, PsiTimeline) hand-roll `animate-shimmer h-X` instead of using `<Skeleton className="h-X" />`. Same visual but two implementations. |
| L2 | **No empty-loading distinction in some charts** | Most charts do this well; one or two could clarify. |
| L3 | **Refresh button doesn't visibly distinguish initial vs refresh** | The `loading` flag drives skeleton AND button spinner — both happen at once. Better: refresh preserves content + only spins the button. |

---

## Section 3 — Proposed shared components

All compose from the existing `<Skeleton>` primitive (`web/src/components/Skeleton.tsx`). No new dependencies required.

### 3.1 `TableSkeleton`

```tsx
<TableSkeleton rows={5} columns={4} showHeader />
```

**Purpose**: replace generic `h-32` boxes used for tables (Audit, Jobs, Features list, Search results).
**Composes**: N rows of M cells, each a `<Skeleton>` sized to typical content width. Header row optional.
**Usage sites**: Audit (table), Jobs history table, Features list, Search results, Actions, Sources scan-history table inside detail panel.
**Impact**: ~6 sites × 5 lines saved each ≈ **30 LOC**. Visual win much larger.

### 3.2 `CardGridSkeleton`

```tsx
<CardGridSkeleton count={4} cardHeight="h-20" columns={4} />
```

**Purpose**: replace `Array.from({ length: 4 }).map((_, i) => <Skeleton key={i} className="h-20" />)` pattern.
**Usage sites**: Dashboard metric row, Monitoring stats row, DataSourceNodes (already grid-shape).
**Impact**: ~4 sites × 3 lines each ≈ **12 LOC**. Mostly a consistency win.

### 3.3 `ChartSkeleton`

```tsx
<ChartSkeleton kind="line" | "bar" | "heatmap" | "donut" height={180} />
```

**Purpose**: chart-shaped skeleton with axis bones + a faint trend curve placeholder. Replaces the generic `<Skeleton h-X />` used by 7 of 9 chart components.
**API sketch**:
- `line` / `bar` / `area` — renders an x/y axis baseline + 5-7 vertical guide ticks
- `heatmap` — renders an NxM grid of muted cells
- `donut` — renders a circular ring placeholder

**Usage sites**: MultiMetricTimeline, DriftRateTrend, PsiTimeline, UsageBubbleChart, GroupDriftHeatmap, DocCoverageDonut, DocDebtHeatmap, DistributionShift.
**Impact**: 8 sites × ~5 lines (loading branch) ≈ **40 LOC**, but the bigger win is eliminating layout shift — every chart currently jumps height when data arrives.

### 3.4 `ListItemSkeleton`

```tsx
<ListItemSkeleton count={6} showIcon showMeta />
```

**Purpose**: row-shaped skeleton for vertical lists (Sources rows, Groups rows, Help glossary entries).
**Usage sites**: Sources list panel, Groups list panel, Help glossary, possibly Lineage feature sidebar.
**Impact**: ~4 sites, modest LOC but big visual win — list rows currently flash as a single grey rectangle.

### 3.5 `DetailHeaderSkeleton`

```tsx
<DetailHeaderSkeleton showSubtitle showActions />
```

**Purpose**: title + subtitle + action-button-row skeleton for detail views (Features detail modal, Sources detail panel, Groups detail panel).
**Usage sites**: Sources detail (currently has hand-rolled stacked h-8/h-20/h-32), Features modal, Groups detail header.
**Impact**: 3-4 sites, consistency.

Skip:
- `StatCardSkeleton` — `<Skeleton className="h-20" />` already does the job; no value adding a wrapper.
- `ModalContentSkeleton` — too case-specific; modals that fetch on open should use the relevant primitive (Table/Card/Detail) inside.

**Total proposed**: **5 components**, all composing from the existing `<Skeleton>`. Estimated LOC reduction ~80-100 across migrations, but the headline win is visual consistency.

---

## Section 4 — Loading orchestration recommendations

### Per-page fixes

| Page | Recommendation |
|---|---|
| **Dashboard** | Pass the existing `loading` state down to `DriftRateTrend` and `DataSourceNodes` instead of letting them fetch internally — eliminates cascading reveal. Already correct on most sub-sections via prop drilling; just need parity. |
| **Features list** | Add `<TableSkeleton rows={10} columns={6} />` to the loading branch (currently `loading && null`). |
| **Groups detail** | Consolidate the 5 tab `load()` functions into a single parent-level `Promise.all` triggered on group selection. Cache the per-tab results so tab switches are instant after first load. |
| **Sources list rows** | Replace `<Skeleton className="h-32" />` with `<ListItemSkeleton count={6} />`. |
| **Sources bulk scan** | Replace `for (...) { await api.sources.scan(name) }` with `Promise.all(names.map(n => api.sources.scan(n)))`. 10× speed-up. |
| **Monitoring refresh-on-error** | Remove `setData(null)` in the error catch. Keep existing data visible + show the Alert banner. |
| **Audit auto-refresh** | Distinguish initial load (skeleton) from auto-refresh tick (no skeleton; subtle border-pulse or pause indicator). The audit table shouldn't disappear every 60s. |
| **Jobs table** | Add `<TableSkeleton rows={8} columns={4} />` to the loading branch. |
| **Actions list** | Add `<ListItemSkeleton count={6} />` to the loading branch. |
| **Search results + facets** | Add `<TableSkeleton rows={5} columns={3} />` for results, `<ListItemSkeleton count={4} />` for the facet sidebar. Crucial — search-as-you-type currently looks broken. |
| **Lineage** | Either pre-compute layout & show `<ChartSkeleton kind="graph" />` or, since the graph is layout-heavy, leave the current generic skeleton and document the limitation. |
| **Help** | Replace `h-64` skeleton with `<ListItemSkeleton count={8} />`. |
| **Settings** | Already best-in-class — refresh button spinner + preserved content. No change. |

### Cross-cutting orchestration patterns to enforce

1. **Single source of truth per page**: each page has ONE `load()` function that `Promise.all`s every required fetch. Sub-components receive data as props; they DO NOT fetch on their own when the parent is loading. Violators: Groups detail tabs, DriftRateTrend, GroupDriftHeatmap.
2. **Parallel mutations**: bulk operations use `Promise.all` over individual sub-requests, not a sequential `for-await` loop. Violator: Sources bulk scan.
3. **Refresh preserves stale data**: on refresh, the page sets `loading=true` but does NOT clear `data`. Spinner shows on the refresh button or as a subtle overlay; the existing content stays visible. Violator: Monitoring.
4. **Initial load vs auto-refresh**: pages with auto-refresh (Audit's 60s tick) should distinguish the two — initial load shows skeleton, refresh tick shows nothing or a tiny pulse on the section that updated.

---

## Section 5 — Phased fix plan

| Phase | Scope | Effort | Visual impact |
|---|---|---|---|
| **Phase 1** | Add 5 shared components: `TableSkeleton`, `CardGridSkeleton`, `ChartSkeleton`, `ListItemSkeleton`, `DetailHeaderSkeleton`. Co-located Vitest tests. Add to `/dev/components` demo page. | ~1 day | None until Phase 2 ships. |
| **Phase 2** | Fix the 5 **Critical** sites: Features list, Jobs table, Actions list, Search results, Monitoring `setData(null)`. Each migration is 5-10 lines. | ~half day | Largest UX win — kills the "white flash" experience on these pages. |
| **Phase 3** | Migrate the 6 **High** sites to use `ChartSkeleton` + `ListItemSkeleton`. Fix Audit auto-refresh treatment. | ~1 day | Visual polish across charts; auto-refresh no longer disorienting. |
| **Phase 4** | Orchestration fixes — Groups tab consolidation, Sources bulk scan parallelization, eager-fetching from parent into `DriftRateTrend` / `GroupDriftHeatmap`. | ~1 day | Eliminates cascading reveals and the bulk-scan latency cliff. |
| **Phase 5** | Low-severity cleanups (consolidate `animate-shimmer` ad-hocs into `<Skeleton>`). | ~half day | Code consistency only. |

**Total**: ~4 days for a full pass through. Phase 2 + Phase 4 alone (the Critical and orchestration fixes) deliver the bulk of user-facing value in ~1.5 days.

---

Audit complete. Awaiting human decision on which fixes to ship.
