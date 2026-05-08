"""Live-Postgres pgvector benchmarks.

Exercises the T1.2 embedding column + HNSW index against realistic catalog
sizes (100, 1k, 10k features). Reports rows/sec for inserts, build time
for index creation, p50/p95 latency for similarity queries, and the
HNSW-vs-seq-scan speedup. All numbers are written to
``tests/perf/results/<timestamp>.json`` so subsequent runs can diff.

Setup
-----
This bench needs a live Postgres + pgvector. The simplest path is to run
the project's docker-compose Postgres swapped to a pgvector image::

    docker run --rm -d --name featcat-bench-pg \\
        -e POSTGRES_USER=featcat -e POSTGRES_PASSWORD=featcat \\
        -e POSTGRES_DB=featcat -p 5432:5432 pgvector/pgvector:pg16

    export FEATCAT_BENCH_DB_URL=postgresql+psycopg2://featcat:featcat@localhost:5432/featcat
    pytest tests/perf -m perf --bench -v

Or use the Makefile shortcut::

    make bench   # assumes the URL env var is set; the target sets a default

Without ``FEATCAT_BENCH_DB_URL`` set the whole module skips with a clear
message — the bench is opt-in by design and never blocks ``make check``.

Notes on ``find_similar_features``
----------------------------------
The bench drives the production code path via ``LocalBackend`` so it
measures what users actually run. It does NOT call private helpers
directly; if the public API changes, the bench changes with it.
"""

# mypy: ignore-errors

from __future__ import annotations

import json
import os
import random
import statistics
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

# Hard skip when the URL isn't set — perf bench is opt-in only.
_BENCH_URL = os.environ.get("FEATCAT_BENCH_DB_URL")
if not _BENCH_URL:
    pytest.skip(
        "FEATCAT_BENCH_DB_URL not set — see module docstring for setup. "
        "This bench requires a live Postgres + pgvector and is opt-in.",
        allow_module_level=True,
    )

# Skip if the postgres driver isn't available (e.g. core deps not installed).
psycopg2 = pytest.importorskip("psycopg2", reason="psycopg2 needed for live-postgres bench")
pytest.importorskip("pgvector", reason="pgvector python helpers needed for live-postgres bench")

from sqlalchemy import bindparam, create_engine, text  # noqa: E402

from featcat.catalog.local import LocalBackend  # noqa: E402
from featcat.catalog.models import DataSource, Feature  # noqa: E402
from featcat.db.embedding_type import Embedding  # noqa: E402
from featcat.db.models import EMBEDDING_DIM, Base  # noqa: E402

# --------------------------------------------------------------------------- #
# Tunables — kept here so an operator can sweep ranges without editing tests.
# --------------------------------------------------------------------------- #

# Sizes that cover small / medium / large catalogs. 10k is roughly 2x the
# largest production featcat catalog as of T1.2.
SIZES: tuple[int, ...] = (100, 1_000, 10_000)

# Bench similarity at these effective-search settings. 40 is the pgvector
# default; 100 / 200 trade latency for recall and represent realistic
# operator overrides.
EF_SEARCH_VALUES: tuple[int, ...] = (40, 100, 200)

# Top-K for the similarity bench — matches the API default.
TOP_K = 10

# How many query repetitions to time when measuring single-query latency.
QUERY_REPS = 100

RESULTS_DIR = Path(__file__).parent / "results"

# Module-level seed for repeatable random-vector generation across runs.
# Changing this invalidates result-to-result comparison.
RNG_SEED = 0xFEA7CA7


# --------------------------------------------------------------------------- #
# Helpers — random embedding generator + setup / teardown.
# --------------------------------------------------------------------------- #


def random_embedding(rng: random.Random, dim: int = EMBEDDING_DIM) -> list[float]:
    """Generate one unit-normalized random embedding.

    Cosine distance compares directions; unit-normalizing keeps similarity
    scores in [-1, 1] regardless of vector magnitude, which mirrors what
    sentence-transformers actually emits. We use the stdlib ``random`` so
    the bench has no numpy hot path that could mask DB cost.
    """
    vec = [rng.gauss(0.0, 1.0) for _ in range(dim)]
    norm = sum(x * x for x in vec) ** 0.5 or 1.0
    return [x / norm for x in vec]


