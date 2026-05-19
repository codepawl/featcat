# Fix Report — four outstanding issues

Branch: `fix/four-issues` (off `origin/staging` @ `7edd3ae`).

Commits (4):

```
329b77b chore: ruff format test_search_hybrid.py
20f060c fix(sources): add bulk-delete endpoint and UI action
3a798ec fix(web): wire selection state in source detail FeatureSelector
0b2a89d fix(chatbot): wire hybrid lexical+semantic search in search_features
```

The plan ([PLAN.md](PLAN.md)) committed before any code was touched
documents the investigation, root causes and the design decisions
locked in via clarifying questions.

---

## Issue 1 — Extracted Features select button

**Root cause:** `web/src/pages/Sources.tsx` rendered the shared
`FeatureSelector` inside `SourceDetail` with a frozen empty `Set` and a
no-op `onChange` (the module-level `EMPTY_SELECTION` / `NOOP_ON_CHANGE`
constants). Every checkbox click ran through the picker's internal
handler but the parent state never updated, so single-click, shift+click
range, select-all-by-source and show-selected toggles all appeared dead.

**Fix:** swap in real `useState<Set<string>>(new Set())` and wire it
to `selected` / `onChange`. Removed the now-unused stubs. Added
`key={detail.source.name}` on the `SourceDetail` render so switching
sources resets the selection instead of leaking it.

**Files:** `web/src/pages/Sources.tsx`

---

## Issue 2 — Data Sources bulk delete

**Root cause:** the bulk-action toolbar (`Sources.tsx`, top of the
sources list) only offered Cancel + Scan now. The backend had
`DELETE /api/sources/{name}` but no bulk equivalent.

**Fix:**

- Backend: new `POST /api/sources/bulk/delete` in
  `featcat/server/routes/sources.py` mirroring the
  `/api/features/bulk/delete` contract. Body is `{names, confirm}`;
  validates the whole batch up-front (unknown names → 400 with
  `invalid_names`); reuses `LocalBackend.delete_source` so every cascade
  rule (features + docs + baselines + monitoring + group membership +
  lineage edges + action items) is preserved.
- Frontend: `api.sources.deleteBulk(...)` in `web/src/api.ts`, a Delete
  button next to Scan now in the bulk toolbar, and the existing
  `ConfirmDialog` for the destructive-action acknowledgement. On success
  the selection clears, caches invalidate, and if the visible detail
  panel referenced one of the deleted sources it closes itself.
- i18n: `actions.delete_selected` + `bulk_delete_modal.*` keys in both
  `en/sources.json` and `vi/sources.json`.
- Pytest: 4 new cases (`tests/test_sources_routes.py::TestBulkDeleteSources`):
  cascade success, unknown-name 400, `confirm: false` 400, empty-list 422.

**Files:** `featcat/server/routes/sources.py`,
`tests/test_sources_routes.py`, `web/src/api.ts`, `web/src/pages/Sources.tsx`,
`web/src/locales/{en,vi}/sources.json`.

---

## Issue 3 — Chatbot `search_features` hybrid search

**Premise correction:** the user's framing mentioned "TF-IDF + pgvector
hybrid" and named the migration `d6e943d39311`. The migration is real
(T1.2 embedding column + `featcat/ai/embeddings.py` exist), but
`search_features` had never been wired to consult embeddings — it
delegated straight to FTS5/tsvector. The user-visible failure on the
dev box ("billing"/"tiền" returning nothing) is data-driven: the local
`catalog.db` only has 95 `client_logs` features, none matching those
terms. The underlying code complaint — search ignores semantic signal
— is real and addressed here.

**Fix:**

- New `LocalBackend.hybrid_search(query, limit=10)` in
  `featcat/catalog/local.py`: pulls `max(limit*3, 30)` lexical
  candidates from `full_text_search` and (when embeddings are available)
  the same many semantic candidates from `search_by_embedding`. Merges
  them via Reciprocal Rank Fusion with k=60. RRF consumes ordinal ranks
  only — BM25 scores and cosine similarities never have to live on the
  same scale.
- `search_features` now delegates to `hybrid_search` (the abstract
  contract on `CatalogBackend` is unchanged; `RemoteBackend` keeps
  delegating to the server which now serves the hybrid result).
