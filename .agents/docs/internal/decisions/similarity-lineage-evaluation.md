# Similarity & Lineage graph features — keep / simplify / kill evaluation

**Status:** Draft for operator review · **Author:** decision-doc audit · **Date:** 2026-05-18

## Context

featcat ships two relationship-graph features:

- **Similarity** (`/similarity` page, 5 backend endpoints). TF-IDF + optional embedding-backed scoring that surfaces similar / duplicate features. Three views: a force-directed graph, a heatmap matrix, and a per-pair reason-code panel.
- **Lineage** (`/lineage` page, 2 backend endpoints). A directed graph of feature derivations, populated by `featcat lineage detect` parsing `features.definition` SQL with `sqlglot`, by manual edits, or by the demo fixture.

`.agents/docs/internal/operations/BACKLOG.md:132` carries the open item this document closes: *"Similarity / lineage graph: decide kill vs ship with use case."* Both features are feature-complete, lightly maintained, and **not instrumented in `usage_log`** — there is no view-count signal. Recommendations therefore lean on code volume, dependency surface, git velocity, and structural data-availability constraints, with the open questions at the end explicitly calling out where operator judgement is still required before any code is removed.

## Method

For each feature: LoC (per file), dependency surface (which deps would die with the feature), git velocity (last meaningful change, bug-fix count over six months), test coverage, and a hard look at data-availability preconditions (does the page do anything useful on a fresh catalog without operator setup?). Recommendation rests on: value to a DS workflow, cost to maintain, and whether a simpler version delivers ~80 % of the value.

Numbers in this doc were re-verified against the working tree on `staging` at `3c60eba` immediately before writing.

---

## Similarity

### Audit

| Layer | Path | LoC | Notes |
|---|---|---:|---|
| Route | `featcat/server/routes/features.py:560` `/similarity-graph` | 83 | All-vs-all graph data, TF-IDF, drift enrichment, module-level cache, edge cap 5/node |
| Route | `featcat/server/routes/features.py:751` `/similarity-matrix` | 37 | Caller-specified subset ≤100, upper-triangle |
| Route | `featcat/server/routes/features.py:790` `/similarity-pair` | 23 | Per-pair reason-code breakdown |
| Route | `featcat/server/routes/features.py:426` `/by-name/similar` | 16 | Top-K, pgvector or TF-IDF fallback |
| Route | `featcat/server/routes/features.py:931` `/recommend` | 52 | LLM-or-TF-IDF discovery, 8 s timeout |
| Service | `featcat/catalog/local.py find_duplicate_pairs` | 113 | Silent 2000-feature cap |
| Service | `featcat/catalog/local.py compute_similarity_matrix` | 79 | |
| Service | `featcat/catalog/local.py compute_pair_reasons` | ~90 | Splits score into name / schema / distribution / semantic |
| Embeddings | `featcat/ai/embeddings.py` | 201 | Lazy-loads `all-MiniLM-L6-v2` |
| Frontend | `web/src/pages/Similarity.tsx` | 75 | Tab shell |
| Frontend | `web/src/pages/similarity/SimilarityGraph.tsx` | 524 | D3 force layout, zoom, drag, selection |
| Frontend | `web/src/pages/similarity/SimilarityMatrix.tsx` | 265 | Feature picker, threshold slider, grid filter |
| Frontend | `web/src/pages/similarity/MatrixGrid.tsx` | 212 | Heatmap render |
| Frontend | `web/src/pages/similarity/PairPanel.tsx` | 156 | Right-side reason-code detail |
| | **Frontend total** | **1 232** | |

**Tests:** 25+ backend tests across `tests/test_similarity_*`. **Zero** frontend component tests for any of the four similarity components.

**Dependencies:**