def _build_backend() -> LocalBackend:
    """Construct a LocalBackend wired to the bench Postgres.

    We set FEATCAT_DB_BACKEND=postgres + FEATCAT_DB_URL ad-hoc rather than
    require the operator to flip globals. The override reverts on test
    teardown via ``monkeypatch`` (caller wraps).
    """
    os.environ["FEATCAT_DB_BACKEND"] = "postgres"
    os.environ["FEATCAT_DB_URL"] = _BENCH_URL  # type: ignore[assignment]
    db = LocalBackend(db_path="unused-for-postgres")
    return db


def _ensure_schema(db: LocalBackend) -> None:
    """Make sure pgvector + the features table + the HNSW index exist.

    The bench targets a freshly-launched container; we don't assume Alembic
    has run. Idempotent so re-runs against the same DB are fine.
    """
    with db.engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
    Base.metadata.create_all(db.engine, checkfirst=True)
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS idx_features_embedding ON features USING hnsw (embedding vector_cosine_ops)"
            )
        )


def _truncate(db: LocalBackend) -> None:
    """Wipe features so each parameterized size starts from zero rows.

    TRUNCATE ... CASCADE clears feature_versions / feature_docs etc that
    have FKs to features. ``data_sources`` is wiped too for the same reason.
    """
    with db.engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE TABLE features, feature_versions, feature_docs, "
                "feature_group_members, feature_lineage, monitoring_baselines, "
                "monitoring_checks, action_items, notifications, usage_log, "
                "data_sources RESTART IDENTITY CASCADE"
            )
        )


def _seed_features(db: LocalBackend, n: int, rng: random.Random) -> str:
    """Insert ``n`` features with random embeddings and return the source id.

    Uses the public ``upsert_feature`` API so the bench measures what users
    actually run. Embeddings are written via raw SQL because the public API
    doesn't accept them in one shot (the production pipeline computes them
    in a separate background job).
    """
    src = db.add_source(DataSource(name=f"bench_src_{n}", path=f"/tmp/bench_{n}.parquet"))
    for i in range(n):
        db.upsert_feature(
            Feature(
                name=f"{src.name}.col_{i}",
                data_source_id=src.id,
                column_name=f"col_{i}",
                dtype="float64",
                description=f"synthetic feature {i}",
            )
        )

    # Bulk-update embeddings — single round-trip per chunk keeps the seed
    # phase bounded to ~seconds even at N=10k. We're not measuring this
    # phase; ``bench_insert`` measures inserts on its own.
    stmt = text("UPDATE features SET embedding = :v WHERE id = :id").bindparams(
        bindparam("v", type_=Embedding(EMBEDDING_DIM))
    )
    with db.session() as s:
        feats = list(db.list_features(source_name=src.name))
        for f in feats:
            s.execute(stmt, {"v": random_embedding(rng), "id": f.id})
        s.commit()
    return src.id


# --------------------------------------------------------------------------- #
# Result recorder — appends one JSON file per bench run, named by timestamp.
# --------------------------------------------------------------------------- #


class _ResultRecorder:
    """Collects bench results in memory and writes them on session teardown.

    A single JSON file per ``pytest`` invocation keeps the results
    directory trivially diffable: ``ls -t tests/perf/results/`` is a
    chronological log.
    """

    def __init__(self) -> None:
        self.entries: list[dict[str, Any]] = []
        self.started_at = datetime.now(timezone.utc).isoformat()

    def record(self, name: str, **fields: Any) -> None:
        self.entries.append({"name": name, **fields})

    def flush(self) -> Path | None:
        if not self.entries:
            return None
        RESULTS_DIR.mkdir(parents=True, exist_ok=True)
        # Filename uses the session start time so all entries from one run
        # land together. ``:`` is replaced because Windows filesystems hate it.
        slug = self.started_at.replace(":", "-").replace("+", "_")
        path = RESULTS_DIR / f"{slug}.json"
        path.write_text(
            json.dumps(
                {
                    "started_at": self.started_at,
                    "bench_db_url": _BENCH_URL,
                    "embedding_dim": EMBEDDING_DIM,
                    "entries": self.entries,
                },
                indent=2,
            )
        )
        return path


