# Reusable Component Audit — featcat frontend

**Date**: 2026-05-12
**Scope**: `web/src/` only (backend out of scope)
**Method**: Pattern-by-pattern grep + read across `pages/`, `components/`, `locales/`. Cross-checked existing components in `web/src/components/` and `web/src/components/ui/`.
**Output**: This report. No code was changed.

---

## Component inventory (already shared)

| Component | Path | What it does | Adoption |
|---|---|---|---|
| `Badge` | `web/src/components/Badge.tsx` | Variant-driven status pill (success / warning / danger / info / default + aliases healthy / critical / error / running). | 23 callsites; 7 inline equivalents bypass it. |
| `Skeleton` | `web/src/components/Skeleton.tsx` | Shimmer-gradient box driven by `className`. | 30 callsites; **100 % adoption**. |
| `Modal` | `web/src/components/Modal.tsx` | Overlay + dialog + animated open/close + footer slot. | 18+ callsites; **100 % adoption**. |
| `MetricCard` | `web/src/components/MetricCard.tsx` | Label + numeric value + optional icon + optional 0–100 progress bar. | 8+ callsites. |
| `FeatureSelector` | `web/src/components/FeatureSelector.tsx` | Search + checkbox + AI-suggest list of features. | 4 callsites (Groups, Features, ExportModal, Sources). |
| `ScoreTooltip` | `web/src/components/ScoreTooltip.tsx` | Glossary-linked metric tooltip. | 5+ callsites in Monitoring + Features. |
| `SearchInput` | `web/src/components/SearchInput.tsx` | Debounced search input. | Used in Features, FeatureSelector. |
| `timeAgo()` | `web/src/api.ts:671-682` | i18n-aware relative-time formatter (`Intl.RelativeTimeFormat`). | 8 callsites; **100 % adoption**. |

---

## Pattern 1: Confirmation Dialog (destructive actions)

**Rating**: Medium

**Occurrences**: 5 destructive-action callsites across 4 pages (mixed flavours).

| File | Lines | Variation notes |
|---|---|---|
| `web/src/pages/Sources.tsx` | 70, 173, 417 (modal at 878–950) | `<Modal>` + async `/impact` fetch + group-list preview + loading state. Confirm label changes to "Deleting…". |
| `web/src/pages/Features.tsx` | 1745–1770 (`BulkDeleteModal`) | `<Modal>` + checkbox-acknowledgment gate + preview list of names with overflow count. |
| `web/src/pages/Groups.tsx` | 72 | `window.confirm()` only. |
| `web/src/pages/Settings.tsx` | 133 | `window.confirm()` only. |

**Total duplicated LOC**: ~150 (mostly Sources + Features modal scaffolding; window.confirm sites are 1-liners but lose UX consistency).

**Snippet — Sources delete modal (878–894)**:
```tsx
<Modal open={open} onClose={onClose} title={t('delete_modal.title', { name })}
  actions={<>
    <button onClick={onClose} disabled={deleting} ...>{t('actions.cancel', { ns: 'common' })}</button>
    <button onClick={submit} disabled={deleting || loading}
      className="bg-[var(--danger)] text-white rounded-lg disabled:opacity-50">
      {deleting ? t('delete_modal.deleting') : t('delete_modal.confirm')}
    </button>
  </>}
>
```

**Snippet — Features bulk-delete with acknowledgment (1755–1769)**:
```tsx
<button disabled={!acknowledged || submitting || names.length === 0}
  className="bg-[var(--danger)] text-white rounded-lg disabled:opacity-50">
  {submitting ? t('actions.loading', { ns: 'common' }) : t('bulk.delete_modal.confirm_button')}
</button>
<div className="border border-[var(--danger)]/40 bg-[var(--danger)]/10">
  <AlertTriangle size={16} className="text-[var(--danger)]" />
  <p className="text-[13px] text-[var(--danger)]">{t('bulk.delete_modal.warning')}</p>
</div>
```

**Snippet — Groups native confirm (72)**:
```tsx
const deleteGroup = async (name: string) => {
  if (!window.confirm(t('confirm_delete', { name }))) return
  await api.groups.delete(name)
```

