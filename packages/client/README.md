# featcat-client

Python SDK for the featcat feature catalog server. Lets data scientists pull feature metadata + Parquet data from a notebook in five lines.

## Install

```bash
# From a wheel
uv add ./packages/client
# Or from git
uv add "git+https://github.com/codepawl/featcat.git#subdirectory=packages/client"
```

## Quickstart

```python
from featcat_client import FeatCatClient

client = FeatCatClient(base_url="http://localhost:8000", actor="my-notebook")

# List features by source / tag / dtype
features = client.list_features(source="user_behavior", tag="churn")

# Single feature metadata
feat = client.get_feature("user_behavior.session_count_30d")

# Read a single column as a polars DataFrame
df = client.read_feature("user_behavior.session_count_30d")

# Search
results = client.search("user activity in 30 days")

# Find similar features (TF-IDF cosine)
similar = client.find_similar("user_behavior.session_count_30d", top_k=10)

# Get a group joined into one DataFrame
detail = client.get_group("churn_v2")
df = detail.to_polars(entity_key="user_id")
df_pd = detail.to_pandas(entity_key="user_id")  # requires pip install featcat-client[pandas]
```

## Configuration

```python
client = FeatCatClient(
    base_url="http://server:8000",
    actor="ds-pipeline-v2",         # sent as X-Featcat-Actor header for traceability
    connect_timeout=5.0,
    read_timeout=30.0,
    max_retries=3,                  # retries on 5xx with exponential backoff
)
```

## Errors

All client-side failures inherit from `FeatCatError`:

- `ConnectionError` — server unreachable after retries
- `ServerError(status_code, body)` — non-2xx the SDK doesn't recognize
- `FeatureNotFound(name)` — 404 on a feature lookup
- `GroupNotFound(name)` — 404 on a group lookup

## Notes

- **Auth**: there isn't any. `actor` is opaque metadata for operational traceability; treat it like a User-Agent string, not a credential.
- **Usage logging**: the server auto-logs a `view` action whenever the SDK fetches a feature by name. There's no separate `log_usage` call.
- **DataFrame**: polars is the default. Pandas conversion is opt-in via `[pandas]` extra to keep install lean.
- **Caching**: parquet reads are LRU-cached per process (size 64). Restart the kernel to drop the cache.

## Development

```bash
cd packages/client
uv sync --all-extras
uv run pytest -v
uv run mypy --strict src/
```
