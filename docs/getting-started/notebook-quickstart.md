# Notebook quickstart

This page gets a Jupyter notebook talking to featcat in five lines. Assumes the [server is running](installation.md#production-via-docker-compose) at `http://localhost:8000` (or wherever your team's instance lives).

## Install the SDK

In a terminal where your notebook env lives:

```bash
uv pip install ./packages/client
# or directly from git:
uv pip install "git+https://github.com/codepawl/featcat.git#subdirectory=packages/client"
```

The SDK is intentionally lean: just `httpx`, `pydantic`, `polars`, `pyarrow`. **No** torch, **no** Celery, **no** server deps.

## Five-line "first DataFrame"

```python
from featcat_client import FeatCatClient

client = FeatCatClient("http://localhost:8000", actor="alice-churn-notebook")
df = client.read_feature("user_behavior.session_count_30d")
df.head()
```

That's a `polars.DataFrame` with a single column. The SDK figured out which Parquet file the feature lives in via two API hops, then read it via `pyarrow`. Subsequent reads in the same kernel hit an `lru_cache(64)` so you don't pay the disk cost twice.

## Common patterns

### List features by source / tag / dtype

```python
features = client.list_features(source="user_behavior", tag="churn", dtype="int64")
for f in features:
    print(f.name, f.dtype, f.tags)
```

### Find similar features

```python
similar = client.find_similar("user_behavior.session_count_30d", top_k=5)
for f in similar:
    print(f.name)
```

When the server has [embeddings enabled](../architecture/ai.md) *(coming soon)* this uses pgvector cosine. Otherwise it falls back to TF-IDF over names + tags + descriptions. Same client call either way.

### Pull a whole feature group as one joined frame

```python
detail = client.get_group("churn_v2")
df = detail.to_polars(entity_key="user_id")  # joins all member parquets on user_id
df.head()
```

If you don't pass `entity_key`, the SDK auto-detects it from columns shared across all members (preferring `user_id`, `session_id`, `id`, `entity_id`, `device_id`). Ambiguous cases raise with the candidate list so you can pick.

`detail.to_pandas(...)` returns the same thing as a pandas DataFrame — requires the `[pandas]` extra: `uv pip install "featcat-client[pandas]"`.

### Natural-language search

```python
results = client.search("user activity in the last 30 days")
for f in results:
    print(f.name)
```

This calls the same TF-IDF + (when available) embedding pipeline the chat UI uses.

## Notebook hygiene

A few notebook-friendly conventions worth adopting:

```python
client = FeatCatClient(
    base_url="http://featcat-server:8000",
    actor="alice-churn-v2",          # shows up as X-Featcat-Actor in server logs
    connect_timeout=5.0,
    read_timeout=30.0,
    max_retries=3,                    # retries 5xx with exponential backoff
)
```

`actor` is opaque metadata — treat it like a User-Agent string, not a credential. If your server is protected by `FEATCAT_SERVER_AUTH_TOKEN` or an SSO proxy, use the client only against an authenticated deployment; the actor field itself is still for tracing who pulled what during incident reviews.

## When things go wrong

The SDK wraps every server failure in a typed exception:

```python
from featcat_client import FeatureNotFound, ConnectionError, ServerError

try:
    df = client.read_feature("user_behavior.session_count_30d")
except FeatureNotFound as e:
    print(f"Not found: {e.name}")
except ConnectionError:
    print("Server unreachable — is featcat-server running?")
except ServerError as e:
    print(f"Server returned HTTP {e.status_code}: {e.body}")
```

Caching: parquet reads are LRU-cached at module level (size 64). If the underlying file changes during a kernel session, restart the kernel to drop the cache. There's no force-refresh API today.

## What's next

- **[SDK Quickstart](../sdk/quickstart.md)** — the full method-by-method walkthrough.
- **[SDK Reference](../sdk/reference.md)** *(coming soon)* — every public class and method.
- **[Cookbook](../sdk/cookbook.md)** *(coming soon)* — recipes for common notebook workflows: feature discovery, cross-source joins, drift inspection.
