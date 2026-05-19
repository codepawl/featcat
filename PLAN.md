# Plan: Fix four outstanding issues in featcat

> Will be copied to `PLAN.md` at repo root once approved (plan mode only allows editing this file).

## Context

Four issues were reported. Investigation revealed that **two** of them
(Extracted Features select, Data Sources bulk delete) are real code bugs in
`web/src/pages/Sources.tsx`; **one** (chatbot `search_features`) is partly real
(the catalog has lexical-only FTS5 search today even though embeddings
infrastructure exists from T1.2) but the user-visible failure on the dev box
is data-driven — the local catalog only has `client_logs` features, none about
billing/revenue; and **one** (`instructor`/`zod-stream`/`openai` peer dep
conflict) doesn't exist — none of those packages are in `web/package.json`
and `bun install` runs clean.

Decisions (locked in via AskUserQuestion):

- **Issue 4**: Drop. Document as non-issue; no commit.
- **Issue 3**: Wire hybrid lexical+semantic search by composing existing pieces.
  No new demo data. Embeddings are best-effort: rows without an embedding get
  lexical-only contribution. CLI `featcat embeddings backfill` (already exists
  at `featcat/cli.py:3397`) remains the way to populate embeddings.
- **Issue 2**: Add `POST /api/sources/bulk/delete` mirroring
  `/api/features/bulk/delete`.
- **Issue 1**: Wire selection state in the Source detail panel so
  `FeatureSelector` is interactive there, matching other call sites.

