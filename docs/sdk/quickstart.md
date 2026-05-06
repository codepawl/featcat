# SDK quickstart

The `featcat-client` package is a sync HTTP client for the featcat REST API, plus polars-shaped DataFrame helpers for pulling Parquet data.

```python
from featcat_client import FeatCatClient
client = FeatCatClient("http://localhost:8000", actor="my-notebook")
```

That's the whole construction. There's no auth handshake, no async setup, no `await`. Sync was a deliberate choice — notebooks are sync; threading a single `httpx.Client` is fine for the catalog use case.

## Method tour

### Sources

```python
client.list_sources()                        # → list[DataSource]
client.get_source("user_behavior")           # → DataSource | raise FeatureNotFound
```

### Features

```python
client.list_features(
    source="user_behavior",
    tag="churn",
    dtype="float64",
    owner="data-team",
    has_doc=True,
    sort="name",
    order="asc",
)                                            # → list[Feature]

client.get_feature("user_behavior.session_count_30d")     # → Feature
client.get_path("user_behavior.session_count_30d")        # → str (parquet path)
client.read_feature("user_behavior.session_count_30d")    # → polars.DataFrame
```

`get_feature` and `get_path` are two HTTP round-trips (feature → source). `read_feature` adds one parquet read on top, cached per-process.

### Search + similarity

```python
client.search("user activity in 30 days", limit=20)        # → list[Feature]
client.find_similar(
    "user_behavior.session_count_30d",
    top_k=10,
    threshold=0.3,
)                                                          # → list[Feature]
```

`find_similar` calls `/api/features/by-name/similar` first (server picks pgvector or TF-IDF). Falls back to walking the legacy similarity-graph endpoint when the new endpoint isn't there (older servers).

### Groups

```python
client.list_groups(project="ml-team")                      # → list[FeatureGroup]
detail = client.get_group("churn_v2")                      # → FeatureGroupDetail
detail.members                                              # list[Feature]

# Joined DataFrame
df = detail.to_polars(entity_key="user_id")
df_pd = detail.to_pandas(entity_key="user_id")             # needs [pandas] extra
```

Auto-detect of `entity_key`: SDK intersects non-feature columns across member parquets, prefers `user_id` / `session_id` / `id` / `entity_id` / `device_id`. Raises with the candidate set if ambiguous.

### Usage stats

```python
client.get_feature_usage("user_behavior.session_count_30d")
# → FeatureUsage(views=42, queries=11, total=53, last_seen=..., daily=[{"date": "...", "count": 7}, ...])
```

## Configuration

```python
FeatCatClient(
    base_url="http://featcat-server:8000",
    actor="ds-pipeline-v2",       # sent as X-Featcat-Actor for server-side traceability
    connect_timeout=5.0,          # seconds
    read_timeout=30.0,
    max_retries=3,                # retries 5xx with exponential backoff (0.25 × 2^n)
    transport=None,               # inject httpx.MockTransport for tests
)
```

The `transport` arg is the test seam — pass an `httpx.MockTransport(handler)` to drive the client offline; that's what the SDK's own pytest suite does.

## Errors

All client-side failures inherit from `FeatCatError`:

| Class | When |
|---|---|
| `FeatCatError` | Base — catch this if you don't care which kind |
| `ConnectionError` | Server unreachable after `max_retries` |
| `ServerError(status_code, body)` | Non-2xx that isn't a recognized special case |
| `FeatureNotFound(name)` | 404 on a feature lookup |
| `GroupNotFound(name)` | 404 on a group lookup |

```python
from featcat_client import FeatureNotFound, ConnectionError

try:
    feat = client.get_feature("user_behavior.session_count_30d")
except FeatureNotFound as e:
    print(f"Missing: {e.name}")
except ConnectionError:
    print("Server unreachable — check `docker compose ps featcat`")
```

## Caching

Two layers, both per-process:

- **HTTP GETs**: 10-second client-side cache for read endpoints. Mutations bypass and invalidate by prefix.
- **Parquet reads**: `lru_cache(maxsize=64)` keyed on path. Restart the kernel to drop.

There's deliberately no remote cache (no Redis, no etag handshakes) — featcat catalog state is small enough that a 10-second TTL is fine, and notebook users don't want surprise staleness.

## Lifecycle

```python
# Context manager closes the underlying httpx.Client
with FeatCatClient("http://...") as client:
    feat = client.get_feature("...")
# httpx connection released

# Manual:
client = FeatCatClient(...)
try:
    ...
finally:
    client.close()
```

## What's next

- **[SDK Reference](reference.md)** *(coming soon)* — every public class and method, auto-generated from docstrings via `mkdocstrings`.
- **[Cookbook](cookbook.md)** *(coming soon)* — recipes for cross-source joins, drift inspection, bulk metadata edits.
- **[Notebook Quickstart](../getting-started/notebook-quickstart.md)** — the same content but framed for first-time notebook users.