- `search_by_embedding` gained a SQLite branch
  (`_search_by_embedding_sqlite`) that reads JSON-encoded embeddings via
  the ORM TypeDecorator and computes cosine in numpy. Memory ceiling:
  ~7.5 MB for 5k×384 float32 — documented inline. Postgres still uses
  pgvector's `<=>` operator.
- Graceful degrade: if `sentence-transformers` isn't installed, the
  embedding model fails to load, or no row has an embedding, the result
  reduces to lexical-only without raising.
- Tool schema (`featcat/ai/tools.py`) and the system-prompt one-liner in
  `featcat/ai/agent.py` were updated so the LLM stops calling the tool
  "keyword search".
- Tests: `tests/test_search_hybrid.py` (8 cases) covers EN/VI/no-match
  in lexical-only mode, hybrid RRF merge with stubbed `embed_text`,
  graceful fallback when `embed_text` raises, and direct cosine
  ranking on the SQLite override.

**Backfill:** features written before T1.2 have NULL embeddings. The
existing `featcat embeddings backfill` CLI (`featcat/cli.py:3397`) is
the way to populate them — search degrades cleanly until then.

**Files:** `featcat/catalog/local.py`, `featcat/ai/tools.py`,
`featcat/ai/agent.py`, `tests/test_search_hybrid.py`.

---

## Issue 4 — `instructor`/`zod-stream`/`openai` peer-dep conflict

**No code change.** The premise didn't reproduce:

- `web/package.json` lists none of `openai`, `instructor`,
  `instructor-js`, or `zod-stream`.
- `bun install` in `web/` runs clean — no peer warnings.
- A grep across `web/src/` finds no imports of those packages.
- The frontend talks to llama.cpp via the `ai` package (v6.0.176); it
  never depended on the OpenAI SDK.

If a conflict was seen elsewhere (a sibling package directory, an older
checkout, a different branch), point me at the exact `bun install`
output and I'll re-investigate.

---

## Verification

```text
$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
214 files already formatted

$ uv run mypy featcat/
featcat/catalog/exporter.py:177: error: Item "Series" of "DataFrame | Series" has no attribute "join"  [union-attr]
featcat/catalog/exporter.py:177: error: Argument 1 to "join" of "DataFrame" has incompatible type "DataFrame | Series"; expected "DataFrame"  [arg-type]
Found 2 errors in 1 file (checked 124 source files)
```

The two mypy errors above are **pre-existing on `origin/staging`** —
`featcat/catalog/exporter.py` was last touched in commit `79828df`
(unchanged on this branch). The file isn't part of this fix.

```text
$ uv run pytest -x --no-cov -q
982 passed, 1 skipped, 4 deselected, 4 warnings in 216.62s (0:03:36)

$ uv run pytest tests/test_search_hybrid.py -v --no-cov
8 passed in 3.82s

$ uv run pytest tests/test_sources_routes.py -v --no-cov
18 passed in 5.65s
```

Frontend (`web/package.json` has only `build`, `test`, `test:run`,
`test:e2e` scripts — no `lint` / `typecheck`; the build script runs
`tsc && vite build`, which is the typecheck):

```text
$ cd web && bun install
601 packages installed [...] no peer warnings

$ bun run build
✓ built in 27.85s  (tsc passes, vite emits to featcat/server/static)

$ bun run test:run
Test Files  20 passed (20)
     Tests  119 passed (119)
```

The plan's "manual checks" against the live server are not run in this
report because the dev catalog has no billing/tiền features (the
data-driven aspect of Issue 3 — see the premise correction above);
hybrid behaviour is exercised end-to-end by the new pytest cases
instead.

---

## Deferred follow-ups

- Mid-batch failure handling for `POST /api/sources/bulk/delete`: today
  the loop accumulates `features_removed` but if a later delete throws
  the response surfaces a 500 and leaves earlier deletes committed. A
  single SA transaction across the loop would fix that — deferred
  because `LocalBackend.delete_source` opens its own session and
  unifying them is more than this fix's scope.
- Pre-existing mypy errors in `featcat/catalog/exporter.py:177` —
  unrelated to this work; whoever owns `exporter.py` should pick them
  up in a follow-up.
- Embedding-backfill UX in the web UI: today operators must run
  `featcat embeddings backfill` from the CLI. A button on the admin
  page would close the loop but is out of scope here.
