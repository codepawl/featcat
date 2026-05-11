# Similarity Refactor — Implementation Plan

> Phase 0 deliverable for the "list-first Similarity page" brief. Approved with revisions on 2026-05-11.

## Context

`/similarity` currently shows a D3 force-directed graph as the primary view. Two issues:

1. **Not actionable.** Users see clusters and leave. The high-value workflows are *find duplicates* and *recommend features for a use case* — both list/table interactions.
2. **Heavy initial bundle.** `d3` is grouped with `recharts` in `manualChunks.charts`, so the full `~431 kB` chart bundle ships on first Similarity hit even though most users never interact with the graph.

The refactor restructures `/similarity` around three tabs (Duplicates default · Recommendations · Graph), lazy-loads the Graph tab via `React.lazy`, and splits `d3` out of the shared chart chunk so the lazy boundary actually pays off.

---

## Findings (from Phase 0 exploration)

### Backend — what exists, what doesn't

**Already exists (reuse, do NOT duplicate):**

- `GET /api/features/similarity-graph?threshold=…&source=…` — `featcat/server/routes/features.py:556-638`. Builds TF-IDF over `name + tags + short_description`, returns `{nodes, edges}`. **Untouched by this PR.**
- `GET /api/features/by-name/similar?name=…&top_k=…` — `routes/features.py:422-438`. Returns `[{id, name, dtype, similarity}]`. Will be reused indirectly.
- `LocalBackend.find_similar_features(feature_id, top_k)` — `featcat/catalog/local.py:1508-1655`. Postgres+pgvector path (`_find_similar_pgvector`) and TF-IDF fallback (`_find_similar_tfidf`). The TF-IDF helper already builds the corpus and the vectorizer the new duplicates endpoint needs.
- `LocalBackend.search_by_embedding(vec, top_k)` — `local.py:1562-1599`. pgvector-only; safe to ignore on SQLite.
- `POST /api/ai/discover` — `routes/ai.py:37-70`. Calls `DiscoveryPlugin` (LLM-required, returns 503 without LLM). Returns `{existing_features, new_feature_suggestions, summary}`.
- `get_feature_summary(db, max_features=100)` — `featcat/utils/catalog_context.py:11-36`. Plain-text corpus used by the discovery prompt.
- `_compute_stats` — `featcat/catalog/scanner.py:80-95`. Per-feature `mean / std / min / max / null_ratio / unique_count` in `features.stats` (TEXT JSON).
- `LocalBackend.get_latest_severity(feature_id)` — `local.py:1379`. Drift status (healthy/warning/critical).
- In-process TTL cache — `featcat/server/cache.py` (`cache_get`, `cache_set`, `invalidate(prefix)`).
- Pydantic conventions — see `StatusCountsResponse` (`routes/features.py:317`) for the canonical response-model shape.

**Does NOT exist (must build):**