**Proposed API**:
```tsx
<ConfirmDialog
  open: boolean
  onClose: () => void
  title: string
  message?: ReactNode                // e.g. impact summary
  warning?: string                   // red callout under message
  requireCheckbox?: string           // when set, renders an "I understand" checkbox
  severity?: 'destructive' | 'warning' | 'info'  // styles the confirm button
  confirmLabel: string               // e.g. "Delete"
  pendingLabel?: string              // shown while pending, e.g. "Deleting…"
  onConfirm: () => void | Promise<void>
/>
```

**Migration complexity**: Medium. Sources' impact loader and Features' acknowledgment gate are different enough that the API needs `message: ReactNode` (free-form body) + the optional `requireCheckbox` switch. Replacing the two `window.confirm` callers is trivial.

**Recommendation**: **Ship in follow-up PR** — the visual-vs-native split is a UX inconsistency that's worth fixing once we have the component. Defer the deeper "type-to-confirm" variant unless a real callsite demands it.

---

## Pattern 2: Empty State

**Rating**: High

**Occurrences**: 18 callsites across 8 pages.

| File | Lines | Variation notes |
|---|---|---|
| `web/src/pages/Sources.tsx` | 342–354 | Icon (HardDrive) + title + CTA button. |
| `web/src/pages/Sources.tsx` | 357–359 | Filter-aware text-only fallback ("no match"). |
| `web/src/pages/Search.tsx` | 169–172 | Icon + prompt text only. |
| `web/src/pages/Search.tsx` | 256–267 | Bordered card + multi-paragraph + conditional "Clear filters" CTA. |
| `web/src/pages/Groups.tsx` | 114, 362, 482, 504, 627 | 5 inline simple text variants. |
| `web/src/pages/Dashboard.tsx` | 100–104, 233, 247, 249, 285, 335, 359 | 7 inline variants (error + 6 empty-text). |
| `web/src/pages/Monitoring.tsx` | 131 | Inline simple text. |
| `web/src/pages/Features.tsx` | 805, 839, 883, 908, 936 | 5 inline span variants. |

**Total duplicated LOC**: ~180.

**Snippet — Sources rich (342–354)**:
```tsx
<div className="text-center py-8 px-3">
  <HardDrive size={32} className="mx-auto mb-2 text-[var(--text-tertiary)]" strokeWidth={1.5} />
  <p className="text-sm text-[var(--text-secondary)] mb-3">{t('list.empty_title')}</p>
  <button onClick={() => setCreateOpen(true)} className="text-xs text-brand hover:underline">
    {t('list.empty_cta')}
  </button>
</div>
```

**Snippet — Search bordered + clear (256–267)**:
```tsx
<div className="text-center py-16 border border-dashed border-[var(--border-subtle)] rounded-xl">
  <p className="text-sm text-[var(--text-secondary)] mb-2">{t('empty.no_match', { query: q })}</p>
  <p className="text-xs text-[var(--text-tertiary)]">{t('empty.suggest')}</p>
  {activeFilterCount > 0 && (
    <button onClick={clearAll} className="mt-3 text-xs text-brand hover:underline">{t('facets.clear')}</button>
  )}
</div>
```

**Snippet — Groups bare (114)**:
```tsx
<p className="text-[var(--text-tertiary)] text-sm py-4 text-center">{t('list.empty')}</p>
```

**Proposed API**:
```tsx
<EmptyState
  icon?: LucideIcon                  // e.g. HardDrive (32px, tertiary, centered)
  title: string                      // e.g. "Chưa có nguồn nào"
  description?: string               // optional secondary line
  action?: { label: string; onClick: () => void }   // CTA button
  variant?: 'plain' | 'bordered'     // bordered = dashed-border card (Search style)
  size?: 'compact' | 'default'       // py-4 vs py-8/16
/>
```

**Migration complexity**: Easy for the 14 simple-text sites. Medium for Sources (CTA) + Search (bordered + dynamic clear). The two outliers slot into the same component via the `action` and `variant` props.

**Recommendation**: **Ship in follow-up PR**. The dashboard alone has 7 inline variants — extracting this gives the most immediate pile-of-LOC reduction and locks in visual consistency.

---

## Pattern 3: Status / Severity Badge — fix-up only

**Rating**: Low (component already exists)

**Occurrences**: 23 `<Badge>` callsites + 7 inline equivalents that should switch.

