# Featcat technical backlog

Captured 2026-05-15 from sandbox UAT sessions and operator review. New
sprint-queue items are filed at the top; the categorised backlog below is the
source of truth for "what exists" and is grouped by P0 / P1 / P2.

---

## Sprint queue — next up (2026-05-15)

Pick top-down; estimates are operator-supplied and subject to refinement once
investigation starts. Every row links back to the categorised entry below so
nothing slips out of the backlog when this section is rewritten.

_All sprint-queue items below are shipped (PRs #81–#97). New items will be filed
here as they enter the queue; ticked entries are preserved in the categorised
backlog for the audit trail._

| # | Estimate | Item | Backlog ref | Shipped |
|---|----------|------|-------------|---------|
| 1 | ~30 min | Ship `[embeddings]` extra in the default image build + rebuild + push → unblocks the similarity feature (Finding 5 from `run-2026-05-15-024551.md`) | Bugs P0 — *Default Docker image missing [embeddings] extra* + Infrastructure P2 — *Rebuild + push image with current main* | #81, #84 |
| 2 | 3 h | Bug: auto-generate progress lost on F5/reload mid-batch | Bugs P0 — *Auto-generate progress lost on F5* | #82, #86 |
| 3 | 1 – 2 h | Bug: `feature diff` returns `(no differences)` between consecutive versions after a definition edit — investigate comparator | Bugs P0 — *feature diff returns "(no differences)"* | #83 |
| 4 | 1 h | Bug: `feature_versions.changed_by` shows `unknown` for LLM-generated docs; set to `autodoc` or `llm:<model_name>` | Bugs P0 — *changed_by is "unknown" for LLM-generated docs* | #85 |
| 5 | 2 h | Bug: drift severity classifier inconsistent — numeric score present but label says `unknown`; health score 55 (grade C) but page labels feature `healthy` | Bugs P0 — *Drift severity classifier inconsistent* | #87 |
| 6 | 3 – 4 h | Feature: add KL Divergence + Wasserstein columns alongside PSI; surface in Distribution Shift chart (only if time after #1–#5) | Features — backend P1 — *Add KL Divergence + Wasserstein* | #92 |

---

## Bugs (P0)

- [x] Auto-generate progress lost on F5/reload mid-batch; UI reverts to
      pre-run button state instead of resuming progress display
      (PR #82, #86)
- [x] Drift severity classifier inconsistent: numeric score present but
      label shows "unknown"; health score 55 (grade C) but monitoring page
      labels feature "healthy" (PR #87)
- [x] feature_versions.changed_by is "unknown" for LLM-generated docs;
      should be "autodoc" or "llm:<model_name>" (PR #85)
- [x] Monitoring rows missing PSI in some entries (data gap vs compute
      error to be determined) — fixed together with severity classifier
      in PR #87 (root cause shared)
- [x] feature diff returns "(no differences)" between consecutive versions
      after definition edit (UAT e-i finding) (PR #83)
- [x] action_items module + monitoring module lack pytest coverage
      (PR #90)
- [x] Default Docker image missing [embeddings] extra: similarity matrix
      uniform, graph has 0 edges (PR #81, #84)

## Features — frontend (P1)

- [x] Shared component for cards (sources/groups/jobs use divergent UIs)
      (PR #95)
- [x] Shared component for tables (features/monitoring/audit/jobs)
      (PR #95 — Audit migrated; Jobs migrated in PR #96)
- [x] Shared FloatingPanel for detail views; replace job bottom panel.
      Convention: all detail views use FloatingPanel (PR #96 — Features,
      Jobs, SchedulerOverview migrated; convention noted in PR body
      pending CLAUDE.md edit by operator)
- [x] Replace HTML-native checkbox/dropdown with themed components
      (PR #97 — Checkbox + Select shipped; 5 widgets migrated; row-level
      tri-state callers deferred to follow-up)
- [ ] Search moves from tab to sticky top-bar element
- [ ] Improve search ranking + faceted results
- [x] Add /groups/<name> route + group detail page (PR #93)
- [x] Rename Definition→Specification, Documentation→Data Profile;
      reorder; add AI-generated badge + timestamp; add empty state
      (PR #91)
- [x] Feature status transitions UI (draft/reviewed/certified/deprecated;
      backend endpoint already exists at POST /api/features/by-name/status)
      (PR #94)
- [x] Delete button for data sources (backend DELETE /api/sources/{name}
      exists) (PR #91 — verified already shipped)
- [x] Job card: collapse edit + details into 3-dot menu top-right
      (PR #96)
- [ ] Dashboard export/copy report (time range filter, recommend export
      when payload large) — needs spec before implementing

## Features — backend (P1)

- [x] Add KL Divergence + Wasserstein columns to monitoring_checks;
      compute alongside PSI; surface in Distribution Shift chart
      (PR #92)
- [x] Search fallback to features.name + features.tags when
      feature_docs.short_description empty (PR #91 — regression test
      added; the existing TF-IDF corpus already covers this contract,
      no code change needed)
- [x] Doc generate per-source / per-limit filter
      (current CLI only has --all) (PR #91)

## Documentation drift sync (P1)

Sync README and CLI --help text to match shipped flags:

- [x] doc generate X (positional, not --feature X) (PR #88)
- [x] group add G a b c (positional varargs, not --features a,b,c)
      (PR #88 — verified docs already correct)
- [x] group remove G a (positional) (PR #88 — verified docs already correct)
- [x] group delete N --yes (not --confirm) (PR #88 — verified docs already
      correct)
- [x] feature set-definition N --sql "..." (not --type sql --definition)
      (PR #88 — verified docs already correct)
- [x] feature diff N --v1 1 --v2 2 (not --from --to) (PR #88 — verified
      docs already correct)
- [x] feature rollback N --version 1 (not --to 1) (PR #88 — verified
      docs already correct)
- [x] /api/ai/chat body schema is `{"query":"..."}` not `{"messages":[...]}`
      (PR #88 — added as 8th item during reconciliation)

## Infrastructure (P2)

- [ ] CI auto-rebuild nxank4/featcat:latest on tag/main push
- [ ] Walk sandbox scenarios j-o (PSI timeline, distribution shift chart,
      doc debt heatmap, health score, export to DataFrame, versioning
      rollback E2E, teardown reproduce)
- [ ] Rebuild + push image with current main (fixes doctor sub-app gap
      from prior UAT)

## Deferred — needs spec/discussion before scoping (P2)

- [ ] Path picker for input fields (Windows/Linux/Mac compat)
- [ ] Chat: copy conversation + edit prior prompts with stream-abort logic
- [ ] Doc Help UI redesign (need specific pain points from users first)
- [ ] CLI + TUI gap audit (vague — need bug list before scoping)
- [ ] Similarity / lineage graph: decide kill vs ship with use case
- [ ] Feast-like online/offline store + registry (scope expansion beyond
      catalog — design doc first, defer to next quarter)
- [ ] Featcat logo + favicon (needs design)

## Coverage baseline 2026-05-15

After P0 bug fixes (PRs #82-#88 merged), `uv run pytest --cov=featcat` reports:
- Total: 69% (10887 stmts, 3427 miss)
- Critical-path modules below 50%:
  - featcat/server/routes/ai.py: 39%
  - featcat/server/routes/docs.py: 42%
  - featcat/server/routes/scan.py: 42%
  - featcat/catalog/context_builder.py: 46%
  - featcat/cli.py: 48%
- TUI modules excluded from coverage focus (0% by design, not exercised in pytest)
- featcat/catalog/remote.py at 27% acceptable (covered via integration in deployed setup)

Baseline informs P1 coverage work selection.