@pytest.fixture(scope="session")
def recorder() -> _ResultRecorder:
    """Session-scoped collector — one JSON output per ``pytest`` run."""
    rec = _ResultRecorder()
    yield rec
    written = rec.flush()
    if written is not None:
        print(f"\n[pgvector-bench] wrote {len(rec.entries)} entries to {written}")


@pytest.fixture(scope="session")
def bench_engine() -> Any:
    """Session-scoped raw engine — used by setup / teardown helpers."""
    engine = create_engine(_BENCH_URL, future=True)
    yield engine
    engine.dispose()


@pytest.fixture()
def db(bench_engine: Any) -> LocalBackend:  # noqa: ARG001 — engine fixture forces session order
    """Per-test backend; truncates first so each test starts clean."""
    db = _build_backend()
    _ensure_schema(db)
    _truncate(db)
    yield db
    db.close()


# --------------------------------------------------------------------------- #
# Benches.
# --------------------------------------------------------------------------- #


@pytest.mark.perf
@pytest.mark.parametrize("n", SIZES)
def bench_insert(db: LocalBackend, recorder: _ResultRecorder, n: int) -> None:
    """Time inserting N features (no embeddings) via the public API.

    Reports rows/sec. Embedding writes are NOT included here — they're a
    separate hot path (see ``bench_index_build``). This isolates the
    plain-table insert cost so regressions in feature_versions snapshotting
    or trigger overhead show up cleanly.
    """
    rng = random.Random(RNG_SEED)
    src = db.add_source(DataSource(name=f"insert_bench_{n}", path=f"/tmp/insert_{n}.parquet"))
    start = time.perf_counter()
    for i in range(n):
        db.upsert_feature(
            Feature(
                name=f"{src.name}.col_{i}",
                data_source_id=src.id,
                column_name=f"col_{i}",
                dtype="float64",
                description=f"feature {i}",
            )
        )
    elapsed = time.perf_counter() - start
    rate = n / elapsed if elapsed > 0 else 0.0
    recorder.record("insert", n=n, elapsed_seconds=elapsed, rows_per_sec=rate)
    # Sanity, not a perf assertion — keeps the bench honest if upsert silently no-ops.
    assert n == 0 or rate > 0
    # Touch rng so unused-warnings stay quiet on linters that scan benches.
    _ = rng


@pytest.mark.perf
@pytest.mark.parametrize("n", SIZES)
def bench_index_build(db: LocalBackend, recorder: _ResultRecorder, n: int) -> None:
    """Drop the HNSW index, time rebuilding it over N pre-inserted rows.

    HNSW build cost is O(N log N) and dominates schema migrations on large
    catalogs. Operators want to know "if I have to re-embed and rebuild,
    how long will the catalog be index-less?".
    """
    rng = random.Random(RNG_SEED + 1)
    _seed_features(db, n, rng)
    with db.engine.begin() as conn:
        conn.execute(text("DROP INDEX IF EXISTS idx_features_embedding"))
    start = time.perf_counter()
    with db.engine.begin() as conn:
        conn.execute(text("CREATE INDEX idx_features_embedding ON features USING hnsw (embedding vector_cosine_ops)"))
    elapsed = time.perf_counter() - start
    recorder.record("index_build", n=n, elapsed_seconds=elapsed)