| File | Lines | Notes |
|---|---|---|
| `Badge` callsites — Sources, Groups, Jobs, Features, Monitoring, Dashboard, Audit, SchedulerOverview, DataSourceNodes | various | Correct usage — no action needed. |
| `Sources.tsx` | 262, 665, 736, 985, 989 | Inline danger banners — `<p className="text-[var(--danger)] bg-[var(--danger-subtle-bg)] rounded-lg px-3 py-2">…</p>`. Block-level, not pill — see Pattern note below. |
| `Monitoring.tsx` | 104 | Inline error alert. |
| `Chat.tsx` | 381 | Inline warning banner. |
| `Features.tsx` | 501, 1765 | Inline danger alert boxes (`<AlertTriangle>` + paragraph). |

**Total duplicated LOC**: ~50.

**Pattern note**: The "inline equivalents" are **not** badges — they are full-width info/warning/error **alerts** (paragraph + optional icon). Trying to retrofit them onto the existing `<Badge>` would distort it. They are a distinct pattern that should become an `<Alert>` component (see new Pattern 19 below).

**Recommendation**: **Skip** as a Badge-extraction effort. Roll the 7 inline cases into the new `<Alert>` work in Pattern 19.

---

## Pattern 4: Loading skeletons — no action

**Rating**: Skip

**Occurrences**: 30 callsites across 13 files; `<Skeleton>` is used at every site we found. No `animate-pulse` fallbacks.

**Recommendation**: **Skip** — already cleanly extracted.

---

## Pattern 5: Path display

**Rating**: Skip

**Occurrences**: 2 (both inside `Sources.tsx`).

| File | Lines | Notes |
|---|---|---|
| `Sources.tsx` | 483–485 | Truncated mono path with `title` tooltip. |
| `Sources.tsx` | 620 | Path input field (different concern). |

Other pages don't render long paths today.

**Recommendation**: **Skip**. If path display lands on Feature detail or Dashboard later, revisit.

---

## Pattern 6: Threshold slider

**Rating**: Skip / Defer

**Occurrences**: 2 (both inside `pages/similarity/`).

| File | Lines | Notes |
|---|---|---|
| `similarity/SimilarityMatrix.tsx` | 167–171 | `useDebouncedValue(threshold, 400)` hook. |
| `similarity/SimilarityGraph.tsx` | 440–448 | `useRef`+`setTimeout` debounce, 400ms. |

Both share step `0.05`, both 400ms debounce, but use different debounce mechanisms.

**Total duplicated LOC**: ~35.

**Recommendation**: **Defer**. The win is real but small (2 sites in the same subfolder). If a third caller appears (e.g. Monitoring threshold config), revisit and extract `<ThresholdSlider min={...} max={...} step={0.05} debounceMs={400} value={...} onCommit={...} />`.

---

## Pattern 7: Relative time display — no action

**Rating**: Skip

**Occurrences**: 8 callsites; all use `timeAgo()` from `web/src/api.ts:671-682`. i18n-aware via `Intl.RelativeTimeFormat`.

**Recommendation**: **Skip** — already centralized. (Optionally bring forward an `<RelativeTime>` wrapper later that adds an absolute-timestamp tooltip on hover, but not urgent.)

---

## Pattern 8: Feature reference chip

**Rating**: Medium

**Occurrences**: 6, with two distinct shapes.

| File | Lines | Shape | Notes |
|---|---|---|---|
| `components/FeatureSelector.tsx` | 180–199 | List row | spec / dtype / health-grade / AI-star / checkbox. |
| `pages/similarity/PairPanel.tsx` | 145–154 | Card | name / source / dtype, static. |
| `pages/Search.tsx` | 275–286 | Search hit | name (mono brand) / source / dtype / rank %. |
| `pages/Search.tsx` | 515–524 | Autocomplete row | denser version of above. |
| `components/charts/GroupDriftHeatmap.tsx` | 110–114 | Heatmap cell | name only + tooltip. |
| `pages/Features.tsx` | 351 | Table row | source extracted from `name.split('.')[0]`. |

**Total duplicated LOC**: ~120.

**Snippet — PairPanel card (145–154)**:
```tsx
function FeatureCard({ label, feat }: { label: string; feat: SimilarityFeatureBrief }) {
  return (
    <div className="border border-[var(--border-subtle)] rounded-md px-3 py-2">
      <div className="text-[10px] uppercase tracking-wide text-[var(--text-tertiary)]">{label}</div>
      <div className="text-[13px] font-medium text-[var(--text-primary)] break-all">{feat.name}</div>
      <div className="text-[11px] text-[var(--text-tertiary)] flex gap-2 mt-1">
        <span>{feat.source || '—'}</span><span className="font-mono">{feat.dtype || '—'}</span>
      </div>
    </div>
  )
}
```

