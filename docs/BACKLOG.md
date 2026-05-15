# Featcat technical backlog

Captured 2026-05-15 from sandbox UAT sessions and operator review. New
sprint-queue items are filed at the top; the categorised backlog below is the
source of truth for "what exists" and is grouped by P0 / P1 / P2.

---

## Sprint queue — next up (2026-05-15)

Pick top-down; estimates are operator-supplied and subject to refinement once
investigation starts. Every row links back to the categorised entry below so
nothing slips out of the backlog when this section is rewritten.

| # | Estimate | Item | Backlog ref |
|---|----------|------|-------------|
| 1 | ~30 min | Ship `[embeddings]` extra in the default image build + rebuild + push → unblocks the similarity feature (Finding 5 from `run-2026-05-15-024551.md`) | Bugs P0 — *Default Docker image missing [embeddings] extra* + Infrastructure P2 — *Rebuild + push image with current main* |
| 2 | 3 h | Bug: auto-generate progress lost on F5/reload mid-batch | Bugs P0 — *Auto-generate progress lost on F5* |
| 3 | 1 – 2 h | Bug: `feature diff` returns `(no differences)` between consecutive versions after a definition edit — investigate comparator | Bugs P0 — *feature diff returns "(no differences)"* |
| 4 | 1 h | Bug: `feature_versions.changed_by` shows `unknown` for LLM-generated docs; set to `autodoc` or `llm:<model_name>` | Bugs P0 — *changed_by is "unknown" for LLM-generated docs* |
| 5 | 2 h | Bug: drift severity classifier inconsistent — numeric score present but label says `unknown`; health score 55 (grade C) but page labels feature `healthy` | Bugs P0 — *Drift severity classifier inconsistent* |
| 6 | 3 – 4 h | Feature: add KL Divergence + Wasserstein columns alongside PSI; surface in Distribution Shift chart (only if time after #1–#5) | Features — backend P1 — *Add KL Divergence + Wasserstein* |

---

## Bugs (P0)

- [ ] Auto-generate progress lost on F5/reload mid-batch; UI reverts to
      pre-run button state instead of resuming progress display
- [ ] Drift severity classifier inconsistent: numeric score present but
      label shows "unknown"; health score 55 (grade C) but monitoring page
      labels feature "healthy"
- [ ] feature_versions.changed_by is "unknown" for LLM-generated docs;
      should be "autodoc" or "llm:<model_name>"
- [ ] Monitoring rows missing PSI in some entries (data gap vs compute
      error to be determined)
- [ ] feature diff returns "(no differences)" between consecutive versions
      after definition edit (UAT e-i finding)
- [ ] action_items module + monitoring module lack pytest coverage
- [ ] Default Docker image missing [embeddings] extra: similarity matrix
      uniform, graph has 0 edges

## Features — frontend (P1)

- [ ] Shared component for cards (sources/groups/jobs use divergent UIs)
- [ ] Shared component for tables (features/monitoring/audit/jobs)
- [ ] Shared FloatingPanel for detail views; replace job bottom panel.
      Convention: all detail views use FloatingPanel
- [ ] Replace HTML-native checkbox/dropdown with themed components
- [ ] Search moves from tab to sticky top-bar element
- [ ] Improve search ranking + faceted results
- [ ] Add /groups/<name> route + group detail page
- [ ] Rename Definition→Specification, Documentation→Data Profile;
      reorder; add AI-generated badge + timestamp; add empty state
- [ ] Feature status transitions UI (draft/reviewed/certified/deprecated;
      backend endpoint already exists at POST /api/features/by-name/status)
- [ ] Delete button for data sources (backend DELETE /api/sources/{name}
      exists)
- [ ] Job card: collapse edit + details into 3-dot menu top-right
- [ ] Dashboard export/copy report (time range filter, recommend export
      when payload large) — needs spec before implementing

## Features — backend (P1)

- [ ] Add KL Divergence + Wasserstein columns to monitoring_checks;
      compute alongside PSI; surface in Distribution Shift chart
- [ ] Search fallback to features.name + features.tags when
      feature_docs.short_description empty
- [ ] Doc generate per-source / per-limit filter
      (current CLI only has --all)

## Documentation drift sync (P1)

Sync README and CLI --help text to match shipped flags:

- [ ] doc generate X (positional, not --feature X)
- [ ] group add G a b c (positional varargs, not --features a,b,c)
- [ ] group remove G a (positional)
- [ ] group delete N --yes (not --confirm)
- [ ] feature set-definition N --sql "..." (not --type sql --definition)
- [ ] feature diff N --v1 1 --v2 2 (not --from --to)
- [ ] feature rollback N --version 1 (not --to 1)

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