| Dep | Where | Shared with | Removable if Similarity dies? |
|---|---|---|---|
| `sklearn` | core, similarity service | distribution stats | No |
| `numpy` | core, similarity service | stats, charts | No |
| `pgvector` | optional extra | lineage | No |
| `sentence-transformers>=2.2` | `[embeddings]` extra, `pyproject.toml:54` | none | **Yes** — pulls torch (~1 GB transitively). Recent Docker rebuild churn (PRs #81, #84, #101) is partly because of this extra. |
| `d3@^7.9.0` | `web/package.json:34` | Lineage.tsx | Only if Lineage is also killed |

**Git velocity (6 months):** 15 commits. Last substantive feature work in February 2026 (`daec638` matrix + pair endpoints, `f8db21d` tab split). Since then: polish only. **Zero bug-fix PRs.** No open issues tagged similarity.

**Pain signals:** full D3 bundle shipped for one page (~175 KB gz); silent 2000-feature cap on `find_duplicate_pairs` with no UI surfacing; `[embeddings]` extra has bitten Docker deployment twice in the last quarter.

**Usage tracking:** none of the five endpoints write to `usage_log`.

### Value evaluation

DS-workflow questions the feature could answer:

- **"Is someone already building this feature, or is there a near-duplicate I should reuse?"** — this is the strongest argument for keeping anything in the similarity stack. The duplicate-finder is the headline use case in `README.md` and `docs/architecture/data.md`. For a telecom catalog growing past a few hundred features, this is genuine.
- **"Why are these two features similar?"** — the per-pair reason-code panel (name / schema / distribution / semantic) explains the score concretely. Useful for trust calibration.

Questions the feature *looks* like it answers but doesn't, well:

- **"Show me how the whole catalog connects"** — the force-directed graph view is the most visible component (524 LoC, the heaviest single similarity file) and the least defensible. At telecom-catalog scale (>1 000 features) it collapses into a hairball. The existing silent 2000-feature cap on the underlying duplicate scan is an admission that the all-vs-all visualisation does not scale to real catalogs. The matrix view exposes the same information more legibly at the same scale.

### Recommendation: **KEEP_SIMPLIFIED**

Concrete, file-level next steps. Effort estimates assume a single engineer familiar with the codebase.

1. **Delete `web/src/pages/similarity/SimilarityGraph.tsx` (524 LoC) and remove the Graph tab from `web/src/pages/Similarity.tsx`.** Keep `SimilarityMatrix.tsx`, `MatrixGrid.tsx`, `PairPanel.tsx`. The matrix view subsumes the graph view's information without the hairball problem.
   - Effort: **0.5 day** (delete files, drop tab routing, refresh any screenshots / demo captures in `web/scripts/capture_demo_screenshots.ts`).
2. **Decommission `GET /api/features/similarity-graph` (handler at `featcat/server/routes/features.py:560`).** Drop the route, its `MatrixResponse` sibling that's only used by graph, and the corresponding backend test file `tests/test_similarity_endpoint.py` block for that endpoint (the matrix + pair tests stay).
   - Effort: **1 hour.**
3. **Instrument `usage_log` writes on the surviving `/similarity-matrix` and `/similarity-pair` endpoints.** Use the same pattern that the explore audit found in `featcat/server/routes/features.py:50-71` for the existing `view` / `search` / `query` actions. A future re-evaluation will then have real data.
   - Effort: **1 hour.**
4. **Keep `[embeddings]` optional extra** unchanged. The duplicate-finder is the strongest argument for the whole feature, and `sentence-transformers` is already optional; the recent Docker churn is a separate operational fix, not a reason to drop the capability.

**Estimated total:** ~1 working day. **Net delta:** −607 LoC frontend, −83 LoC backend, +~20 LoC instrumentation.

---

## Lineage

### Audit

| Layer | Path | LoC | Notes |
|---|---|---:|---|
| Route | `featcat/server/routes/lineage.py /api/lineage/full` | ~80 | Whole-catalog feature→feature graph (excludes source-column edges) |
| Route | `featcat/server/routes/lineage.py /api/lineage/impact` | ~36 | "If I change X, what depends on it?" — transitive downstream |
| SQL parser | `featcat/lineage/sql_detect.py` | 307 | sqlglot-based AST walk; depends on optional `[lineage-sql]` extra |
| Package init | `featcat/lineage/__init__.py` | 17 | |
| Catalog methods | `featcat/catalog/local.py` (add_lineage, remove_lineage, get_impact, get_lineage_graph, get_feature_lineage) | ~300 | |
| Schema | `featcat/db/models.py:297-335` `FeatureLineage` | — | `detected_method ∈ {manual, sql_parse, imported, demo}` |
| Frontend | `web/src/pages/Lineage.tsx` | **1 090** | Single-file D3 force sim with SVG↔Canvas auto-fallback, drag/zoom/search/source-filter |

**Tests:** ~730 LoC unit tests (`tests/test_lineage_sql_detect.py`, `tests/test_lineage_seed.py`, `tests/test_lineage_impact.py`). **Zero** frontend component tests.

**Dependencies:**

| Dep | Where | Shared with | Removable if Lineage dies? |
|---|---|---|---|
| `sqlglot>=20.0` | `[lineage-sql]` extra, `pyproject.toml:70` | none | **Yes** |
| `d3@^7.9.0` | `web/package.json:34` | SimilarityGraph.tsx (only) | **Yes**, *if* SimilarityGraph has also been removed (see Similarity step 1) |
| `pgvector` | optional | similarity | No |

**Git velocity (6 months):** ~6 substantive commits, last meaningful work `c9f9f1b` (canvas fallback) six months ago. **Zero** bug fixes since.

**Usage tracking:** neither endpoint writes to `usage_log`.

**Structural data-availability constraint (this is the killer fact):** the graph is empty unless users have populated `features.definition` with SQL **and** run `featcat lineage detect --apply`. The audit found no metric in the codebase that measures real-catalog coverage of `features.definition`. The only realistic dataset that exercises the page is `tests/fixtures/lineage-demo.json` (13 edges across 3 sources). On a freshly bootstrapped real catalog, `/lineage` shows an empty state with a CLI hint and nothing else.

### Value evaluation

Real DS-workflow questions:

- **"If I change feature X, what breaks?"** — `/api/lineage/impact` is the high-value endpoint for refactor planning and incident response. It does not need a graph UI; a feature-detail page section ("downstream consumers: A, B, C") delivers 90 % of the value.
- **"Where does feature X come from?"** — useful for documentation. Again, a feature-detail page section reading `transform` + parents from `feature_lineage` covers this.

Use cases that fall apart:

- **"Visualise the whole catalog as a graph"** — only meaningful with broad SQL-definition coverage that the codebase does not currently measure or enforce. The page exists; the data it needs does not exist by default.

### Recommendation: **KEEP_SIMPLIFIED**, with an explicit data-tripwire

The recommendation deliberately does not jump to KILL despite the data-availability concern, because removing the routes before instrumenting them removes the ability to ever measure usage. The plan instruments first, then decides.

1. **Instrument `usage_log` on `/api/lineage/full` and `/api/lineage/impact`.** Same pattern as the similarity recommendation step 3. This is the precondition for any further deletion.
   - Effort: **30 minutes.**
2. **Add a SQL-definition-coverage stat to `featcat doctor` and to `/api/stats`.** Compute the percentage of features with a non-null `features.definition`. This is the single number that tells the operator whether the graph page can ever do useful work.
   - Effort: **2 hours.**
3. **Decision branch — re-evaluate after 30 days of step 1 data:**
   - **If `/api/lineage/full` sees ≥10 views/week on a real catalog AND the definition-coverage stat is ≥30 %** → simplify, don't kill. Concrete simplifications to `web/src/pages/Lineage.tsx`:
     - Drop the SVG ↔ Canvas auto-fallback. Pick canvas above 500 nodes, SVG below, inline. (~200 LoC).
     - Replace the render-mode and source-visibility toggles with search + "highlight ancestry on hover" (~100 LoC).
     - Net target: ~700-800 LoC, down from 1 090.
     - Effort: **1.5 days.**
   - **If usage is 0 or coverage is <10 %** → kill the graph page. Delete `web/src/pages/Lineage.tsx` (1 090 LoC) and `GET /api/lineage/full` (~80 LoC). Keep `/api/lineage/impact`, keep the `feature_lineage` table, keep `featcat/lineage/sql_detect.py` and the CLI subcommands — they remain useful for feature-detail rendering and for operators who do populate SQL. Drop `d3@^7.9.0` from `web/package.json` **only after** Similarity step 1 has shipped (so D3 has no other consumer). Drop `sqlglot` only if the CLI auto-detect path is also removed.
     - Effort: **1 day.**

**Estimated total upfront:** 2.5 hours (instrumentation + coverage stat). The kill-or-keep follow-up is 1-1.5 days and is **explicitly gated on the data** the instrumentation produces.

---

## Summary

| Feature   | Recommendation                | Effort to act now | Net code delta (immediate) |
|-----------|-------------------------------|-------------------|----------------------------|
| Similarity | **KEEP_SIMPLIFIED**           | ~1 working day    | −607 LoC frontend, −83 LoC backend, +~20 LoC instrumentation |
| Lineage    | **KEEP_SIMPLIFIED w/ tripwire** | 2.5 hours now, then 1-1.5 days gated on usage + coverage data | +~30 LoC instrumentation now |

Combined immediate delta if both recommendations land: **−607 frontend, −83 backend, +~50 LoC instrumentation**, plus an unblocked path to dropping `d3` from `web/package.json` once Similarity ships its step 1.

## Open questions for the operator

1. **Has anyone on the DS team walked `/similarity` or `/lineage` on a real (non-demo) catalog in the last 90 days?** A confirmed "yes, regularly" steers harder toward KEEP_AS_IS; a confirmed "no" steers Similarity toward a deeper cut and accelerates Lineage's tripwire to "kill now."
2. **What fraction of features in production catalogs have a populated `features.definition`?** This is the single fact that decides whether the lineage graph is structurally usable. The "coverage stat" follow-up exists to surface this number; if you already know it informally, share it now to short-circuit the wait.
3. **Is "find duplicate features before I build a new one" actually requested by the DS team, or is it speculative?** If the duplicate-finder use case is not real customer demand, the Similarity recommendation drops to KILL and everything in `featcat/ai/embeddings.py` plus the `[embeddings]` extra can go too.
4. **Are there third-party consumers (other apps, scripts) of `GET /api/features/similarity-graph` or `GET /api/lineage/full`?** `usage_log` will only see frontend traffic; an API client that hits these directly would break silently on a route removal. This needs a manual check (Slack the team, grep internal repos).
5. **Is the team willing to maintain the `[embeddings]` optional extra long-term?** Recent Docker rebuild churn (PRs #81, #84, #101) suggests friction. If the answer is "no, this keeps biting us," that's another argument for the lighter Similarity scope (matrix-only, no embeddings).

The operator should answer 1-5 and then open follow-up code PRs implementing the chosen path per feature. This document records the recommendation and the evidence behind it; the merge of this PR is **not** authorisation to delete code.