**Snippet — Search hit (275–286)**:
```tsx
<div className="flex items-center justify-between gap-3 mb-1">
  <span className="font-mono text-sm font-medium text-brand truncate">{hit.name}</span>
  <span className="text-[11px] text-[var(--text-tertiary)] tabular-nums">{Math.round(hit.rank * 100)}%</span>
</div>
<div className="flex items-center gap-2 text-xs text-[var(--text-tertiary)]">
  <span>{hit.source}</span><span>·</span><span className="font-mono">{hit.dtype}</span>
</div>
```

**Proposed API**:
```tsx
<FeatureRef
  feature: { name: string; source?: string; dtype?: string; has_doc?: boolean; health_grade?: string }
  density: 'card' | 'row' | 'inline'   // controls layout (card = boxed, row = list-item, inline = chip)
  to?: string                           // when set, wraps in <Link>
  trailing?: ReactNode                  // e.g. score %, rank %, AI-star
/>
```

**Migration complexity**: Medium. The shapes differ enough that the component needs `density` + `trailing` slots. The heatmap cell (name-only with tooltip) doesn't fit and stays as-is. FeatureSelector's row has interactive state (checkbox + AI-star) and would keep its own inline rendering — `<FeatureRef>` is read-only display.

**Recommendation**: **Defer to a second wave**. The primary win is Search hit + PairPanel card; not enough sites to be top-priority. Revisit when adding Lineage node tooltips or Group recommendations panel — both natural future callsites.

---

## Pattern 9: Score visualization (0–1 bar)

**Rating**: Medium

**Occurrences**: 11. The simple single-segment bar is already covered by `<MetricCard progress={...} />`. The duplication is in **multi-segment stacked bars** (grade distribution A/B/C/D, certification status, segmented progress).

| File | Lines | Notes |
|---|---|---|
| `MetricCard.tsx` | 28–35 | Reusable single-segment bar (already shared). |
| `Dashboard.tsx` | 166–175 | A/B/C/D health-grade stacked bar. |
| `Dashboard.tsx` | 202–219 | Certification status (draft/reviewed/certified/deprecated) stacked bar with clickable segments. |
| `Groups.tsx` | 166–175 | Same A/B/C/D pattern as Dashboard — direct duplicate. |
| `Groups.tsx` | 390 | Single colored segment. |
| `Groups.tsx` | 794 | Completion progress bar. |
| `Features.tsx` | 365–376 | Inline 12px-wide health-score bar in table row. |
| `Features.tsx` | 1400–1415 | Three custom 1.5px bars (doc / drift / usage) in health-breakdown modal. |
| `components/charts/DocCoverageDonut.tsx` | 68 | Legend bar. |
| `components/charts/DataSourceNodes.tsx` | 98 | Doc-percentage bar. |

**Total duplicated LOC**: ~180.

**Snippet — Dashboard A/B/C/D stack (166–175)**:
```tsx
<div className="flex items-center gap-1 h-4 rounded-full overflow-hidden mb-2">
  {(['A','B','C','D'] as const).map(g => {
    const count = healthSummary.grade_distribution[g] || 0
    const total = Object.values(healthSummary.grade_distribution).reduce((a,b) => a+b, 0)
    const pct = total > 0 ? (count/total)*100 : 0
    if (pct === 0) return null
    const bg = { A:'bg-green-500', B:'bg-teal-500', C:'bg-amber-500', D:'bg-red-500' }[g]
    return <div key={g} className={`h-full ${bg}`} style={{ width: `${pct}%` }} />
  })}
</div>
```

**Snippet — Features triple-bar breakdown (1400–1402)** ✕ 3:
```tsx
<div className="h-1.5 bg-[var(--bg-tertiary)] rounded-full overflow-hidden">
  <div className="h-full bg-[var(--brand)] transition-all" style={{ width: `${docPct}%` }} />
</div>
```

**Proposed API**:
```tsx
<SegmentedBar
  segments: { value: number; color: string; label?: string; onClick?: () => void }[]
  height?: number             // 4 | 6 | 16  (default 6)
  rounded?: boolean           // pill vs square
  showZero?: boolean          // render 0-value segments or skip them
/>
```

