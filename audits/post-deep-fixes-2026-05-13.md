# Post-Deep-Fixes Audit — Gap 3, P1.1, P2.1

**Date:** 2026-05-13
**Branch:** `feat/intent-classifier`
**Tip commits:** `aa35ab6` (timeout) → `e79503d` (context summary) → `ebcb375` (FTS5)
**Builds on:** `audits/p0-3-verification-2026-05-13.md` (85.7% pass-only baseline)

This document records the three deep fixes shipped after P0.3 verification.
Each one targets a specific failure mode identified during P0 MVP
testing. Re-running the 35-prompt
MVP suite and updating the headline numbers is **deferred to the user** because
the suite requires the live LLM stack (~30 min wall-clock) — placeholders
below mark where numbers should land.

---

## Fix 1 — Server-side timeout on `/api/ai/chat` (audit Gap 3)

**Commit:** `aa35ab6` — `feat(server): deadline-aware timeout on /api/ai/chat SSE stream`

**Problem.** B2 ran 235s on the P0.3 baseline run; no `asyncio.wait_for`
wrapping the SSE generator. One bad prompt blocked the uvicorn worker for
minutes. `/discover` and `/ask` already use `LLM_TIMEOUT = 180` — `/chat` was
the only LLM-calling route without a timeout.

**Change.** Per-iteration `asyncio.wait_for(iterator.__anext__(), …)` with a
shrinking deadline computed once at stream start. Default 90s, override via
`FEATCAT_CHAT_TIMEOUT_SECONDS`. On timeout: emit the existing
`{"type": "error", "content": "Phản hồi quá lâu …"}` SSE event (already
handled at `web/src/pages/Chat.tsx:268-275`), close the generator cleanly,
skip the assistant-side `session.add_message` so a half-streamed answer
cannot poison future turns.

Why per-iteration instead of a single wrap: Python 3.10 (the project's
minimum) lacks `asyncio.timeout()`. Wrapping `async for` is awkward; bounding
each `anext()` with the remaining budget is portable.

**Files:** `featcat/server/routes/ai.py`, `tests/test_chat_timeout.py`.

**Local verification.** Patched stub generator + 1s deadline → error event in
<1.5s, session.messages contains only the user turn (no assistant).

**Expected MVP delta.**

| Prompt | P0.3 | Post-fix prediction | Why |
|---|---|---|---|
| B2 (network anomaly) | ⚠ Partial (235s runaway) | ☒ Fail (timeout error event) → opportunity to re-prompt | timeout fires; user sees the message and can shorten the query |
| Worker block-time on runaway | ~235s | ≤90s | hard cap |

The fix does not improve B2's *answer quality* — it only stops the runaway
from blocking the worker. B2 may stay at Partial unless the underlying
`suggest_features` model behaviour also improves.

---

## Fix 2 — Conversation context extraction (P1.1, C5 memory failure)

**Commit:** `e79503d` — `feat(ai): extract feature-name context from dropped session turns`

**Problem.** `ChatSession.get_history()` returns only the last 6
user/assistant messages. In long sessions, feature names mentioned in earlier
turns drop off the prompt window. C5 in the audit corpus is a multi-turn
test where the model loses track of which feature was being investigated.

**Change.** New `ChatSession.get_context_summary()` that extracts
feature-name entities (regex `\w+\.\w+`) from messages older than the live
6-turn window, dedups, caps at 8. Threaded through `CatalogAgent.chat()` as
an optional `context_summary` kwarg and rendered as a second system message
with a language-aware label (`"Bối cảnh trước đó (các feature đã đề cập)"`
for VI, `"Earlier context (features mentioned)"` for EN, picked via
`detect_language(user_message)`).

Rule-based, not LLM-based: zero extra LLM calls (latency-conscious), perfect
for featcat queries which are entity-centric. Group/source name extraction
is intentionally deferred — disambiguating bare identifiers needs a catalog
lookup; feature names carry the most signal anyway.

**Files:** `featcat/ai/session.py`, `featcat/ai/agent.py`,
`featcat/server/routes/ai.py`, `tests/test_agent.py`,
`tests/test_chat_timeout.py` (stub kwargs).

**Local verification.** 5 unit tests on extraction (dedup, cap, language
label, no-features → None, non-string content → no crash). 3 unit tests on
agent wiring (VI label, EN label, no-summary keeps single system message).

**Expected MVP delta.**

| Prompt | P0.3 | Post-fix prediction | Why |
|---|---|---|---|
| C5 (6-turn memory) | ☒ Fail (per audit pre-baseline) | ☑ Pass | turn-1 feature names survive in the system context message at turn 7+ |

Other C-section prompts (C1–C4, all ≤4 turns) stay within the 6-message
window, so the context summary is `None` and the agent path is unchanged.

---

## Fix 3 — FTS5 search (P2.1, A3/E2/D6 search rigidity)

**Commit:** `ebcb375` — `feat(catalog): FTS5-backed search with BM25 ranking and diacritic folding`

**Problem.** `search_features` used `LIKE %q%` over name/description/tags/
column_name, sorted alphabetically. A3 ("find feature with cpu in the name")
missed `cpu_load` when searching for `cpu_usage`; Vietnamese queries with
diacritics didn't match assets written without them; result order had no
relevance signal.

