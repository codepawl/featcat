# Benchmarks

Performance benches live in `tests/perf/` and are **never collected by default**. They need a live Postgres + pgvector and can take minutes to run; running them in `make check` would block every CI job and pre-commit.

## Live-Postgres pgvector bench

Exercises the T1.2 embedding column + HNSW index against realistic catalog sizes (100, 1k, 10k features). Reports rows/sec for inserts, build time for the HNSW index, p50/p95 latency for similarity queries, and the HNSW-vs-seq-scan speedup.

### Setup

1. Start the `pgvector/pgvector:pg16` Postgres container (same image the deploy stack uses, with `pgvector` pre-installed):

   ```bash
   docker run --rm -d --name featcat-bench-pg \
       -e POSTGRES_USER=featcat \
       -e POSTGRES_PASSWORD=featcat \
       -e POSTGRES_DB=featcat \
       -p 5432:5432 \
       pgvector/pgvector:pg16
   ```

2. Install the optional `[bench]` extra (this brings in `pytest-benchmark`):

   ```bash
   uv pip install -e ".[bench]"
   ```

3. Run the bench:

   ```bash
   make bench
   ```

   …or invoke directly:

   ```bash
   FEATCAT_BENCH_DB_URL=postgresql+psycopg2://featcat:featcat@localhost:5432/featcat \
       uv run pytest tests/perf -m perf --bench -v
   ```

The bench creates the `vector` extension, the schema, and the HNSW index on first run. Re-running against the same container is fine — each test truncates `features` before seeding.

### Results

Each run writes a JSON file to `tests/perf/results/<UTC-timestamp>.json` with one entry per bench case:

```json
{
  "started_at": "2026-05-08T11:30:00+00:00",
  "bench_db_url": "postgresql+psycopg2://...",
  "embedding_dim": 384,
  "entries": [
    {"name": "insert", "n": 1000, "elapsed_seconds": 0.42, "rows_per_sec": 2380.9},
    {"name": "index_build", "n": 1000, "elapsed_seconds": 0.18},
    {"name": "similarity_top_k", "n": 1000, "ef_search": 40, "median_seconds": 0.0021, "p95_seconds": 0.0033},
    ...
  ]
}
```

`tests/perf/results/` is committed (small files, useful for trend tracking). Diff two runs with `jq` or any text diff tool.

### Cases

| Bench | What it measures | Why it matters |
|---|---|---|
| `bench_insert` | rows/sec for `upsert_feature` | catches regressions in versioning trigger / `feature_versions` snapshot overhead |
| `bench_index_build` | wall-clock to build the HNSW index | tells operators how long re-embedding takes the catalog out of service |
| `bench_similarity_top_k` | median + p95 latency, parameterized over `ef_search` | sets expectation for `find_similar_features` (and the `/api/features/<id>/similar` endpoint) at production scale |
| `bench_bulk_similarity` | wall-clock for 100 query embeddings in one round | mirrors NL-query embeds-first fan-out cost |
| `bench_seq_scan_vs_hnsw` | speedup factor vs forced seq scan | proves the HNSW index is paying for itself at the tested catalog size |

### Why it's gated

The bench is double-gated:

1. `@pytest.mark.perf` — registered marker, required on every bench function
2. `--bench` CLI flag — declared in `tests/perf/conftest.py`; without it, perf tests are skipped (not deselected, so the skip count is visible)

Plus a module-level `pytest.skip(...)` if `FEATCAT_BENCH_DB_URL` is missing. Three layers ensures the bench cannot accidentally run in CI / pre-commit.