**Migration complexity**: Medium. The A/B/C/D and certification cases land cleanly. The Features 1.5px-bar triplet is just 3 separate `<MetricCard>`-style single bars — those should reuse `<MetricCard>` with `progress`, not `<SegmentedBar>`.

**Recommendation**: **Ship `<SegmentedBar>` in follow-up PR**. Secondary win: rip the Features 1400–1415 triple-bar over to `<MetricCard>`s in the same PR.

---

## Pattern 10: Source storage badge

**Rating**: Skip

**Occurrences**: 3 (all in `Sources.tsx`, all the same conditional `Badge variant=…`).

**Recommendation**: **Skip** — already uses `<Badge>`, repetition is trivial within one file.

---

## Pattern 11: Page header layout

**Rating**: High

**Occurrences**: 17 page-level headers with the same flex/justify-between/h1 + actions pattern.

| File | Lines | Variation |
|---|---|---|
| `pages/Dashboard.tsx` | 120–126 | Title + refresh button. |
| `pages/Features.tsx` | 388–396 | Title + refresh + count label. |
| `pages/Sources.tsx` | 250–258 | Title + primary CTA. |
| `pages/Groups.tsx` | 100–106 | Title + primary CTA. |
| `pages/Audit.tsx` | 53–60 | Title + subtitle + refresh. |
| `pages/Actions.tsx` | 85–96 | Title + subtitle + refresh. |
| `pages/Settings.tsx` | 31–34 | Title + subtitle. |
| `pages/Jobs.tsx` | 79–81 | Title only. |
| `pages/Monitoring.tsx` | 89 | Title only. |
| `pages/Help.tsx` | 56 | Title only. |
| `pages/Search.tsx` | 159 | Title only. |
| `pages/Chat.tsx` | 393 | Title inside container. |
| `pages/Lineage.tsx` | 900–902 | Title + optional actions. |
| `pages/similarity/SimilarityGraph.tsx` | 423 | Title + empty actions slot. |
| `pages/Similarity.tsx` | 50–52 | Title + optional actions. |

**Total duplicated LOC**: ~120.

**Snippet — Dashboard (120–126)**:
```tsx
<div className="flex justify-between items-center mb-6">
  <h1 className="text-2xl font-semibold">{t('page.title')}</h1>
  <button onClick={load} disabled={loading} className="...">
    <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
    {t('actions.refresh', { ns: 'common' })}
  </button>
</div>
```

**Snippet — Audit with subtitle (53–60)**:
```tsx
<div className="flex justify-between items-center mb-6">
  <div>
    <h1 className="text-xl font-semibold">{t('page.title')}</h1>
    <p className="text-sm text-[var(--text-tertiary)] mt-0.5">{t('page.subtitle')}</p>
  </div>
  <button onClick={load} disabled={loading} className="...">…</button>
</div>
```

**Proposed API**:
```tsx
<PageHeader
  title: string
  subtitle?: string
  actions?: ReactNode               // free-form action slot (refresh button, CTA, count chips)
  size?: 'default' | 'compact'      // controls h1 size — Audit uses xl, others 2xl
/>
```

**Migration complexity**: Easy. Drop-in across all 17 pages, even the title-only ones (`<PageHeader title={t('page.title')} />`).

**Recommendation**: **Ship in follow-up PR**. Highest-occurrence pattern in the audit; locks in spacing + h1 sizing across the app.

---

## Pattern 12: Tab navigation

**Rating**: Medium

**Occurrences**: 3 sites, all using the same `border-b-2 + active brand` underline pattern.

| File | Lines | Notes |
|---|---|---|
| `pages/Features.tsx` | 708–717 | Hardcoded 2-tab pair (overview/history). |
| `pages/Groups.tsx` | 189–199 | Map over array of `{id, label, icon}` (members/health/monitoring/docs/versions). |
| `pages/Similarity.tsx` | 54–75 | Map over array with icons (graph/matrix/pairs). |

**Total duplicated LOC**: ~80.

**Snippet — Groups dynamic (189–197)**:
```tsx
className={`flex items-center gap-1.5 px-3 py-2 text-[12px] font-medium border-b-2 transition-colors ${
  tab === entry.id ? 'border-brand text-brand' : 'border-transparent text-[var(--text-tertiary)] hover:text-[var(--text-primary)]'
}`}
```

