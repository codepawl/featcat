# Testing

featcat's test suite is the spec for the catalog's contracts. ~415 tests on staging, ~3 minutes wall-clock on a laptop. This page covers what's where, what to write, and how to run things.

## Layout

```
tests/
├── conftest.py              # shared fixtures (in_memory_backend, tmp_catalog, etc.)
├── fixtures/                # parquet test data
├── test_catalog.py          # CatalogBackend contract
├── test_features_routes.py  # FastAPI route tests via TestClient
├── test_groups.py
├── test_certification.py
├── test_full_text_search.py
├── test_lineage.py
├── test_monitoring.py
├── test_notifications.py
├── test_scheduler.py
├── test_celery_tasks.py     # gated by importorskip("celery")
├── test_sdk_client.py       # uses httpx.MockTransport
└── perf/                    # opt-in timing tests; not run by default
```

Naming is `test_<topic>.py`. One topic per file. When a file grows past 500 lines, split.

## Fixtures

Most useful ones, defined in `tests/conftest.py`:

- **`in_memory_backend`** — fresh `LocalBackend` against `:memory:` SQLite. Use this for unit tests that hit the catalog directly. Cheap (~5ms setup), isolated per test.
- **`tmp_catalog`** — like above but a temp file, so multiple connections can share state. Use for tests that need cross-thread / cross-process behavior.
- **`feature_minimal`** — pre-populated catalog with one source + 3 features, no docs. Good base for feature-flow tests.
- **`feature_ready`** — same, but with docs + baselines. Use when you need a "complete" feature (e.g. certification readiness check).
- **`api_client`** — FastAPI `TestClient` with `in_memory_backend` injected. Use for route tests.
- **`mock_llm`** — `BaseLLM` stub returning canned strings. Use anywhere the production code calls into LLM.

Add a fixture to `conftest.py` only if it's used in 2+ files. Otherwise local to the test file.

## Backend tests

The `CatalogBackend` ABC is the contract. Every method is tested via `LocalBackend` (since it's the only real impl). Pattern:

```python
def test_list_features_filters_by_source(in_memory_backend):
    backend = in_memory_backend
    backend.add_source(name="src_a", path="/a.parquet")
    backend.add_source(name="src_b", path="/b.parquet")
    backend.add_feature(name="src_a.col1", source_name="src_a")
    backend.add_feature(name="src_b.col1", source_name="src_b")

    result = backend.list_features(source_name="src_a")

    assert [f.name for f in result] == ["src_a.col1"]
```

Arrange-act-assert, with whitespace separating the three. Don't combine multiple behaviors in one test.

## Route tests

Use the `api_client` fixture and the FastAPI `TestClient`. Don't mock the backend — let it hit the in-memory SQLite. That way you're testing the actual SQL.

```python
def test_get_feature_by_name(api_client, feature_minimal):
    resp = api_client.get("/api/features/by-name?name=src.col1")
    assert resp.status_code == 200
    assert resp.json()["name"] == "src.col1"
```

For routes that call the LLM, inject `mock_llm` via the lifespan override:

```python
def test_chat_streams_tokens(api_client_with_mock_llm):
    with api_client_with_mock_llm.stream("POST", "/api/ai/chat",
                                          json={"messages": [{"role": "user", "content": "..."}]}) as r:
        events = list(r.iter_lines())
        assert any("token" in e for e in events)
```

## Optional-extra tests

Tests that need an extra (`celery`, `sentence-transformers`, `polars`) gate themselves with `importorskip`:

```python
import pytest
pytest.importorskip("celery")    # at module level → skip whole file
pytest.importorskip("sentence_transformers", reason="needs [embeddings] extra")
```

CI runs the suite with `[all]` installed once and with `[dev]` only once. The default install must pass without any extra.

## Performance tests

`tests/perf/` runs only with `pytest tests/perf -m perf`. Each test asserts a wall-clock budget:

```python
@pytest.mark.perf
def test_list_features_p99_under_100ms(in_memory_backend, benchmark):
    populate_n_features(in_memory_backend, 10_000)
    result = benchmark(in_memory_backend.list_features, limit=50)
    assert benchmark.stats["mean"] < 0.1   # 100ms
```

Don't put perf tests in the default suite — they'll go red on slow CI runners.

## Running

```bash
make test                           # full suite, ~3 min
pytest -x                           # stop on first failure
pytest --lf                         # last-failed only (fast iteration)
pytest -k "search or fts"           # name filter
pytest tests/test_catalog.py -v     # one file, verbose
pytest -n auto                      # parallel (needs pytest-xdist)
make test-cov                       # with htmlcov/index.html report
```

CI runs `make check` which is `lint + type-check + test`. Pre-commit runs lint only — type-check + test don't gate commits, only PR merges.

## What to write tests for

| Worth testing | Skip |
|---|---|
| Public API behavior (CLI commands, route responses, SDK methods) | Trivial getters / setters |
| Error paths that callers must handle (`FeatureNotFound`, `ValidationError`) | Errors that "can't happen" |
| Cross-dialect SQL (sqlite + postgres) when the queries differ | Queries that are dialect-clean |
| Migrations — at least an upgrade-then-downgrade smoke test | Auto-generated parts of migrations |
| Bug fixes — regression test, in the same PR | Stylistic refactors |
| Concurrency-sensitive code (scheduler, threadpool routes) | Pure transformations |
| Anything you'd be surprised to see break | Compiler-checkable correctness |

If a behavior changes, the tests exercising it should change too. A green suite after a behavior change with no test diff is a code smell.

## Test data

`tests/fixtures/*.parquet` are committed (small, < 100KB each). For larger generated data, use `tests/perf/_generate.py` which creates synthetic data on the fly.

Don't commit large test data. Don't commit recorded LLM responses (the cache layer makes them pointless).

## Common patterns

### Testing a CLI command

Use Typer's `CliRunner`:

```python
from typer.testing import CliRunner
from featcat.cli import app

runner = CliRunner()

def test_features_list(in_memory_backend, monkeypatch):
    monkeypatch.setattr("featcat.cli._get_db", lambda: in_memory_backend)
    result = runner.invoke(app, ["features", "list", "--limit", "5"])
    assert result.exit_code == 0
```

### Testing SSE / streaming

```python
def test_chat_stream(api_client_with_mock_llm):
    with api_client_with_mock_llm.stream("POST", "/api/ai/chat",
                                          json={"messages": [{"role": "user", "content": "hi"}]}) as r:
        lines = [line for line in r.iter_lines() if line]
        assert any(line.startswith("event: token") for line in lines)
        assert any(line.startswith("event: done") for line in lines)
```

### Testing migrations

```python
def test_migration_round_trip(tmp_path):
    db_url = f"sqlite:///{tmp_path}/test.db"
    config = make_alembic_config(db_url)

    command.upgrade(config, "head")
    command.downgrade(config, "-1")
    command.upgrade(config, "head")
    # asserts no exceptions
```

## Flakes

If a test is flaky, *fix it or delete it* — never xfail-and-forget. Common causes:

- Time-based assertions without `freezegun` or fixed `now()`.
- Unordered SQL results compared with `==`. Use `set` or `sorted`.
- Network calls. Mock with `httpx.MockTransport` (SDK), `responses`/`respx` (server-side).

## Related

- **[Setup](setup.md)** — get pytest running
- **[Style](style.md)** — code conventions, including test code
- **[Architecture Overview](../architecture/overview.md)** — context for what each test covers