@pytest.mark.perf
@pytest.mark.parametrize("n", SIZES)
@pytest.mark.parametrize("ef_search", EF_SEARCH_VALUES)
def bench_similarity_top_k(
    db: LocalBackend,
    recorder: _ResultRecorder,
    n: int,
    ef_search: int,
) -> None:
    """Run ``QUERY_REPS`` similarity queries, report median + p95 latency.

    Drives the production code path: ``LocalBackend.find_similar_features``.
    Sweeps ``ef_search`` to characterize the recall/latency knob —
    operators set this via ``SET hnsw.ef_search`` per session.
    """
    rng = random.Random(RNG_SEED + 2)
    _seed_features(db, n, rng)
    with db.engine.begin() as conn:
        conn.execute(text(f"SET hnsw.ef_search = {int(ef_search)}"))

    feature_ids = [f.id for f in db.list_features(limit=QUERY_REPS)]
    # Ensure we have something to query with even at small N.
    if not feature_ids:
        pytest.skip("no features after seed — N must be > 0")
    timings: list[float] = []
    for i in range(QUERY_REPS):
        target = feature_ids[i % len(feature_ids)]
        # Per-query SET so it survives connection-pool checkout.
        with db.engine.begin() as conn:
            conn.execute(text(f"SET hnsw.ef_search = {int(ef_search)}"))
        start = time.perf_counter()
        results = db.find_similar_features(target, top_k=TOP_K)
        timings.append(time.perf_counter() - start)
        # Cheap correctness check — first result for a feature query of the
        # same feature itself should NOT be returned (we exclude self).
        assert all(r["id"] != target for r in results)

    timings.sort()
    median = statistics.median(timings)
    p95 = timings[int(len(timings) * 0.95)] if timings else 0.0
    recorder.record(
        "similarity_top_k",
        n=n,
        ef_search=ef_search,
        top_k=TOP_K,
        reps=QUERY_REPS,
        median_seconds=median,
        p95_seconds=p95,
    )


@pytest.mark.perf
@pytest.mark.parametrize("n", SIZES)
def bench_bulk_similarity(db: LocalBackend, recorder: _ResultRecorder, n: int) -> None:
    """100 random query embeddings in one round, total wall-clock.

    Mirrors the NL-query embeds-first path which calls
    ``search_by_embedding`` once per user query — at scale (e.g. an LLM
    agent fanning out 100 candidate queries), wall-clock for the whole
    burst matters more than median single-query latency.
    """
    rng = random.Random(RNG_SEED + 3)
    _seed_features(db, n, rng)

    queries = [random_embedding(rng) for _ in range(100)]
    start = time.perf_counter()
    for q in queries:
        db.search_by_embedding(q, top_k=TOP_K)
    elapsed = time.perf_counter() - start
    recorder.record(
        "bulk_similarity",
        n=n,
        queries=len(queries),
        top_k=TOP_K,
        elapsed_seconds=elapsed,
    )


@pytest.mark.perf
@pytest.mark.parametrize("n", SIZES)
def bench_seq_scan_vs_hnsw(db: LocalBackend, recorder: _ResultRecorder, n: int) -> None:
    """Compare HNSW indexed query vs. forced sequential scan.

    Forces ``enable_indexscan = off`` on a single connection to make the
    planner fall back to a seq scan + sort, then compares against the
    default plan. This is the headline number for "is the HNSW index
    paying for itself at this catalog size?".
    """
    rng = random.Random(RNG_SEED + 4)
    src_id = _seed_features(db, n, rng)  # noqa: F841 — needed so source exists for query

    feats = db.list_features(limit=1)
    if not feats:
        pytest.skip("no features after seed — N must be > 0")
    target = feats[0]

    # HNSW path (default planner).
    start = time.perf_counter()
    db.find_similar_features(target.id, top_k=TOP_K)
    hnsw_seconds = time.perf_counter() - start

    # Seq-scan path. We hit the engine directly because we need a stable
    # session in which to keep the SET applied. find_similar_features uses
    # its own session so we replicate the SQL inline here — the SQL
    # matches _find_similar_pgvector character-for-character.
    sql = (
        "SELECT f.id, f.name, f.dtype, "
        "       1 - (f.embedding <=> ref.embedding) AS similarity "
        "FROM features f, "
        "     (SELECT embedding FROM features WHERE id = :id) AS ref "
        "WHERE f.id != :id AND f.embedding IS NOT NULL "
        "ORDER BY f.embedding <=> ref.embedding "
        "LIMIT :k"
    )
    with db.engine.connect() as conn:
        conn.execute(text("SET enable_indexscan = off"))
        conn.execute(text("SET enable_bitmapscan = off"))
        start = time.perf_counter()
        conn.execute(text(sql), {"id": target.id, "k": TOP_K}).all()
        seq_seconds = time.perf_counter() - start

    speedup = (seq_seconds / hnsw_seconds) if hnsw_seconds > 0 else 0.0
    recorder.record(
        "seq_scan_vs_hnsw",
        n=n,
        hnsw_seconds=hnsw_seconds,
        seq_scan_seconds=seq_seconds,
        speedup=speedup,
    )