**Proposed API**:
```tsx
<Tabs
  tabs: { id: string; label: string; icon?: LucideIcon; badge?: ReactNode }[]
  value: string
  onChange: (id: string) => void
  size?: 'default' | 'compact'
/>
```

**Migration complexity**: Easy. Groups already uses an array; Features needs a 30-second refactor to the same shape.

**Recommendation**: **Ship in follow-up PR**. Locks in that any future "tabbed detail pane" gets identical look.

---

## Pattern 13: Tooltips

**Rating**: Low (heterogeneous; not one component)

**Occurrences**: 30+ across three distinct categories.

| Kind | Sites | Notes |
|---|---|---|
| Native `title=""` | 20+ across pages and chart components | Lightweight, OK for short labels. |
| `<ScoreTooltip>` (custom) | 5 callsites in Monitoring + Features | Glossary-linked help bubble. Already extracted. |
| Recharts `<Tooltip>` + per-chart `CustomTooltip` | 4 chart components (MultiMetricTimeline, DriftRateTrend, PsiTimeline, UsageBubbleChart) | Each rolls its own `CustomTooltip`. |

**Total duplicated LOC**: ~120 (mostly the four chart `CustomTooltip` components).

**Recommendation**: **Defer**. The native `title` callsites aren't worth replacing (browser tooltips are fine for short labels). The Recharts `CustomTooltip` duplication is real but cross-cutting with chart styling and deserves its own dedicated pass: extract `<ChartTooltipShell>` (just the styled card wrapper) so each chart provides its own per-row content but reuses the visual chrome.

---

## Pattern 14: Filter bar

**Rating**: Medium (extract the parts, not the whole)

**Occurrences**: 6 filter clusters across 6 pages.

| File | Lines | Notes |
|---|---|---|
| `pages/Features.tsx` | 399–459 | Search + 4 dropdowns + 2 toggles + clear-link + actions. Most complex. |
| `pages/Sources.tsx` | 303–335 | Search input + 2 dropdowns. |
| `pages/Audit.tsx` | 63–84 | 3 dropdowns + count label. |
| `pages/Actions.tsx` | 99–120 | 2 dropdowns. |
| `pages/Jobs.tsx` | 87–130 | 3 dropdowns + count label. |
| `pages/Search.tsx` | 191–200 | Sidebar facet panel + clear button. |

**Total duplicated LOC**: ~240, but the cluster shape varies enough that a single `<FilterBar>` would need a long prop list.

**What is identical across sites**: the `<select>` styling, the "clear all filters" link, and the `count` chip. What varies: how many filters, which fields, whether a search input is present, whether the bar is horizontal or sidebar.

**Proposed API** (small primitives, not one mega-component):
```tsx
<FilterRow>...</FilterRow>                                  // flex wrapper with the right gap/wrap behavior
<FilterSelect value={...} onChange={...} options={[...]} /> // styled <select> with the standard className
<FilterClearLink onClick={...} />                           // "Clear all filters" — only renders when active filters > 0
<FilterCountChip count={N} label={...} />                   // "120 features"
```

**Migration complexity**: Medium. Pages keep their own state and filter logic; only the chrome is shared. No big-bang refactor.

**Recommendation**: **Ship in follow-up PR** — extract just `<FilterSelect>` first (huge LOC win, low risk), then `<FilterClearLink>` and `<FilterCountChip>`. Hold off on a single `<FilterBar>` wrapper until a third caller wants horizontal-with-search exactly like Sources or Features.

---

## Pattern 15: Action menus (three-dot dropdown)

**Rating**: N/A

**Occurrences**: **0**. No `MoreHorizontal` / `MoreVertical` callsites; no row-level dropdown menus. Inline action buttons (edit/delete icons sitting next to each other) is the convention today.

**Recommendation**: **Skip**. Revisit if a future row gains 4+ actions and starts looking cluttered.

---

## Pattern 16: Modal wrapper — no action

**Rating**: Skip

**Occurrences**: 18+ `<Modal>` callsites; **100 % adoption**. No raw `fixed inset-0` overlays found.

**Recommendation**: **Skip** — already cleanly extracted.

---

## Pattern 17 (open): Refresh button

**Rating**: High

**Occurrences**: 8–10 sites with the same icon-button pattern.

