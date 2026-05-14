# Documentation generation

Auto-generated documentation is featcat's core value-add: every feature gets a short description, long description, expected ranges, and gotchas — written by the local LLM from the feature's stats and (optionally) hints you provide.

## When to use it

- **Right after a fresh scan**, so newly registered features don't sit in the catalog with empty descriptions.
- **After a schema change**, to refresh descriptions that may now be wrong.
- **Before certifying** a feature, since `certified` status requires a doc to be present.
- **When stats shift significantly**, since the model uses stats for context — old docs may describe a different distribution.

## Generating docs

For a single feature:

```bash
featcat docs generate user_behavior.session_count_30d
```

For all features in a source (most common at first scan):

```bash
featcat docs generate --source user_behavior
```

For a group:

```bash
featcat groups regenerate-docs churn_v2
```

For everything missing docs (catch-up batch):

```bash
featcat docs generate --missing-only
```

## Watching progress

Generation is async. The CLI returns a `job_id`; poll with:

```bash
featcat docs status --job <job_id>
# Documented: 12 / 50 (24%) — running
# ETA ~ 4m12s
```

Or watch in the web UI: the Features page shows a progress banner while a doc batch is running, and feature rows pulse as they're completed.

`GET /api/docs/generate-batch/{job_id}/status` is the API equivalent if you want to drive it from a pipeline. Returns:

```json
{
  "job_id": "doc-gen-20250506-091322",
  "total": 50,
  "completed": 12,
  "failed": 0,
  "running": true,
  "started_at": "...",
  "eta_seconds": 252
}
```

## Hints

Hints are short snippets of context you give the LLM, persisted on the feature so future regenerations stay consistent.

```bash
featcat hints set user_behavior.session_count_30d \
    "Counts distinct sessions per user over the trailing 30 days. \
     Excludes sessions <2s (bot heuristic)."
```

Subsequent `docs generate` calls include the hint. Per-source hints (`featcat hints set --source user_behavior "..."`) apply to all features in that source unless overridden.

You can also pass a one-off hint at generate time without saving it:

```bash
featcat docs generate user_behavior.session_count_30d --hint "v2 sessionization rules"
```

Hints make the difference between docs that feel obvious and docs that feel right. The LLM has stats but no business context — give it the bot-filter rule, the v2 / v3 distinction, the unit, and so on.

## Organization context

When the whole catalog shares a domain (e.g. "telco churn prediction") you can pass the context once with `--context` instead of repeating it as per-feature hints. The string is injected into the prompt under an `ORG CONTEXT:` header and applies to every feature generated in that run:

```bash
featcat doc generate --context "FPT Telecom DS team — focus on churn and network quality"
featcat doc generate user_behavior.session_count_30d --context "Telco DS team"
```

`--context` is ignored in remote mode (the server uses its own configured context).

## Generated content

Each doc has these fields:

| Field | What it describes |
|---|---|
| `short_description` | One sentence, ≤ 140 chars. Suitable for a list view. |
| `long_description` | 2–4 paragraphs. Plain English, no jargon. |
| `expected_ranges` | "Typically 0–100 with a long tail to ~500." Calibrated to the stats. |
| `gotchas` | Bullet list of things that surprise new consumers (skewed distribution, post-hoc label leakage, etc.) |
| `last_generated` | Timestamp |
| `model` | Which LLM ran it (default: `gemma-4-E2B-it-Q4_K_M`) |

## Glossary

`featcat docs glossary` returns a deduped list of terms across all descriptions, useful for spotting inconsistent vocabulary ("session" vs "visit", "user" vs "device"). The web UI exposes this as the **Glossary** tab. Edit a term's canonical form and any future generation will use it.

## Doc debt

`GET /api/docs/stats/doc-debt` reports the catalog's documentation gap:

```json
{
  "total": 412,
  "documented": 287,
  "missing": 125,
  "stale": 18,         // doc older than feature stats
  "coverage_pct": 69.7
}
```

The dashboard shows this as a tile. Aim for ≥ 95 % before a sprint review.

## Caching

LLM responses cache to SQLite by prompt hash (`featcat/llm/cached.py`), so regenerating the same feature with the same hint and stats is free. Bust by passing `--force` to `docs generate`, which adds a salt to the prompt.

## Failure modes

- **"Generation failed: server unreachable"** — the local llama.cpp server is down. `docker compose ps llm` to check; the model can take ~30s to load on first call.
- **"Generated doc is just `{}`"** — the model returned malformed JSON. featcat retries with a stricter prompt; if it still fails, try a smaller batch (`--limit 5`) so one bad feature doesn't drag the rest down.
- **"Doc text matches another feature word-for-word"** — the LLM hallucinated based on similar names. Add a hint that distinguishes them.
- **"Doc says 'this feature counts unique users' but it counts sessions"** — wrong stats fed to the model. Re-scan the source so the latest stats are used, then regenerate.

## Related

- **[First Feature](../getting-started/first-feature.md)** — generation walkthrough
- **[Catalog browser](catalog.md)** — view generated docs
- **[Monitoring](monitoring.md)** — drift may invalidate descriptions
- **[AI assistant](ai.md)** — uses generated docs as context for chat answers
