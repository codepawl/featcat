# Your first feature

Five minutes, end-to-end. We'll register a Parquet source, scan it for features, generate documentation, and look at the result in the web UI.

## Prerequisites

- featcat installed locally (see [Installation](installation.md))
- A Parquet file you can point at — we'll use the bundled fixture as an example: `tests/fixtures/user_behavior_30d.parquet`
- The server running: `featcat serve --host 0.0.0.0 --port 8000`

## Step 1 — register the source

A *source* is a file path featcat will scan. Sources own *features* (one per column).

=== "CLI"

    ```bash
    featcat source add \
        user_behavior \
        tests/fixtures/user_behavior_30d.parquet \
        --description "Synthetic 30-day user behavior fixture"
    ```

=== "API"

    ```bash
    curl -X POST http://localhost:8000/api/sources \
        -H 'Content-Type: application/json' \
        -d '{
              "name": "user_behavior",
              "path": "tests/fixtures/user_behavior_30d.parquet",
              "description": "Synthetic 30-day user behavior fixture"
            }'
    ```

=== "Web UI"

    1. Open `http://localhost:8000`
    2. Click **+ Add source**
    3. Fill in name + path, click **Add**

The source appears in the catalog but has no features yet — we still need to scan it.

## Step 2 — scan for features

Scanning reads the Parquet schema + lightweight column statistics (mean, std, null ratio, etc.) and registers a *feature* per column.

```bash
featcat source scan user_behavior
```

Output:

```
Scanned user_behavior — registered 6 feature(s):
  user_behavior.user_id
  user_behavior.session_count_30d
  user_behavior.event_count_30d
  user_behavior.last_seen_at
  user_behavior.country
  user_behavior.is_premium
```

Each one is now in the catalog with auto-extracted dtype + stats.

## Step 3 — generate documentation

Most of the value of a catalog comes from explanations a human can read. featcat asks the local LLM for a short + long description per feature, plus expected ranges and potential issues.

```bash
featcat doc generate
```

This generates docs for all currently undocumented features. For one feature:

```bash
featcat doc generate user_behavior.session_count_30d
featcat doc stats
```

!!! tip "Generation hints"
    Persist context with `featcat feature set-hint user_behavior.session_count_30d --hint "Counts distinct sessions over a trailing 30-day window"`. Future doc generation includes that hint.

## Step 4 — set up monitoring

To know when a feature *drifts*, we save a baseline now and let the scheduler check against it daily:

```bash
featcat monitor baseline          # current stats become the baseline
```

The default scheduler runs `monitor_check` every 6 hours. Each check computes PSI (Population Stability Index) against the saved baseline; a PSI > 0.1 trips a warning, > 0.25 trips critical. Critical drift appears in [in-app notifications](../user-guide/notifications.md).

## Step 5 — explore in the web UI

Open `http://localhost:8000`. You'll see:

- **Dashboard** — counts, doc coverage, drift summary, recent activity
- **Features** — paginated list with filters (source, dtype, owner, has-doc, drift status). Click a row for the detail panel: full description, lineage, monitoring history, version log
- **Groups** — bundles of related features (e.g. `churn_v2`)
- **Chat** — natural-language queries against the catalog. Try *"which features in user_behavior look most relevant to predicting churn?"*

## Step 6 — pull the feature into a notebook

Once a feature exists in the catalog, the SDK gives you the Parquet data without you needing to remember the path:

```python
from featcat_client import FeatCatClient

client = FeatCatClient("http://localhost:8000")
df = client.read_feature("user_behavior.session_count_30d")
print(df.head())
```

→ [SDK Quickstart](../sdk/quickstart.md) for the full API.

## What's next

- **Group related features** so you can pull them as a single joined frame: see [User Guide › Feature Groups](../user-guide/groups.md).
- **Certify a feature for production**: when it has a doc + baseline + owner + group membership, run `featcat status set user_behavior.session_count_30d certified --notes "Q4 sign-off"`.
- **Search across the catalog** with full-text or natural-language queries: see [User Guide › Catalog Browser](../user-guide/catalog.md).

## Common first-feature questions

- **"My scan registered 0 features."** — Check the file is readable from inside the featcat process. In Docker, the path needs to be visible to the container; the bundled compose mounts `${DATA_DIR:-./data}` to `/sources`. Pass paths under `/sources/...`.
- **"Doc generation is stuck."** — `llama.cpp` takes ~30s to load on first request. Watch `docker compose logs -f llm` to see when it's ready. The doc generator retries with backoff; subsequent generations are fast (cached + warm).
- **"Why does PSI complain about a fresh feature?"** — The baseline is *now*, not history. PSI compares to a fixed reference, so the very next check should be near-zero. If you see drift right away, the underlying data changed between baseline-set and the next run.