| File | Lines | Notes |
|---|---|---|
| `Dashboard.tsx` | 122–126 | |
| `Features.tsx` | 392–395 | |
| `Audit.tsx` | 58–60 | |
| `Actions.tsx` | 91–96 | |
| `Monitoring.tsx` | 111–117 | Slightly different style (no border). |
| `Sources.tsx` | (in detail panel) | Inline next to delete. |
| `Groups.tsx` | (in subpanels) | |
| `Jobs.tsx` | (in SchedulerOverview) | |

**Total duplicated LOC**: ~80.

**Snippet (Dashboard 122–126)**:
```tsx
<button onClick={load} disabled={loading}
  className="flex items-center gap-1.5 px-3 py-1.5 text-[13px] font-medium border border-[var(--border-default)] rounded-lg bg-[var(--bg-primary)] hover:bg-[var(--bg-secondary)] disabled:opacity-50">
  <RefreshCw size={14} className={loading ? 'animate-spin' : ''} />
  {t('actions.refresh', { ns: 'common' })}
</button>
```

**Proposed API**:
```tsx
<RefreshButton
  onClick: () => void
  loading: boolean
  label?: string             // defaults to t('actions.refresh', {ns:'common'})
  size?: 'default' | 'compact'
/>
```

**Migration complexity**: Easy.

**Recommendation**: **Ship in follow-up PR**. Trivially extractable, tightens the spinner-on-loading affordance everywhere.

---

## Pattern 18 (open): Primary CTA button

**Rating**: Low (use a CSS class, not a component)

**Occurrences**: 9 sites with the `px-4 py-2 bg-brand text-white rounded-lg ...` pattern.

| File | Lines | Notes |
|---|---|---|
| `Sources.tsx` | 254 | New Source CTA. |
| `Groups.tsx` | 102, 613, 777 | Create + submit buttons. |
| `Features.tsx` | 455 | Export selection. |
| `Chat.tsx` | 456 | Send button. |
| `Monitoring.tsx` | 188 | Confirm baseline. |
| `Dashboard.tsx` | 102 | Retry. |

**Total duplicated LOC**: ~90 (mostly className strings).

**Recommendation**: **Defer / consider a CSS utility instead** — wrapping a `<button>` in a component for one className adds an indirection without much benefit. A Tailwind plugin or shared `className` constant (`btnPrimary`, `btnSecondary`) might be a better fit. Park this; revisit if the class drifts (e.g. someone adds focus-ring tokens).

---

## Pattern 19 (new): Inline alert / banner

**Rating**: Medium