Order of commits (per user's spec): Issue 4 first (no-op), then 3, then 1, then 2.

---

## Issue 1 — Extracted Features select button

### Root cause

- **File:** `web/src/pages/Sources.tsx:778-793`, with `EMPTY_SELECTION` /
  `NOOP_ON_CHANGE` constants defined at lines 811-813.
- **Current code:**
  ```tsx
  <FeatureSelector
    features={featureItems}
    selected={EMPTY_SELECTION}
    onChange={NOOP_ON_CHANGE}
    showAISuggest={false}
    maxHeight="280px"
  />
  ```
- **Why it fails:** the picker is rendered with a frozen empty `Set` and a
  no-op `onChange`. Checkbox clicks bubble to `handleClick(f.spec, e)` inside
  `FeatureSelector.tsx`, which calls `onChange(next)` — but because `onChange`
  is a no-op, the parent state never updates and on the next render the
  `selected` prop is still empty, so every row looks unchecked. Shift+click
  range, select-all-by-source, show-selected-only, and AI suggest all read
  through the same `selected` prop, so they all appear broken.
- **Comparison — working call sites:** `Groups.tsx:349-357` (AddFeaturesModal),
  `Features.tsx:1160` (GenerateDocsModal), `ExportModal.tsx:171-183` — all wire
  real `useState<Set<string>>` to `selected` and pass the setter to `onChange`.

### Fix

- Replace the two module-scope stubs with real state local to `SourceDetail`.
- Drop the now-stale comment "read-only FeatureSelector" on line 778; replace
  with a one-line comment only if non-obvious context remains (likely none).
- No new external action — the selection is a transient picker state, same
  as it is inside any FeatureSelector. Out of scope: hooking the selection
  into a downstream action (Add to group, Bulk tag, …). If the user wants
  that, it's a follow-up.

### Files

- Modify: `web/src/pages/Sources.tsx:778-793, 811-813`

### Risk / scope

- Single component, no shared-state or backend changes. Re-renders the
  picker with a live `Set` instead of a frozen one — well within React's
  expected pattern.

### Verification

- `cd web && bun run lint && bun run typecheck && bun run build`
- Manual: load `/sources/<name>` → click checkboxes (single, shift+click
  range, select-all-by-source); confirm checkbox state visibly updates and
  "Show selected only" toggles the row list.

---

## Issue 2 — Data Sources bulk delete

### Root cause

- **File:** `web/src/pages/Sources.tsx:280-302` (bulk-action toolbar).
- **Current behavior:** when `selectedForScan.size > 0`, toolbar shows
  only Cancel + Scan now. There is no Delete button. The backend has
  single-source delete (`DELETE /api/sources/{name}` at
  `featcat/server/routes/sources.py:221-236`) but no bulk-delete endpoint.

### Fix

Backend:
- Add `POST /api/sources/bulk/delete` in
  `featcat/server/routes/sources.py` (or split into a new
  `featcat/server/routes/sources_bulk.py` if you prefer — but appending to
  `sources.py` keeps the surface together; mirroring `bulk.py`'s style is
  the bigger win).
- Body: `BulkDeleteSourcesRequest{names: list[str] (min_length=1), confirm: bool = False}`.
  Mirror the `BulkDeleteRequest` shape in `featcat/server/routes/bulk.py:75-89`.
- Validation: `confirm` must be `true` (400 otherwise). Pre-check every name
  via `db.get_source_by_name(name)`; if any are missing, raise 400 with
  `{"message": "Some sources do not exist.", "invalid_names": [...]}` —
  all-or-nothing, matching `bulk.py`'s `_validate_or_400` pattern.
- Delete each via the existing `db.delete_source(name)` and accumulate
  `features_removed`. Single round-trip, no new backend method.
- Invalidate `sources:`, `features:`, `dashboard:` caches once at the end.
- Response shape `DeleteSourcesBulkResponse{deleted: list[str], features_removed: int, requested: int}`.

Frontend API client:
- Add `api.sources.deleteBulk({names, confirm})` in `web/src/api.ts`
  alongside the existing `api.sources.delete` (around line 191), and
  export a `DeleteSourcesBulkResult` type matching the response.

Frontend UI:
- Modify `Sources.tsx:280-302` (the bulk-action toolbar): insert a Delete
  button between Cancel and Scan now. Use `Trash2` (already imported,
  `Sources.tsx:4`).
- Add `bulkDeleteOpen` and `bulkDeleting` state. On Delete click, open
  the existing `ConfirmDialog` component (already imported,
  `Sources.tsx:15`) with body text along the lines of
  `delete_bulk_confirm` (new i18n key) — "Delete {N} sources and all their
  features?".
- On confirm: call `api.sources.deleteBulk({names: Array.from(selectedForScan), confirm: true})`,
  invalidate `'/sources'`, `'/features'`, `'/stats/by-source'`, clear
  `selectedForScan`, close detail if a deleted source was selected, then
  `load()`.
- New i18n keys: `actions.delete_selected`, `dialogs.bulk_delete_title`,
  `dialogs.bulk_delete_body`, `dialogs.bulk_deleting`. Add to all language
  bundles under `web/public/locales/*/sources.json`.

### Files

- Modify: `featcat/server/routes/sources.py` (add endpoint + Pydantic models)
- Modify: `web/src/api.ts` (add `deleteBulk` method + type)
- Modify: `web/src/pages/Sources.tsx` (toolbar + confirm dialog + state)
- Modify: `web/public/locales/{en,vi}/sources.json` (new keys)
- Add: `tests/test_sources_routes.py` cases for bulk-delete:
  success, missing-name 400, confirm=false 400, empty-list 422 (Pydantic
  `min_length`).

### Reuse (do not rebuild)

- `db.delete_source(name)` — `featcat/catalog/local.py` (already cascades
  features, docs, baselines, monitoring, usage, group memberships, lineage
  edges, action items).
- `BulkDeleteRequest` shape and `_validate_or_400` helper pattern in
  `featcat/server/routes/bulk.py`. Mirror — don't reuse the helper across
  routers; it's private to that module.
- `invalidate(prefix=...)` from `featcat/server/cache.py`.
- `ConfirmDialog`, `Trash2`, `Modal` (already imported in `Sources.tsx`).

### Risk / scope

- New endpoint, no behavior change for existing routes. The cascade rules
  in `delete_source` are well-tested
  (`tests/test_sources_routes.py:56-82`). Risk is partial-failure if a
  source's delete blows up mid-loop — surface as a 500 with a
  `deleted: [...]` list of what did succeed. (Or: do all the per-source
  deletes inside one SA transaction. `LocalBackend.delete_source` uses its
  own session, so reusing it doesn't get us a single transaction; deferring
  that polish — partial-failure rollback adds complexity the spec doesn't
  ask for. Document the trade-off in the response shape and move on.)

### Verification

- `uv run pytest tests/test_sources_routes.py -v` — all new + existing
  cases green.
- `uv run ruff check . && uv run mypy .`
- `cd web && bun run lint && bun run typecheck && bun run build`
- Manual: with the server running, select 2+ sources on
  `http://localhost:8000/sources`, click Delete, confirm the modal,
  observe deletion + list refresh + cleared selection.
- `curl` smoke:
  ```bash
  curl -s -X POST http://localhost:8000/api/sources/bulk/delete \
       -H 'Content-Type: application/json' \
       -d '{"names":["nonexistent_a","nonexistent_b"],"confirm":true}' | jq
  # → 400 with invalid_names
  ```

---

## Issue 3 — Chatbot `search_features` hybrid lexical+semantic

### Root cause

- **Tool definition** (`featcat/ai/tools.py:9-22`) calls itself a "Keyword
  search" — schema and description only commit the LLM to lexical recall.
- **Executor** (`featcat/ai/executor.py:44-53`) calls
  `backend.search_features(query)`.
- **Backend** (`featcat/catalog/local.py:1109-1124`) delegates to
  `full_text_search` → SQLite FTS5 (`_fts_sqlite`,
  `featcat/catalog/local.py:892-943`) or Postgres tsvector
  (`_fts_postgres`, lines 841-890). **Lexical only.** Embeddings are not
  consulted in this path even though:
  - `featcat/ai/embeddings.py` exists with `embed_text` + `embed_batch`
    + `update_missing_embeddings` (T1.2).
  - `LocalBackend.search_by_embedding`
    (`featcat/catalog/local.py:2360-2397`) implements pgvector top-K
    cosine but returns `[]` on SQLite by design.
  - `_find_similar_pgvector` and `_find_similar_tfidf` exist for the
    per-feature similarity case, but neither is wired into the free-form
    text-search path.
- **System prompt** (`featcat/ai/agent.py:49`) describes
  `search_features` as "Keyword/topic search ('features về churn')" —
  consistent with the (broken) framing.
- **Why "billing"/"tiền" return nothing on the dev box:** the local
  `catalog.db` contains 95 features from `client_logs`, none with names,
  descriptions, tags, or column names matching billing/revenue. That's
  data, not a code bug. But the broader claim — that search ignores
  semantic signal — is real.

### Fix

- Add `LocalBackend.search_by_embedding` SQLite override that loads
  `(id, name, dtype, embedding)` for rows where `embedding IS NOT NULL`,
  computes cosine in numpy (`numpy` is already a dependency; embeddings
  are L2-normalized at write time per
  `embed_batch`'s `normalize_embeddings=True` flag, so cosine = dot
  product), and returns top-K in the same shape as the Postgres path:
  `[{id, name, dtype, similarity}]`. Move the existing Postgres-only
  body into `_search_by_embedding_pg`; dispatch on `self.backend` in
  the public method. Acceptable on SQLite up to a few thousand features
  (sub-100ms for 1k×384 floats); document the scale ceiling in the
  docstring so it's not a surprise. The pure Postgres-only signature in
  `backend.py:273-281` stays put — SQLite override is more specific, not
  a contract change.
- Add `LocalBackend.hybrid_search(query, limit=10) -> list[Feature]` that:
  1. Runs `self.full_text_search(query, limit=lex_k)` → list of `{id, …, rank}`.
     `lex_k = max(limit * 3, 30)` so the lexical candidate pool is wide
     enough that merging meaningfully reorders results.
  2. If `embeddings.embeddings_available()`:
     - `vec = embeddings.embed_text(query)` (wrapped in `try/except RuntimeError`
       to keep search alive when the model fails to load — log warning, skip
       semantic). No bare `except`.
     - `sem = self.search_by_embedding(vec, top_k=lex_k)` → `[{id, …, similarity}]`.
     If embeddings not available, `sem = []`.
  3. Merge by Reciprocal Rank Fusion: score(id) = sum over each list of
     `1.0 / (60 + rank)` (k=60 is the standard RRF constant). RRF is
     well-suited here because lexical BM25 and cosine sim live on
     different scales — RRF only uses ordinal ranks, so no normalization.
  4. Top-`limit` IDs by RRF score, fetched in bulk via
     `_features_by_ids`, returned in score order.
  5. If both lists are empty, return `[]`. If only lexical returned hits,
     behavior is identical to today.
- Wire `LocalBackend.search_features(query)` to call `hybrid_search(query)`
  (was: delegated straight to `full_text_search`). Default `limit=10`
  matches the executor's top-10 cap, so this doesn't widen response
  payloads.
- Tighten tool description in `featcat/ai/tools.py:9-22`:
  - name unchanged.
  - description: "Hybrid lexical+semantic search across feature names,
    descriptions, tags, and column names. Accepts free-form Vietnamese or
    English queries; does NOT require exact match — phrases like 'tiền',
    'billing', 'doanh thu', 'churn risk' all work. Returns top-10 matches
    ranked by combined relevance. For structured filters (by source /
    has_doc / dtype) use list_features."
  - parameter description: "Free-form query in any language; partial
    phrases are fine."
- System prompt (`featcat/ai/agent.py:49`): swap "Keyword/topic search"
  for "Hybrid lexical+semantic search" so the routing example matches
  the new tool description. One-line change.
- **Backfill ergonomics:** the existing CLI `featcat embeddings backfill`
  (`featcat/cli.py:3397`, wraps `embeddings.update_missing_embeddings`)
  is the answer for catalogs whose features predate T1.2. Reference it
  in the tool description's note: not blocking.
- **Tests:** in `tests/test_ai_executor.py` (or `tests/test_search.py` if
  that's where existing FTS tests live), add three cases:
  1. EN query "billing" on a small fixture containing a feature
     `billing.invoice_amount` — must return that feature.
  2. VI query "doanh thu" on a fixture containing
     `revenue.daily_total` (description: "doanh thu hằng ngày") — must
     return that feature, exercising the FTS5 diacritic-folding tokenizer
     and (when embeddings are available) the semantic branch.
  3. Query "xxxxnomatchxxxx" on a fixture — must return `[]`, not raise.
  Tests must NOT require `sentence-transformers` at import time. Either:
  - Patch `embeddings.embeddings_available` to return `False` for the
    plain unit test (proves the lexical-only fallback still works), AND
  - Patch `embeddings.embed_text` and the backend's `search_by_embedding`
    to a stub for the hybrid-path case (proves RRF merging works).

### Files

- Modify: `featcat/catalog/local.py` — add `_search_by_embedding_sqlite`,
  refactor `search_by_embedding` to dispatch, add `hybrid_search`, swap
  `search_features` body. ~80 new lines.
- Modify: `featcat/ai/tools.py:9-22` — description tweaks only.
- Modify: `featcat/ai/agent.py:49` — one-line prompt tweak.
- Add: `tests/test_search_hybrid.py` (or extend `tests/test_search.py`)
  with the three cases above.

### Reuse

- `featcat.ai.embeddings.embeddings_available`, `embed_text`,
  `update_missing_embeddings`.
- `full_text_search` (unchanged), `_features_by_ids`.
- `numpy` (already in deps via sklearn / pandas — verify
  `pyproject.toml` if uncertain).
- `RuntimeError` shape from `_get_model` for graceful semantic-degrade.

### Risk / scope

- `search_features` is also used by RemoteBackend (`featcat/catalog/remote.py:148`) —
  that's an HTTP client that delegates to whatever the server's
  `LocalBackend.search_features` returns, so the change is transparent
  there.
- `search_facets` (`featcat/catalog/local.py:1032-1107`) calls
  `full_text_search` directly, not `search_features` — facets stay
  lexical-only, which is correct (facets are exact filters, not
  retrieval). No regression.
- The Search page (`/api/search`) hits `full_text_search`, not
  `search_features` — unaffected by this change. Only the chatbot's
  `search_features` tool gets hybrid behavior. (Worth confirming with a
  grep before commit, but that's a route review during implementation,
  not a planning question.)
- Memory cost on SQLite: 384 floats × 4 bytes × 5k features = 7.7 MB.
  Acceptable. Documented in the docstring.

### Verification

- `uv run pytest tests/test_search.py tests/test_search_hybrid.py -v`
- `uv run ruff check . && uv run mypy .`
- `uv run pytest -x` (full suite stays green).
- Manual against the live SQLite catalog (data-limited so this won't
  surface billing/tiền hits, but it must not regress):
  ```bash
  curl -N -X POST http://localhost:8000/api/chat \
       -H 'Content-Type: application/json' \
       -d '{"message":"tìm feature về cpu","session_id":"hybrid-test-1"}'
  ```
  Expect the SSE stream to emit a `tool_call` for `search_features` and a
  `tool_result` listing CPU-related features.
- Direct backend probe:
  ```bash
  curl -s 'http://localhost:8000/api/features/search?q=cpu&limit=10' | jq '.[].name'
  ```
- If embeddings are missing on this catalog, run
  `uv run featcat embeddings backfill` once (downloads
  sentence-transformers model on first run, ~100MB) before re-probing.

---

## Issue 4 — `instructor` / `zod-stream` / `openai` peer dep conflict

### Root cause

There is no conflict. `web/package.json` contains none of those packages;
`bun install` runs with zero warnings. The frontend uses the `ai` package
(v6.0.176) and llama.cpp — not the OpenAI SDK.

### Fix

No code change. Document the finding in `FIX_REPORT.md`. If the user
wants me to scan other directories (repo root, deploy) I will, but the
investigation already covered `web/` (the only JS package directory).

### Files

- Modify: `FIX_REPORT.md` only — explain that the premise didn't reproduce
  and the steps taken to confirm.

### Verification

- `cd web && bun install 2>&1 | tail -20` — captured already, zero
  peer warnings.

---

## Verification — full plan

Run from repo root after each commit:

```bash
uv run ruff check .
uv run mypy .
uv run pytest -x
cd web && bun run lint && bun run typecheck && bun run build && cd ..
```

Then the manual checks listed under each issue.

End-of-task: write `FIX_REPORT.md` at repo root summarizing what changed,
what was verified, and any follow-ups deferred (e.g. partial-failure
rollback on bulk delete, embedding-backfill UX).