**Change.** Contentful FTS5 virtual table `features_fts` with
`unicode61 remove_diacritics=2` tokenizer, populated and synced via
AFTER INSERT/UPDATE/DELETE triggers added to `init_db`'s `legacy_alters`
tuple (idempotent — re-runs are no-ops via `OperationalError` suppression
and a `WHERE NOT EXISTS` guard on the backfill). `_fts_sqlite` now uses
FTS5 + BM25; structured filters (source/tag/dtype/has_doc) are intersected
in Python with the FTS5 hits. `_fts_sqlite_legacy` keeps the pre-FTS5
keyword scorer as a fallback when FTS5 errors out (malformed input, stale
DB without the virtual table). `search_features` delegates to
`full_text_search` and re-hydrates Feature objects via a single
`SELECT * FROM features WHERE id IN (:ids)` preserving rank order.

Why contentful instead of external content with `content_rowid='id'`:
`features.id` is TEXT, not an INTEGER rowid alias, so the external-content
pattern won't compile. Contentful doubles index storage for the indexed
columns — at featcat catalog scale (≤10k features), the storage hit is
trivial and the simpler join wins.

`_build_fts5_query` splits user input on whitespace/underscore/punct, quotes
each token, and joins with OR plus a phrase boost (`"cpu_usage" → "cpu usage"
OR "cpu" OR "usage"`). The phrase boost makes verbatim hits rank highest via
BM25 while OR preserves recall.

**Files:** `featcat/catalog/local.py`, `tests/test_full_text_search.py`.

**Local verification.** Full suite green (733 passed, 1 skipped). New tests:
underscore tokenization, diacritic folding (`luot truy cap` matches
`lượt truy cập`), malformed query fallback, INSERT/DELETE trigger sync,
`search_features` hydration + tag search.

**Expected MVP delta.**

| Prompt | P0.3 | Post-fix prediction | Why |
|---|---|---|---|
| A3 (find specific) | ⚠ Partial (substring miss) | ☑ Pass | FTS5 OR + token match picks up related names |
| E2 (multi-tool, search step) | ☑ Pass | ☑ Pass | likely faster + better-ranked search hits |
| D6 (conflicting / "top 3") | ⚠ Partial (returns 10) | ⚠ Partial (no change) | this is a list-features limit problem, not search; FTS5 doesn't fix it |
| Vietnamese diacritic queries | unmeasured | now case- and accent-insensitive | new capability |

---

## Aggregate prediction

| Metric | P0.3 baseline | Post-deep-fixes prediction |
|---|---:|---:|
| Pass-only score | 24 / 28 = 85.7% | **25 / 28 = 89.3%** (A3 flips) |
| Pass + Partial | 28 / 28 = 100% | 28 / 28 = 100% (unchanged) |
| Worst-case latency (B2) | 235s | ≤90s (timed out cleanly) |
| Multi-turn coverage (C5) | not in 28-prompt single-shot | now testable; expected pass |

The "~95%" goal from the original deep-fixes brief assumed B2 would flip to
Pass; honest read is B2 stays Partial-or-Fail (the timeout *contains* the
problem rather than *fixing* the underlying suggest_features runaway). A3
flipping is the most likely test-suite win.

---

## What's still owed (for the user to run)

1. **MVP rerun.** Start the LLM stack (`docker compose -f deploy/docker-compose.yml up`),
   restart featcat server (it pre-loads the route code at import time, so the
   running instance still has pre-fix code), then:
   ```bash
   python scripts/run_mvp_tests.py --runs 1 --mode on
   ```
   Compare `artifacts/p0-3-mvp-fullsuite.csv` to the new run. Append a §5b
   "Post-deep-fixes 35-prompt rerun" section to this doc with the per-prompt
   pass/fail diff.

2. **Demo screenshots.** Run `scripts/capture_demo_screenshots.ts` and
   `scripts/capture_lineage_screenshot.ts` against a fresh dev server with
   the new code, save outputs to `slides/`.

3. **README/CHANGELOG note.** v0.2.0 line item: "Chat hardening: 90s server
   timeout, multi-turn memory via entity extraction, FTS5 search with BM25
   ranking and Vietnamese diacritic folding."

---

## Risks and known caveats

- **Backfill assumes empty fts table.** The `WHERE NOT EXISTS` guard means a
  populated catalog with a *partially* synced fts table will not auto-repair.
  In practice the triggers keep it in sync on every mutation, and re-running
  `init_db` on a fresh state populates from scratch. If catalogs drift, a
  manual `DELETE FROM features_fts; INSERT … SELECT … FROM features;` is the
  recovery path.

- **Timeout default of 90s** may need bumping for `suggest_features` and
  `compare_features` on slow hardware (those legitimately run 60-90s in the
  P0.3 measurements). Override via `FEATCAT_CHAT_TIMEOUT_SECONDS=120` if
  staging soak shows false-positive timeouts.

- **Context summary is feature-names only.** A user who refers to a group or
  source by bare name across the 6-turn boundary will still see that
  reference dropped. Follow-up work: pass the catalog backend into the
  extractor and resolve bare identifiers against `list_sources`/
  `list_groups`.

- **Postgres backend unaffected by Fix 3.** All FTS5 changes are gated on
  `self.backend == "sqlite"`. The existing postgres tsvector path
  (`_fts_postgres`) is unchanged.