**Occurrences**: 7 distinct alert blocks (extracted out of Pattern 3 since they aren't actually pills).

| File | Lines | Notes |
|---|---|---|
| `Sources.tsx` | 262, 665, 736 | `<p className="text-[var(--danger)] bg-[var(--danger-subtle-bg)] rounded-lg px-3 py-2">{error}</p>` — error inline. |
| `Sources.tsx` | 985, 989 | Modal warning + error banner pair. |
| `Monitoring.tsx` | 104 | Inline error with dismiss button. |
| `Chat.tsx` | 381 | Warning banner. |
| `Features.tsx` | 501, 1765 | Danger-tinted action button + acknowledgment block. |

**Total duplicated LOC**: ~70.

**Snippet — Sources error banner (262)**:
```tsx
<div className="mb-4 p-3 rounded-lg bg-[var(--danger-subtle-bg)] border border-[var(--danger-subtle-bg)] text-[var(--danger)] text-sm flex items-center justify-between">
  <span>{error}</span>
  <button onClick={() => setError(null)} className="text-[var(--danger)] hover:opacity-80 ml-2 shrink-0">×</button>
</div>
```

**Snippet — Features warning with icon (1765)**:
```tsx
<div className="flex items-start gap-2 rounded-lg border border-[var(--danger)]/40 bg-[var(--danger)]/10 px-3 py-2">
  <AlertTriangle size={16} className="text-[var(--danger)]" />
  <p className="text-[13px] text-[var(--danger)]">{t('bulk.delete_modal.warning')}</p>
</div>
```

**Proposed API**:
```tsx
<Alert
  severity: 'info' | 'warning' | 'danger' | 'success'
  message: ReactNode
  icon?: boolean                   // include the matching lucide icon
  onDismiss?: () => void           // when set, shows ✕ close button
/>
```

**Migration complexity**: Easy. All 7 sites map cleanly; the dismissable variant covers Sources/Monitoring's `setError(null)` pattern.

**Recommendation**: **Ship in follow-up PR**. Pairs well with Pattern 1 (ConfirmDialog) since both surface error/warning states.

---

## Summary table (ranked by ROI)

ROI = `occurrences × LOC saved per occurrence × likelihood of future reuse`. "Already shared" patterns excluded.

| Rank | Pattern | Sites | LOC saved | Migration | Recommendation |
|---|---|---|---|---|---|
| 1 | **PageHeader** (#11) | 17 | ~120 | Easy | **Ship** — drives consistency for every page. |
| 2 | **EmptyState** (#2) | 18 | ~180 | Easy (mostly) | **Ship** — biggest pile of duplicated JSX. |
| 3 | **RefreshButton** (#17) | 8–10 | ~80 | Easy | **Ship** — trivial extraction, immediate consistency. |
| 4 | **FilterSelect + FilterClearLink + FilterCountChip** (#14) | 6 sites, ~15 inline `<select>`s | ~240 | Medium | **Ship** — extract the parts, not the whole. |
| 5 | **Tabs** (#12) | 3 | ~80 | Easy | **Ship** — small but locks in pattern for next caller. |
| 6 | **Alert** (#19) | 7 | ~70 | Easy | **Ship** — fixes the inline-Badge-equivalent gap. |
| 7 | **ConfirmDialog** (#1) | 5 (mixed flavours) | ~150 | Medium | **Ship** — kills the `window.confirm` UX inconsistency. |
| 8 | **SegmentedBar** (#9) | 5–6 | ~180 | Medium | **Ship** — covers grade + certification stacked bars. |
| — | FeatureRef chip (#8) | 6 | ~120 | Medium | **Defer** — too much variation; revisit when Lineage tooltips need it. |
| — | Tooltip cluster (#13) | 30+ mixed | ~120 | Hard | **Defer** — extract just `<ChartTooltipShell>` later. |
| — | Threshold slider (#6) | 2 | ~35 | Easy | **Defer** — only Similarity uses it today. |
| — | Primary CTA (#18) | 9 | ~90 | Easy | **Defer** — CSS class likely better than component. |
| — | Path display (#5) | 2 | ~15 | — | **Skip** — single-file. |
| — | Storage badge (#10) | 3 | ~10 | — | **Skip** — already `<Badge>`. |
| — | Action menus (#15) | 0 | — | — | **Skip** — pattern doesn't exist yet. |
| — | Status Badge (#3) | shared | — | — | **Skip** — already extracted; Pattern 19 covers the spillover. |
| — | Skeleton (#4), Modal (#16), `timeAgo` (#7) | shared | — | — | **Skip** — already 100 % adoption. |

---

## Final recommendation

**Ship 8 components in a single follow-up "shared UI" PR**, in the order listed below. Total LOC removed: roughly **1,000+** (sum of "LOC saved" column for ranks 1–8). Most are small, mechanical migrations.

1. **`PageHeader`** — start here. 17 callsites, drop-in.
2. **`EmptyState`** — 18 callsites, drop-in for the simple cases; CTA + bordered variants for Sources / Search.
3. **`RefreshButton`** — trivial.
4. **`FilterSelect` + `FilterClearLink` + `FilterCountChip`** — three small primitives; do **not** ship a giant `<FilterBar>` wrapper yet.
5. **`Tabs`** — three callsites, all converge on the same shape after a 30-line refactor in Features.
6. **`Alert`** — fixes the seven inline danger/warning banners that currently bypass `<Badge>`.
7. **`ConfirmDialog`** — replaces the two `window.confirm()` callsites and lets Sources/Features share the modal scaffold.
8. **`SegmentedBar`** — locks in the A/B/C/D + certification stacked-bar pattern; secondary win is migrating Features 1400–1415's triple-bar to `<MetricCard>`.

**Defer** to a second wave when there's a third caller justifying the work: `FeatureRef`, `ChartTooltipShell`, `ThresholdSlider`, primary-CTA shared class.

**Skip** (no action): path display, storage badge (already a Badge), action menus (don't exist yet), the patterns that are already 100 % shared (`Skeleton`, `Modal`, `timeAgo`, `MetricCard`'s single-segment bar).

---

Audit complete. Awaiting human decision on which patterns to extract.