- A "find duplicate **pairs**" endpoint. No existing helper aggregates pairs above a threshold with reason codes. Search for `duplicate`/`dedup` in the codebase: only references are anti-duplicate UPSERT logic, nothing semantic.
- A non-LLM recommend path. `DiscoveryPlugin` hard-fails without LLM. The brief explicitly wants Recommendations to work without LLM (LLM is bonus).
- A schema/distribution similarity helper (compares two features' `stats` dicts).

### Frontend — what exists, what doesn't

- **Page:** `web/src/pages/Similarity.tsx` (526 lines). Module-level layout cache: `cachedGraphData` + `cachedThreshold` at file top — survives re-mount. State includes threshold (debounced 400 ms), source filter set, graph search, selected node.
- **Tab pattern to model after:** `web/src/pages/Groups.tsx:162-200`. `useState<GroupTab>` (no URL sync), `border-b-2` underline buttons, conditional render of tab bodies. Worth upgrading the new page to `?tab=` query-param sync so deep-links + e2e are stable.
- **Routes are already lazy:** `web/src/App.tsx:5-17` uses `lazy(() => import('./pages/…'))` for every page already. Adding another `lazy` for the Graph tab inside Similarity is consistent.
- **Vite chunking:** `web/vite.config.ts:15-23` groups `recharts + d3` together. **This is the load-bearing chunking issue** — splitting `d3` out is required, otherwise the lazy Graph tab still ships d3 inside `charts-*.js` that other pages already pull.
- **Reusable components:** `Badge` (`components/Badge.tsx`), `Skeleton` (`components/Skeleton.tsx`), `DataTable` (`components/DataTable.tsx` — generic, sortable, paginated), `Modal` (now with `role="dialog"` aria), `FeatureSelector`. Empty-state pattern is inline per page (centered flex with title + subtitle), not extracted.
- **API client:** `web/src/api.ts:258-263` for similarity, `web/src/api.ts:180-184` for `ai.discover`. Inline-typed cached `request<T>` calls. No `any`.
- **i18n:** flat keys under `nav.*` / `actions.*` / `empty.*` / `tooltip.*` (`web/src/locales/{en,vi}/similarity.json`). Technical terms (Feature, Schema, Drift, Score) stay English in vi/.
- **AI mocking for e2e:** `web/tests/e2e/fixtures/mock-ai.ts` already exposes `mockSuggestFeatures(specs)` that fulfils `/api/ai/discover` with a synthetic `{existing_features, ...}` shape. Reusable.

---

## Endpoint plan

Two new endpoints, both additive. Existing endpoints unchanged.

### 1. `GET /api/features/duplicates` — new

**Route:** `featcat/server/routes/features.py` (new handler near existing similarity routes).

**Query params:**

- `threshold: float = 0.7` (validated 0.4–0.95)
- `limit: int = 100` (1–500)
- `source: str | None = None` — comma-separated list of source names. Empty/missing → no filter (cross-source default). Single value → both sides of every pair must match that source. Multiple values → both sides must be in the set. Parsed as `str | None` on the request, split on comma, whitespace stripped, empty list treated as "no filter".

**Default behavior (no `source` param):** returns pairs across all sources, **including cross-source pairs**. This is the primary dedup workflow — finding the same logical feature implemented twice in different sources.

**Response model** (new pydantic):

```python
class DuplicateReason(BaseModel):
    code: Literal['name_similarity', 'schema_match', 'distribution_match', 'semantic_match']
    detail: str  # e.g. "shared tokens: user, session" or "both int64, mean within 5%"

class FeatureBrief(BaseModel):
    id: str
    name: str
    dtype: str
    source: str
    has_doc: bool

class DuplicatePair(BaseModel):
    a: FeatureBrief
    b: FeatureBrief
    score: float           # overall similarity 0..1
    reasons: list[DuplicateReason]

class DuplicatesResponse(BaseModel):
    threshold: float
    pairs: list[DuplicatePair]
    total: int                   # before limit
    cached_at: str | None        # ISO timestamp of when this result was computed (cache hit) or None on a fresh compute
    summary: str | None = None   # populated when scale cap triggers (see "Scale and limits" below)
```

The `cached_at` field powers a frontend "Computed N minutes ago · Refresh" affordance — users can force re-compute when they know the catalog changed (since we're explicitly not adding mutation hooks in this PR; see "Caching" below).

**Implementation** — new backend helper `LocalBackend.find_duplicate_pairs(threshold, limit, sources) -> tuple[list[DuplicatePair], int]`:

1. Build the TF-IDF matrix once over all features (reuse the corpus logic from `_find_similar_tfidf`, lines 1601-1655). Refactor that helper to expose `_build_corpus(features) -> (vectorizer, matrix, feature_ids)` so both `find_similar_features` and `find_duplicate_pairs` share it. DRY win, small.
2. Compute the cosine-similarity matrix once. For all `(i, j)` with `i < j` and `score >= threshold`, emit a pair.
3. For each candidate pair, attach reason codes:
   - `semantic_match` — always present (it's why the pair surfaced). Detail = TF-IDF cosine rounded to 3 decimals.
   - `name_similarity` — if Jaccard of `name.replace('.', '_').split('_')` token sets ≥ 0.5. Detail = shared tokens.
   - `schema_match` — same `dtype`. Detail = the dtype.
   - `distribution_match` — **numeric-only**: applies only when *both* features have numeric `mean` and `std` values in their `stats` dict, and the values are within 10% relative tolerance. Detail = "mean Δ=4%, std Δ=8%". Categorical / string features will never receive this reason code; they rely on `name_similarity`, `schema_match`, and `semantic_match` only.
4. Sort pairs by `score` desc; secondary tiebreak by number-of-reasons desc; cap at `limit`.

**Sorting rule:** primary `score` desc, secondary `len(reasons)` desc. Two pairs with identical score and identical reason count keep insertion order from the upper-triangle scan (stable).

**Scale and limits:**

> The current implementation builds an in-memory cosine matrix over all features. Tested up to ~2000 features (~2M candidate pairs, ~16 MB matrix). Above that, memory and compute time become bottlenecks.
>
> **Hard cap:** if `len(features) > 2000`, the endpoint returns `200` with `pairs=[]`, `total=0`, and a `summary` field reading `"Catalog too large for in-memory duplicate detection (N features). Future work: batched cosine or FAISS index."` Log a warning at WARN level. Test: `test_returns_empty_with_summary_when_catalog_exceeds_cap`.

**Caching:** in-process `cache_set(f"duplicates:{threshold}:{','.join(sorted(sources)) or '*'}:{limit}", value, ttl=300)` via `featcat/server/cache.py`. **No** automatic invalidation on catalog mutation in this PR (see "Cache invalidation" below). Stale results are bounded by the 5-minute TTL and surfaced via `cached_at`.

**Edge cases (tests must cover):**

- `test_returns_empty_on_empty_catalog`
- `test_returns_empty_on_single_feature`
- `test_finds_obvious_pair_above_threshold`
- `test_threshold_filters_low_scores`
- `test_pair_deduplicated_a_b_b_a` — never returns both `(a, b)` and `(b, a)`
- `test_no_filter_returns_cross_source_pairs` — seed two near-identical features in different sources, default call returns the pair
- `test_multi_source_filter_scopes_to_set` — filter `billing,network` excludes pairs touching `device`
- `test_single_source_filter_excludes_cross_source` — filter `billing` returns only billing-billing pairs
- `test_reason_codes_attached_for_schema_match` — same dtype → schema_match present
- `test_reason_codes_attached_for_distribution_match` — numeric stats within 10% → distribution_match present
- `test_distribution_match_skipped_for_categorical` — string-typed features with no mean/std never get distribution_match
- `test_cache_hit_returns_same_payload_with_cached_at_set`
- `test_threshold_validation_below_min_returns_422`
- `test_threshold_validation_above_max_returns_422`
- `test_returns_empty_with_summary_when_catalog_exceeds_cap`

### 2. `POST /api/features/recommend` — new

**Route:** `featcat/server/routes/features.py`.

**Request:**

```python
class RecommendRequest(BaseModel):
    use_case: str = Field(min_length=3, max_length=500)
    top_k: int = Field(default=10, ge=1, le=50)
    use_llm: bool = True   # client may force the deterministic path
```

**Response model:**

```python
class FeatureMatch(BaseModel):
    feature: FeatureBrief
    score: float
    reason: str

class RecommendResponse(BaseModel):
    use_case: str
    method: Literal['llm', 'tfidf', 'embedding']
    matches: list[FeatureMatch]
    summary: str | None = None
```

**Server is the single owner of the LLM-vs-TFIDF decision. The client never retries.**

**Implementation:**

1. If `use_llm=True` and `request.app.state.llm is not None`: call `DiscoveryPlugin.execute(db, llm, use_case=...)` wrapped in `asyncio.wait_for(..., timeout=8.0)`. Map `existing_features` to `FeatureMatch` (resolving names → FeatureBrief by DB lookup). Set `method='llm'`. Pass the plugin's `summary` through.
2. **Fall back to the TF-IDF path within the same request** when ANY of these happens:
   - `asyncio.TimeoutError` after 8 seconds.
   - The plugin raises.
   - The plugin returns an empty `existing_features` list.
   - LLM is unavailable (`app.state.llm is None`).
   - The client sets `use_llm=False`.
   Set `method='tfidf'` and populate `summary` with the fallback reason — one of: `"LLM unavailable, ranked by keyword similarity"`, `"LLM timed out after 8s, ranked by keyword similarity"`, `"LLM returned no matches, ranked by keyword similarity"`. When the client opted out, `summary` reads `"Ranked by keyword similarity (LLM bypassed)"`.
3. TF-IDF path — new backend helper `LocalBackend.recommend_by_text(use_case: str, top_k: int) -> list[(Feature, float)]`:
   - Reuse the corpus from the new shared `_build_corpus` helper.
   - `vectorizer.transform([use_case])` → 1×N. Compute cosine vs corpus.
   - Return top-k features with cosine > 0.05. `reason` populated as `"Keyword similarity {score:.2f}"`.
4. Postgres + embeddings is intentionally out of scope for this PR. The `method='embedding'` literal in the response type is reserved for a future enhancement; the handler in this PR never returns it.

The client sends one request and renders whatever `method` the server returns. No client-side retries with a different `use_llm` value.

**Caching:** TTL 600s keyed on `recommend:{sha256(use_case)[:16]}:{top_k}:{use_llm}`. The LLM path *additionally* goes through `ResponseCache` already inside `DiscoveryPlugin`.

**Edge cases (tests must cover):**

- `test_llm_path_uses_discovery_when_available` — mock LLM returns `existing_features`, response method is `'llm'`.
- `test_tfidf_fallback_when_llm_none` — `app.state.llm = None`, assert `method='tfidf'` and summary contains "LLM unavailable".
- `test_force_use_llm_false_skips_llm` — LLM available but bypassed; assert `method='tfidf'` and summary contains "LLM bypassed".
- `test_llm_timeout_falls_back_to_tfidf` — mock LLM that sleeps 9s; assert `method='tfidf'` and summary contains "LLM timed out".
- `test_llm_empty_result_falls_back_to_tfidf` — mock LLM returns `{"existing_features": []}`; assert `method='tfidf'` and summary contains "no matches".
- `test_returns_empty_on_empty_catalog`
- `test_top_k_caps_results`
- `test_validation_use_case_too_short` — 2 chars → 422.

### 3. Existing endpoints — unchanged

`/api/features/similarity-graph` and `/api/features/by-name/similar` stay byte-for-byte identical. The new Graph tab calls them the same way.

### Cache invalidation — explicitly out of scope for this PR

**Phase 1 first step:** check whether `invalidate('/api/features/similarity-graph')` or equivalent prefix invalidation already exists at mutation sites (feature upsert in `LocalBackend.upsert_feature`, scan-bulk completion in `BulkScanResponse` post-write, doc generate, status change, source delete).

- **If hooks exist** at those sites: add `invalidate('duplicates:')` and `invalidate('recommend:')` calls right next to them. Minimal addition.
- **If hooks do not exist**: do NOT add new invalidation infrastructure in this PR. Accept TTL-based staleness (5 min for duplicates, 10 min for recommend). The frontend surfaces the staleness via `cached_at` + a manual "Refresh" button on the Duplicates tab.

Follow-up ticket: "Cache invalidation hooks at catalog mutation sites" (documented in "Out of scope" below).

---

## Component plan

```
web/src/pages/Similarity.tsx                    (rewritten — thin tab shell)
web/src/pages/similarity/                       (new directory)
├── DuplicatesTab.tsx                           (new — default tab)
├── RecommendationsTab.tsx                      (new)
└── GraphTab.tsx                                (new — current Similarity.tsx body, moved verbatim)

web/src/components/similarity/                  (new)
├── DuplicatePairRow.tsx                        (renders one pair: two FeatureBrief blocks side by side + score + reason chips)
└── ReasonChip.tsx                              (small pill, color-coded by reason code)
```

Reused (no changes):

- `Badge`, `Skeleton`, `DataTable` (DuplicatesTab uses it for the pair table with sortable score column)
- `Modal` (Recommendations may show a feature detail on click — same modal pattern as Features page; out of scope, defer)
- `Layout` (page chrome unchanged)

**Tab nav** — modeled on `Groups.tsx:162-200`, but with URL sync:

- `useSearchParams()` → `tab` param (`duplicates|recommendations|graph`). Default to `duplicates` on missing/invalid.
- Each tab body is rendered conditionally. Sibling tabs **mount on click**, then stay mounted (keep their state and any module-level cache like the existing `cachedGraphData`).
- Switching tabs updates the URL via `setSearchParams({ tab }, { replace: true })`.

**Lazy load:**

```ts
const GraphTab = lazy(() => import('./similarity/GraphTab'))

// inside the render:
{tab === 'graph' && (
  <Suspense fallback={<Skeleton className="min-h-[500px]" />}>
    <GraphTab />
  </Suspense>
)}
```

The shell page (Similarity.tsx) imports ONLY `DuplicatesTab` + `RecommendationsTab` statically. `GraphTab` and its `d3` dependency only resolve when `tab === 'graph'`.

**Graph tab redirect note** — at the top of `GraphTab.tsx`, a small `border-l-4 border-brand-muted p-3 text-xs` callout reads (en): *"The graph view is exploratory. For action-oriented workflows, see Duplicates or Recommendations."* (i18n key `similarity.graph_note`.)

**Duplicates row affordances:** `Dismiss` button only. A single TODO comment in `DuplicatePairRow.tsx` references the deferred "Mark as related / Merge into" actions. No stub buttons.

---

## State and caching plan

| Concern | Location | Lifetime |
| --- | --- | --- |
| Active tab | URL search param | Browser session (URL-driven) |
| Duplicates result | `useState` in `DuplicatesTab` | Tab-mount lifetime |
| Duplicates threshold | `useState` in `DuplicatesTab` (slider lives in the tab, not the page header) | Tab-mount lifetime |
| Dismissed pairs | `Set<string>` in `useState`, keyed `${a.id}|${b.id}`, persisted to `localStorage` `featcat:similarity:dismissed-pairs` | Across reloads, until user clears |
| Recommendations query + result | `useState` in `RecommendationsTab` | Tab-mount lifetime |
| Graph data + layout | existing module-level `cachedGraphData` / `cachedThreshold` (preserved as-is) | Module lifetime — survives tab-switch unmount/remount of GraphTab body, **does NOT** survive a full page reload |

**Per-tab fetch gating:** each tab calls `api.*` in its own `useEffect`. Switching to a tab triggers its fetch the first time only (subsequent visits use the local state). Returning to Graph never re-runs the D3 simulation thanks to the existing module cache.

---

## i18n plan

All new keys under `similarity` namespace, en + vi files.

```jsonc
{
  "tabs": {
    "duplicates": "Duplicates",
    "recommendations": "Recommendations",
    "graph": "Graph"
  },
  "duplicates": {
    "subtitle": "Pairs of features that look like the same thing.",
    "threshold_label": "Similarity threshold",
    "score_label": "Score",
    "computed_at": "Computed {{when}}",
    "refresh": "Refresh",
    "reasons": {
      "name_similarity": "Name",
      "schema_match": "Schema",
      "distribution_match": "Distribution",
      "semantic_match": "Semantic"
    },
    "actions": {
      "dismiss": "Dismiss",
      "view_a": "View",
      "view_b": "View"
    },
    "empty": {
      "title": "No likely duplicates",
      "subtitle": "Lower the threshold to surface more candidate pairs."
    }
  },
  "recommendations": {
    "subtitle": "Describe a use case in natural language. We'll rank existing features.",
    "input_placeholder": "e.g. churn prediction for telecom customers",
    "submit": "Find features",
    "method": {
      "llm": "AI ranked",
      "tfidf": "Keyword ranked",
      "embedding": "Semantic ranked"
    },
    "empty": {
      "title": "No matches",
      "subtitle": "Try a different phrasing or broader terms."
    },
    "prompt": "Type a query above to start."
  },
  "graph_note": "The graph view is exploratory. For action-oriented workflows, see Duplicates or Recommendations."
}
```

**Convention:** technical terms (Feature, Schema, Drift, Score, TF-IDF) stay English in vi/. The vi `tabs` block uses "Trùng lặp / Đề xuất / Đồ thị". Reason labels stay short English ("Name / Schema / Distribution / Semantic") in both because the table header is tight.

---

## Test plan

### Backend

`tests/test_duplicates.py` (new) — covers all the duplicate edge cases listed in the endpoint section above.

`tests/test_recommend.py` (new) — covers all the recommend edge cases listed in the endpoint section above, including the four fallback-trigger variants (no LLM / timeout / empty result / use_llm=False).

### Frontend E2E (Playwright)

`web/tests/e2e/similarity-graph.spec.ts` (rewrite — file renames to `similarity.spec.ts`):

- `default tab is Duplicates on first visit` — `goto('/similarity')`, assert `?tab=duplicates` selected; the duplicates subtitle is visible.
- `switching to Graph triggers chunk fetch` — record network responses with `page.on('response')`; click Graph tab; assert at least one response URL matches `/assets/(?:d3|graph-tab|GraphTab).*\.js`. Belt-and-suspenders fallback: assert the SVG/threshold slider appears AFTER click, not before.
- `graph cache survives tab toggle` — go to Graph, capture initial render; switch to Duplicates; switch back to Graph; assert the threshold value and node count match the initial state (module cache hit). Surrogate assertion: no new `/api/features/similarity-graph*` request fires on the second visit.
- `recommendations returns mocked results` — `mockAi.mockSuggestFeatures([...])`; type in the input; submit; assert ranked rows render with the mock feature names.
- `recommendations falls back to TF-IDF without LLM` — by default mock-ai returns 503; submit query; assert the page shows results with `method='tfidf'` label and the summary banner reads "LLM unavailable…". (The server does the fallback; client just renders what comes back.)
- `empty duplicates state` — bump threshold slider to 0.99; assert empty-state title appears.

All AI mocks reuse `fixtures/mock-ai.ts`; no real LLM.

---

## Bundle plan

**Vite config change** — `web/vite.config.ts` `manualChunks`:

```diff
- 'charts': ['recharts', 'd3'],
+ 'charts': ['recharts'],
+ 'd3': ['d3'],
```

**Verification:**

1. `bun run build` and inspect `featcat/server/static/assets/` listing.
2. Confirm `d3-*.js` exists as its own file via:
   ```bash
   ls -lh featcat/server/static/assets/d3-*.js
   ls -lh featcat/server/static/assets/{GraphTab,similarity}*.js
   ```
   Expect: `d3-*.js` ~150–200 kB. `GraphTab-*.js` ~5–15 kB.
3. Bundle size before/after — record in PR description. Expectation:
   - Before: Similarity initial chunk pulls `charts-*.js` (~431 kB combined recharts + d3).
   - After: Similarity initial chunk pulls only `charts-*.js` (~250 kB, recharts only). Graph tab click then fetches `d3-*.js` (~200 kB) + `GraphTab-*.js` (~10 kB). Recharts may also drop from the initial Similarity wave if no recharts components are used in Duplicates/Recommendations (likely the case).
4. **Authoritative manual check** — browser DevTools Network panel: load `/similarity`, no d3 chunk requested; click Graph tab, d3 chunk requested.

**Caveat:** Lineage (`web/src/pages/Lineage.tsx`) also uses d3. After the split, navigating to Lineage will pull the new d3 chunk. Acceptable tradeoff — Lineage is rarely the first page hit, and Similarity → Lineage transitions reuse the cached chunk.

---

## Confirmed decisions

1. **Threshold defaults** — asymmetric. Duplicates defaults to 0.7 (precision-first). Graph defaults to 0.3 (recall-first). Different goals justify different defaults.
2. **Dismissed pairs persistence** — local-only via `localStorage`. Cross-machine sync is out of scope.
3. **Reason code ranking** — sort by score desc, secondary tiebreak by number-of-reasons desc.
4. **Recommendations fallback** — server-side only. 8-second internal timeout. Client renders the returned `method` without retrying.
5. **Lineage d3 chunk impact** — acceptable tradeoff.
6. **Duplicate row actions** — Dismiss only, single TODO comment for future Mark-as-related / Merge-into.

## Translation confirmations needed during review

- `actions.dismiss` → vi "Bỏ qua". Default OK; flag during PR review if not.
- Any other new vi terms flagged during implementation.

---

## Out of scope (deferred)

- **Cache invalidation hooks at catalog mutation sites** — separate follow-up ticket. This PR uses TTL-only staleness and surfaces `cached_at` + a manual Refresh button instead.
- Persisting dismissed pairs to a backend table.
- "Mark as related" / "Merge into" actions on a pair.
- Recommendations result actions (e.g. add to group from the result row).
- Server-side pagination of duplicates beyond the 500-cap (the 2000-feature catalog hard cap is the relevant boundary for now).
- Background job that pre-computes the duplicates report (`monitor_check`-style cron).
- pgvector / embedding path for `recommend` (the `method='embedding'` literal is reserved for a future enhancement).
- FAISS / batched-cosine implementation for catalogs above 2000 features.

---

## Phase sequence after approval

1. **Backend**: build `_build_corpus` extraction, `find_duplicate_pairs`, `recommend_by_text`, new routes, scale-cap handling, optional cache-invalidation hook additions (only if mutation sites already invalidate), and the full test suites for both endpoints. One commit.
2. **Vite config**: split d3 chunk + verify build output via the `ls` checks above. One tiny commit, isolated for easy revert.
3. **Frontend shell**: tab shell + URL sync + lazy-load wiring + GraphTab move (verify it renders identically). One commit.
4. **DuplicatesTab + RecommendationsTab** implementations, including the `cached_at` + Refresh button on Duplicates. One commit.
5. **e2e spec rewrite**. **Phase 5 is gated on `bun run test:e2e` passing cleanly on `main` before this branch is rebased onto it.** If the Playwright setup is still being stabilized when this PR reaches phase 5, defer the e2e spec to a follow-up PR and ship phases 1–4 + 6 (without e2e) first. Backend pytest coverage is sufficient to merge in that case.
6. **i18n + final polish + bundle-size note** in PR description. One commit.

Each phase ends green: `make test` + `bunx tsc --noEmit` + `bun run build` (+ `bun run test:e2e` from phase 5 onwards, conditional on the gating above).

## Human checkpoints

- **After Phase 1 (backend)** — pause for review of the new endpoints' API shape via curl tests against a running dev server. Confirm response models match what the frontend will need before any UI is built.
- **After Phase 2 (vite split)** — pause to verify bundle output. If the d3 chunk doesn't split as expected, revert and investigate before continuing.
- **After Phase 3 (shell + GraphTab move)** — pause to verify the graph still renders identically to the current implementation. This is the highest-risk move (existing module cache, D3 lifecycle).
- **Before opening PR** — verify all manual checks in the Bundle plan section, capture before/after bundle sizes for the PR description.
